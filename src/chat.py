import os
import sys
import time
import re
import threading
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import read_pdf_text, chunk_by_tokens
from config import DATA, CHAT_MODEL, EMBED_MODEL
try:
    from .greetings import is_small_talk, get_smalltalk_response
except ImportError:
    from greetings import is_small_talk, get_smalltalk_response

FALLBACK        = "Munyihanganire, nta makuru mfite kuri iyi ngingo."
RETRY_ATTEMPTS  = 5
RETRY_BASE_WAIT = 2.0

# ------------------------------------------------------------------
# PDF loading
# ------------------------------------------------------------------
_cached_chunks = None

def load_pdf_chunks():
    global _cached_chunks
    if _cached_chunks is not None:
        return _cached_chunks

    pdf_files = [
        DATA / "imirire.pdf",
        DATA / "tubiteho.pdf",
        DATA / "BROCHURE_IMBONEZAMIKURIRE_Y_ABANA_BATO (1).pdf",
        DATA / "6.1 First aid PG DRAFT 5 (V14.10.22) Kinyarwanda.pdf",
        DATA / "all.pdf",
        DATA / "3.1 Play PG DRAFT 5 (V14.10.22) Kinyarwanda.pdf",
        DATA / "3.2 Play BR DRAFT 4 (V26.04.22) Kinyarwanda.pdf",
        DATA / "4.1 Prenatal newborn postnatal care PG DRAFT 5 (V14.10.22) Kinyarwanda.pdf",
        DATA / "4.2 Prenatal newborn postnatal care BR DRAFT 5 (V14.10.22) Kinyarwanda.pdf",
    ]

    all_chunks = []
    print("📚 Loading PDFs and preparing skills data...")
    for pdf_path in pdf_files:
        if not pdf_path.exists():
            print(f"⚠  {pdf_path} not found, skipping...")
            continue
        pages = read_pdf_text(str(pdf_path))
        for page_no, txt in pages:
            if not txt.strip():
                continue
            for ch in chunk_by_tokens(txt, chunk_size=900, overlap=200):
                if ch.strip():
                    all_chunks.append({
                        "source": pdf_path.name,
                        "page":   page_no,
                        "text":   ch,
                    })

    print(f"✅ Loaded {len(all_chunks)} chunks from PDFs.\n")
    _cached_chunks = all_chunks
    return _cached_chunks


# ------------------------------------------------------------------
# Core: send all chunks in batches, each batch answers independently.
#
# The prompt has one job:
#   Read the question. Read the context.
#   Understand what the person is really describing.
#   If anything in the context relates to that situation — answer it.
#   The book may use different words. That is fine.
#   A general answer in the book applies to a specific case in real life.
# ------------------------------------------------------------------

def _parse_retry_after(msg: str) -> float:
    m = re.search(r"try again in (\d+(?:\.\d+)?)s", msg, re.IGNORECASE)
    return float(m.group(1)) + 0.5 if m else 0.0


def _call_batch(batch_chunks, question, client, stop_event):
    if stop_event.is_set():
        return ""

    context = "\n\n---\n\n".join(
        f"[{c['source']} p.{c['page']}]\n{c['text']}"
        for c in batch_chunks
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are Inzozi, a Kinyarwanda child health assistant.\n"
                "You answer only in Kinyarwanda.\n\n"
                "Your reasoning process:\n"
                "1. Understand what the person is actually describing — "
                "the real situation, not just the words used.\n"
                "2. Read the CONTEXT and ask yourself: does any part of this "
                "cover the same situation, even if described differently or "
                "more generally?\n"
                "3. If yes — give that answer, adapted to what the person asked.\n"
                "4. If no part of CONTEXT is relevant at all — "
                f"reply only: '{FALLBACK}'\n\n"
                "Never refuse to answer just because the exact words differ. "
                "A book that says 'object' covers a question about a 'potato'. "
                "A book that says 'fell' covers a question about 'fell off a wall'. "
                "Use your understanding, not word matching."
            )
        },
        {
            "role": "user",
            "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"
        }
    ]

    wait = RETRY_BASE_WAIT
    for attempt in range(RETRY_ATTEMPTS):
        if stop_event.is_set():
            return ""
        try:
            resp = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                temperature=0.0,
            )
            text = resp.choices[0].message.content.strip()
            return text if text != FALLBACK else ""
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                wait_for = _parse_retry_after(err) or wait
                ##print(f"  ⏳ Rate limit {wait_for:.1f}s "
                      ##f"(attempt {attempt+1}/{RETRY_ATTEMPTS})")
                time.sleep(wait_for)
                wait *= 2
            else:
                print(f"⚠  OpenAI error: {e}")
                return ""
    return ""


# ------------------------------------------------------------------
# Orchestrator — send all chunks, collect first good answer
# ------------------------------------------------------------------

def ask_openai(chunks, question, client):
    BATCH = 35
    batches = [chunks[i:i+BATCH] for i in range(0, len(chunks), BATCH)]
    ##print(f"  📄 {len(chunks)} chunks | {len(batches)} batches")

    answers    = []
    stop_event = threading.Event()

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_call_batch, b, question, client, stop_event): i
            for i, b in enumerate(batches)
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                answers.append(result)
                if len(answers) >= 2:
                    stop_event.set()
                    break

    return max(answers, key=len) if answers else FALLBACK


# ------------------------------------------------------------------
# Public API + CLI
# ------------------------------------------------------------------

def get_response(question: str):
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    client  = OpenAI(api_key=api_key) if api_key else OpenAI()
    if is_small_talk(question):
        return get_smalltalk_response(question, client)
    chunks = load_pdf_chunks()
    return ask_openai(chunks, question, client)


def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    client  = OpenAI(api_key=api_key) if api_key else OpenAI()
    chunks  = load_pdf_chunks()

    print("Andika ikibazo cyawe (Ctrl+C gusohoka):")
    while True:
        try:
            question = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nMurakoze!")
            break
        if not question:
            continue
        if is_small_talk(question):
            answer = get_smalltalk_response(question, client)
        else:
            answer = ask_openai(chunks, question, client)
        print(answer + "\n")


if __name__ == "__main__":
    main()