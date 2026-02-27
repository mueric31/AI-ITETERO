import os
import sys
import time
import re
import threading
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to sys.path if needed
ROOT = Path(__file__).resolve().parent.parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import read_pdf_text, chunk_by_tokens
from config import DATA, CHAT_MODEL, EMBED_MODEL
from greetings import is_small_talk, get_smalltalk_response  # ← conversational layer

# ---------------------------
# Constants
# ---------------------------
FALLBACK         = "Munyihanganire, nta makuru mfite kuri iyi ngingo."
MAX_CHUNK_BATCH  = 30
MAX_WORKERS      = 2
RETRY_ATTEMPTS   = 5
RETRY_BASE_WAIT  = 2.0
MIN_SCORE        = 0.08
TOP_CHUNKS       = 90

# ---------------------------
# In-memory chunk cache
# ---------------------------
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
            print(f"⚠ {pdf_path} not found, skipping...")
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


# ---------------------------
# Step 1: Expand question into keywords
# ---------------------------

def expand_question(question: str, client: OpenAI) -> list[str]:
    prompt = (
        "Reba ikibazo cy'umuturage mu Kinyarwanda hepfo.\n"
        "Andika urutonde rw'amagambo y'ingenzi (keywords) 10-20 ajyanye n'ikibazo, "
        "harimo: amagambo ya muganga, amagambo ya gakondo, amagambo afanana, "
        "n'imizi y'amagambo (stems). Andika ijambo rimwe ku murongo. "
        "Ntusobanure, ntandike interuro. Amagambo y'Ikinyarwanda gusa.\n\n"
        f"Ikibazo: {question}"
    )
    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=150,
        )
        raw = resp.choices[0].message.content.strip()
        keywords = [
            w.strip().lower().strip(".,;:-*•")
            for w in raw.splitlines()
            if w.strip() and len(w.strip()) > 2
        ]
        original_tokens = [
            t.lower().strip(".,?!:;")
            for t in question.split()
            if len(t) > 2
        ]
        all_keywords = list(dict.fromkeys(original_tokens + keywords))
        return all_keywords
    except Exception:
        return [t.lower().strip(".,?!:;") for t in question.split() if len(t) > 2]


# ---------------------------
# Step 2: Score and filter chunks
# ---------------------------

STOP_WORDS = {
    "ni", "mu", "ku", "wa", "na", "ko", "ngo", "ariko", "kandi",
    "nta", "iki", "iyi", "uyu", "izi", "we", "ese", "ninde", "hari",
    "aho", "ubwo", "nubwo", "kuko", "gusa", "cyane", "byo", "ibyo",
    "abo", "aba", "ico", "izi", "nawe", "none", "mbere", "nyuma",
}

def _score_chunk(chunk_text: str, keywords: list[str]) -> float:
    if not keywords:
        return 0.0
    chunk_lower = chunk_text.lower()
    hits = 0.0
    for kw in keywords:
        if kw in STOP_WORDS or len(kw) < 3:
            continue
        if kw in chunk_lower:
            hits += 1.0
        elif len(kw) >= 5 and kw[:5] in chunk_lower:
            hits += 0.4
    meaningful = [k for k in keywords if k not in STOP_WORDS and len(k) >= 3]
    return hits / len(meaningful) if meaningful else 0.0


def filter_and_rank_chunks(chunks: list, keywords: list[str]) -> list:
    scored = []
    for chunk in chunks:
        score = _score_chunk(chunk["text"], keywords)
        if score >= MIN_SCORE:
            scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:TOP_CHUNKS]]


# ---------------------------
# Step 3: Batch call — strict PDF-only
# ---------------------------

def _parse_retry_after(error_msg: str) -> float:
    match = re.search(r"try again in (\d+(?:\.\d+)?)s", error_msg, re.IGNORECASE)
    return float(match.group(1)) + 0.5 if match else 0.0


def _call_batch(batch_chunks, original_question, client, stop_event):
    if stop_event.is_set():
        return ""

    context = "\n\n".join(
        f"[{c['source']} - Urupapuro {c['page']}]\n{c['text']}"
        for c in batch_chunks
    )

    system_prompt = (
        "Uri umufasha w'ubuzima uvuga Kinyarwanda gusa.\n\n"
        "AMATEGEKO AKOMEYE:\n"
        "1. Subiza GUSA ukoresheje amakuru ari mu CONTEXT hepfo.\n"
        "2. Niba amakuru ari mu CONTEXT ariko akoresheje amagambo atandukanye "
        "n'ikibazo cy'umuturage, huza ibisobanuro ukasubize.\n"
        "3. UTIBAGIWE: Ntuzongere amakuru yavuye ahandi hantu "
        "uretse ayo muri CONTEXT. Nta gutuza. Nta kwongera ibyo wibwiye.\n"
        f"4. Niba nta makuru ajyanye muri CONTEXT, subiza GUSA uti: '{FALLBACK}'\n\n"
        "Subiza mu Kinyarwanda, usobanure neza."
    )

    user_prompt = (
        f"CONTEXT (bivuye mu bitabo by'ubuzima):\n{context}\n\n"
        f"IKIBAZO CY'UMUTURAGE:\n{original_question}"
    )

    wait = RETRY_BASE_WAIT
    for attempt in range(RETRY_ATTEMPTS):
        if stop_event.is_set():
            return ""
        try:
            resp = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.0,
            )
            text = resp.choices[0].message.content.strip()
            return text if text != FALLBACK else ""

        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                sleep_for = _parse_retry_after(err) or wait
                print(f"  ⏳ Rate limit — waiting {sleep_for:.1f}s (attempt {attempt+1}/{RETRY_ATTEMPTS})")
                time.sleep(sleep_for)
                wait *= 2
            else:
                print(f"⚠ OpenAI error: {e}")
                return ""

    return ""


# ---------------------------
# Main orchestrator
# ---------------------------

def ask_openai(chunks, question, client):
    keywords = expand_question(question, client)
    relevant_chunks = filter_and_rank_chunks(chunks, keywords)

    if not relevant_chunks:
        return FALLBACK

    batches = [
        relevant_chunks[i : i + MAX_CHUNK_BATCH]
        for i in range(0, len(relevant_chunks), MAX_CHUNK_BATCH)
    ]

    answers    = []
    stop_event = threading.Event()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_call_batch, batch, question, client, stop_event): i
            for i, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                answers.append(result)
                if len(answers) >= 2:
                    stop_event.set()
                    break

    return max(answers, key=len) if answers else FALLBACK


# ---------------------------
# Public function for FastAPI
# ---------------------------

def get_response(question: str):
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    client  = OpenAI(api_key=api_key) if api_key else OpenAI()

    # ── Conversational layer (greetings, emotions, daily life) ───────────────
    if is_small_talk(question):
        return get_smalltalk_response(question, client)
    # ─────────────────────────────────────────────────────────────────────────

    chunks = load_pdf_chunks()
    return ask_openai(chunks, question, client)


# ---------------------------
# CLI interface
# ---------------------------

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

        # ── Conversational layer ─────────────────────────────────────────────
        if is_small_talk(question):
            answer = get_smalltalk_response(question, client)
        else:
            answer = ask_openai(chunks, question, client)
        # ─────────────────────────────────────────────────────────────────────

        print(answer + "\n")


if __name__ == "__main__":
    main()