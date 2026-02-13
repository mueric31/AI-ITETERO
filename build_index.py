import json, os, faiss, numpy as np
from tqdm import tqdm
from openai import OpenAI
from config import FAISS_PATH, META_PATH, EMBED_MODEL, CHUNK_SIZE, OVERLAP, DATA
from utils import read_pdf_text, chunk_by_tokens

def embed_texts(client: OpenAI, texts):
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [e.embedding for e in resp.data]

def main():
    # Process all PDFs in the data directory
    pdf_files = [
        DATA / "imirire.pdf",
        DATA / "tubiteho.pdf"
    ]
    
    all_chunks = []
    meta = []
    
    for pdf_path in pdf_files:
        if not pdf_path.exists():
            print(f"Warning: {pdf_path} not found, skipping...")
            continue
            
        print(f"\nReading PDF from: {pdf_path}")
        pages = read_pdf_text(str(pdf_path))
        
        for page_no, txt in pages:
            if not txt.strip():
                continue
            chunks = chunk_by_tokens(txt, CHUNK_SIZE, OVERLAP)
            for ch in chunks:
                all_chunks.append(ch)
                meta.append({
                    "page": page_no, 
                    "text": ch,
                    "source": pdf_path.name
                })

    if not all_chunks:
        raise RuntimeError("No text found in any PDF.")

    print(f"\nEmbedding {len(all_chunks)} chunks from {len(pdf_files)} PDFs with model {EMBED_MODEL} ...")
    client = OpenAI()
    embs = []
    B = 64
    for i in tqdm(range(0, len(all_chunks), B)):
        batch = all_chunks[i : i+B]
        embs.extend(embed_texts(client, batch))

    X = np.array(embs).astype("float32")
    # Normalize for cosine similarity via inner product
    faiss.normalize_L2(X)
    dim = X.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(X)

    faiss.write_index(index, FAISS_PATH)
    with open(META_PATH, "w", encoding="utf-8") as f:
        for row in meta:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nSaved index to {FAISS_PATH} and meta to {META_PATH}")
    print(f"Total chunks indexed: {len(all_chunks)}")

if __name__ == "__main__":
    main()
