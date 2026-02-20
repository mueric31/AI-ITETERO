import json
import re
import faiss
import numpy as np
from tqdm import tqdm
from openai import OpenAI
from config import FAISS_PATH, META_PATH, EMBED_MODEL, DATA
from utils import read_pdf_text, split_into_sentences

# ---------------------------
# CLEAN TEXT
# ---------------------------
def clean_text(text):
    text = text.replace("\x00", "")
    text = re.sub(r'-\n', '', text)
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ---------------------------
# SMART CHUNKING
# ---------------------------
def smart_chunk(text, max_chars=2000, overlap=300):
    text = clean_text(text)
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
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

    # add overlap
    final_chunks = []
    for i, ch in enumerate(chunks):
        if i == 0:
            final_chunks.append(ch)
        else:
            overlap_text = chunks[i-1][-overlap:]
            final_chunks.append(overlap_text + " " + ch)
    return [c for c in final_chunks if c.strip()]

# ---------------------------
# EMBEDDING
# ---------------------------
def embed_texts(client, texts):
    clean_batch = [t.strip() for t in texts if t.strip()]
    if not clean_batch:
        return []
    resp = client.embeddings.create(model=EMBED_MODEL, input=clean_batch)
    return [e.embedding for e in resp.data]

# ---------------------------
# MAIN
# ---------------------------
def main():
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
    meta = []

    for pdf_path in pdf_files:
        if not pdf_path.exists():
            print(f"⚠ {pdf_path.name} not found, skipping...")
            continue
        print(f"\n📖 Reading: {pdf_path.name}")
        pages = read_pdf_text(str(pdf_path))
        current_section = "General"
        for page_no, txt in pages:
            if not txt.strip():
                continue
            # detect headings
            for line in txt.split("\n"):
                line = line.strip()
                if line.isupper() or line.endswith(":") or (len(line.split()) <= 6 and line.istitle()):
                    current_section = line
            # chunk
            chunks = smart_chunk(txt)
            for ch in chunks:
                all_chunks.append(ch)
                meta.append({"source": pdf_path.name, "page": page_no, "section": current_section, "text": ch})

    if not all_chunks:
        raise RuntimeError("No text found in PDFs")

    print(f"\n🔎 Creating embeddings for {len(all_chunks)} chunks...")
    client = OpenAI()
    embeddings = []
    BATCH = 32
    for i in tqdm(range(0, len(all_chunks), BATCH)):
        batch = all_chunks[i:i+BATCH]
        vecs = embed_texts(client, batch)
        if vecs:
            embeddings.extend(vecs)

    if not embeddings:
        raise RuntimeError("No embeddings generated")

    X = np.array(embeddings).astype("float32")
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
