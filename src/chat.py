import os
import sys
import json
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# Add project root to sys.path if needed
ROOT = Path(__file__).resolve().parent.parent
if ROOT not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import read_pdf_text, chunk_by_tokens
from config import DATA, CHAT_MODEL, EMBED_MODEL

# ---------------------------
# Constants
# ---------------------------
FALLBACK = "Mbabarira, nta makuru mfite kuri iyi ngingo."
MAX_CHUNK_BATCH = 50  # number of chunks to send to OpenAI per request

# ---------------------------
# Load PDFs and create chunks
# ---------------------------
def load_pdf_chunks():
    pdf_files = [
        DATA / "imirire.pdf",
        DATA / "tubiteho.pdf",
        DATA / "BROCHURE_IMBONEZAMIKURIRE_Y_ABANA_BATO (1).pdf",
        DATA / "6.1 First aid PG DRAFT 5 (V14.10.22) Kinyarwanda.pdf",
        DATA / "all.pdf",
        DATA / "3.1 Play PG DRAFT 5 (V14.10.22) Kinyarwanda.pdf",
        DATA / "3.2 Play BR DRAFT 4 (V26.04.22) Kinyarwanda.pdf",
        DATA / "4.1 Prenatal newborn postnatal care PG DRAFT 5 (V14.10.22) Kinyarwanda.pdf",
        DATA / "4.2 Prenatal newborn postnatal care BR DRAFT 5 (V14.10.22) Kinyarwanda.pdf"
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
            # Token-based chunking
            chunks = chunk_by_tokens(txt, chunk_size=900, overlap=200)
            for ch in chunks:
                if ch.strip():
                    all_chunks.append({
                        "source": pdf_path.name,
                        "page": page_no,
                        "text": ch
                    })

    print(f"✅ Loaded {len(all_chunks)} chunks from PDFs.\n")
    return all_chunks

# ---------------------------
# Ask OpenAI in batches
# ---------------------------
def ask_openai(chunks, question, client):
    # Split chunks into smaller batches
    answers = []
    for i in range(0, len(chunks), MAX_CHUNK_BATCH):
        batch_chunks = chunks[i:i+MAX_CHUNK_BATCH]
        context = "\n\n".join([f"[Page {c['page']}] {c['text']}" for c in batch_chunks])

        system_prompt = (
            "Uri umufasha uvuga Kinyarwanda. Subiza ikibazo ukoresheje amakuru aboneka muri CONTEXT gusa.\n"
            "Nurangiza, ntukongeremo andi makuru atari mu CONTEXT.\n"
            f"Niba nta gisubizo gihari, subiza '{FALLBACK}'."
        )

        user_prompt = f"CONTEXT:\n{context}\n\nIKIBAZO:\n{question}"

        try:
            resp = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
            )
            answer_text = resp.choices[0].message.content.strip()
            if answer_text and answer_text != FALLBACK:
                answers.append(answer_text)
        except Exception as e:
            print(f"⚠ OpenAI error: {e}")

    if not answers:
        return FALLBACK

    # Combine answers from multiple batches (take the longest / most detailed)
    final_answer = max(answers, key=len)
    return final_answer

# ---------------------------
# Main
# ---------------------------
def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if api_key else OpenAI()

    chunks = load_pdf_chunks()

    print("Andika ikibazo cyawe (Ctrl+C gusohoka):")
    while True:
        try:
            question = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nMurakoze!")
            break

        if not question:
            continue

        answer = ask_openai(chunks, question, client)
        print(answer + "\n")

if __name__ == "__main__":
    main()