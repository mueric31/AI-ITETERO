import json
import re
import faiss
import numpy as np
from tqdm import tqdm
from openai import OpenAI
from config import FAISS_PATH, META_PATH, EMBED_MODEL, DATA
from utils import read_pdf_text


# ---------------------------
# CLEAN TEXT (FIX PDF ISSUES)
# ---------------------------
def clean_text(text):
    text = text.replace("\x00", "")           # remove null bytes
    text = re.sub(r'-\n', '', text)           # fix broken words
    text = re.sub(r'\n+', '\n', text)         # normalize new lines
    text = re.sub(r'\s+', ' ', text)          # remove extra spaces
    return text.strip()


# ---------------------------
# DETECT HEADINGS
# ---------------------------
def is_heading(line):
    line = line.strip()
    return (
        line.isupper()
        or line.endswith(":")
        or (len(line.split()) <= 6 and line.istitle())
    )


# ---------------------------
# SPLIT INTO PARAGRAPHS
# ---------------------------
def split_paragraphs(text):
    return [p.strip() for p in text.split("\n") if p.strip()]


# ---------------------------
# SMART CHUNKING
# ---------------------------
def smart_chunk(text, max_chars=2000, overlap=300):
    text = clean_text(text)
    paragraphs = split_paragraphs(text)

    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) <= max_chars:
            current += " " + para
        else:
            chunks.append(current.strip())
            current = para

    if current:
        chunks.append(current.strip())

    # add overlap for context continuity
    final_chunks = []
    for i, ch in enumerate(chunks):
        if i == 0:
            final_chunks.append(ch)
        else:
            overlap_text = chunks[i-1][-overlap:]
            final_chunks.append(overlap_text + " " + ch)

    # remove empty chunks
    return [c for c in final_chunks if c.strip()]


# ---------------------------
# SAFE EMBEDDING FUNCTION
# ---------------------------
def embed_texts(client, texts):
    clean_batch = []

    for t in texts:
        if not isinstance(t, str):
            continue

        t = t.strip()

        if not t:
            continue

        # remove problematic characters
        t = t.encode("utf-8", "ignore").decode("utf-8")

        # safety limit (avoid API rejection)
        if len(t) > 8000:
            t = t[:8000]

        clean_batch.append(t)

    if not clean_batch:
        return []

    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=clean_batch
    )

    return [e.embedding for e in response.data]


# ---------------------------
# MAIN PROCESS
# ---------------------------
def main():

    pdf_files = [
        DATA / "imirire.pdf",
        DATA / "tubiteho.pdf",
        DATA / "BROCHURE_IMBONEZAMIKURIRE_Y_ABANA_BATO (1).pdf",
        DATA/ "6.1 First aid PG DRAFT 5 (V14.10.22) Kinyarwanda.pdf",
        DATA/ "all.pdf",
        DATA/ "3.1 Play PG DRAFT 5 (V14.10.22) Kinyarwanda.pdf",
        DATA/ "3.2 Play BR DRAFT 4 (V26.04.22) Kinyarwanda.pdf",
        DATA/ "4.1 Prenatal newborn postnatal care PG DRAFT 5 (V14.10.22) Kinyarwanda.pdf",
        DATA/ "4.2 Prenatal newborn postnatal care BR DRAFT 5 (V14.10.22) Kinyarwanda.pdf"
        
    ]

    all_chunks = []
    meta = []

    for pdf_path in pdf_files:
        if not pdf_path.exists():
            print(f"⚠ {pdf_path} not found, skipping...")
            continue

        print(f"\n📖 Reading: {pdf_path.name}")
        pages = read_pdf_text(str(pdf_path))

        current_section = "General"

        for page_no, txt in pages:
            if not txt.strip():
                continue

            # detect headings
            for line in txt.split("\n"):
                if is_heading(line):
                    current_section = line.strip()

            # create smart chunks
            chunks = smart_chunk(txt)

            for ch in chunks:
                if not ch.strip():
                    continue

                all_chunks.append(ch)
                meta.append({
                    "source": pdf_path.name,
                    "page": page_no,
                    "section": current_section,
                    "text": ch
                })

    if not all_chunks:
        raise RuntimeError("❌ No text found in PDFs")

    print(f"\n🔎 Creating embeddings for {len(all_chunks)} chunks...")

    client = OpenAI()
    embeddings = []
    BATCH = 64

    for i in tqdm(range(0, len(all_chunks), BATCH)):
        batch = all_chunks[i:i+BATCH]
        vecs = embed_texts(client, batch)
        if vecs:
            embeddings.extend(vecs)

    if not embeddings:
        raise RuntimeError("❌ No embeddings generated")

    X = np.array(embeddings).astype("float32")

    # normalize vectors (for cosine similarity)
    faiss.normalize_L2(X)

    dim = X.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(X)

    faiss.write_index(index, FAISS_PATH)

    with open(META_PATH, "w", encoding="utf-8") as f:
        for row in meta:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("\n✅ Index built successfully!")
    print(f"Chunks indexed: {len(all_chunks)}")
    print(f"Saved index: {FAISS_PATH}")
    print(f"Metadata: {META_PATH}")


if __name__ == "__main__":
    main()
