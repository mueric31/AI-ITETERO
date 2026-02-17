import os, json, sys, re
import faiss
import numpy as np
from typing import List, Dict
from dotenv import load_dotenv
from openai import OpenAI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import FAISS_PATH, META_PATH, SYN_PATH, EMBED_MODEL, CHAT_MODEL, TOP_K, SCORE_THRESHOLD
from src.greetings_smart import handle_smalltalk

FALLBACK = "Mbabarira, nta makuru mfite kuri iyi ngingo."


# ---------------------------
# META & SYNONYMS LOADING
# ---------------------------
def load_meta(meta_path: str) -> List[Dict]:
    rows = []
    with open(meta_path, "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def load_synonyms(path: str) -> Dict[str, list]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            clean = {}
            for k, v in (data or {}).items():
                if isinstance(v, list):
                    clean[str(k)] = [str(x) for x in v]
            return clean
    except Exception:
        return {}


# ---------------------------
# CLEAN KINYARWANDA QUERY
# ---------------------------
def _clean_kiny_query(q: str) -> str:
    ql = q.lower().strip()
    fillers = [r"^ese\s+", r"^none\s+se\s+", r"^none\s+", r"^mbese\s+", r"^ni\s+iki\s+", r"^niki\s+"]
    for pat in fillers:
        ql = re.sub(pat, "", ql)
    return re.sub(r"\s+", " ", ql).strip()


def expand_query_with_synonyms(q: str, syn: Dict[str, list]) -> str:
    if not syn:
        return q
    q_low = q.lower()
    additions = set()
    for key, candidates in syn.items():
        key_l = key.lower()
        if key_l in q_low:
            for c in candidates:
                c = c.lower().strip()
                if c:
                    additions.add(c)
        for c in candidates:
            c_l = c.lower().strip()
            if c_l and c_l in q_low:
                additions.add(key_l)
    if additions:
        return q + " | " + " ".join(sorted(additions))
    return q


# ---------------------------
# EMBEDDINGS & RETRIEVAL
# ---------------------------
def embed_query(client: OpenAI, text: str) -> np.ndarray:
    emb = client.embeddings.create(model=EMBED_MODEL, input=[text]).data[0].embedding
    x = np.array(emb, dtype="float32")
    faiss.normalize_L2(x.reshape(1, -1))
    return x


def _keyword_candidates(meta_rows: List[Dict], query: str, syn: Dict[str, list], topn: int = 5):
    q = _clean_kiny_query(query).lower()
    tokens = [t for t in re.split(r"[^\w'']+", q) if len(t) > 2]
    extra = set()
    for key, vals in (syn or {}).items():
        key_l = key.lower()
        if key_l in q:
            for v in vals:
                v = str(v).lower().strip()
                if v and len(v) > 2:
                    extra.add(v)
        for v in vals:
            v_l = str(v).lower().strip()
            if v_l and v_l in q and len(v_l) > 2:
                extra.add(key_l)
    vocab = set(tokens) | extra
    if not vocab:
        return []
    scored = []
    for row in meta_rows:
        text = str(row.get("text", "")).lower()
        score = sum(text.count(term) for term in vocab)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:topn]]


def retrieve(client: OpenAI, index, meta_rows: List[Dict], question: str, syn: Dict[str, list]):
    base_q = _clean_kiny_query(question)
    qx = expand_query_with_synonyms(base_q, syn)
    qvec = embed_query(client, qx)

    scores, idxs = index.search(qvec.reshape(1, -1), TOP_K)
    scores = scores[0].tolist()
    idxs = idxs[0].tolist()

    pairs = [(s, meta_rows[i]) for s, i in zip(scores, idxs) if i != -1]
    good = [m for (s, m) in pairs if s >= SCORE_THRESHOLD]

    if not good:
        kw = _keyword_candidates(meta_rows, question, syn, topn=5)
        if kw:
            good = kw[:3]

    return good, scores[:len(good)]


def format_context(chunks: List[Dict]) -> str:
    out = []
    for i, ch in enumerate(chunks, 1):
        out.append(f"[Igice {i} | Page {ch.get('page','?')}] {ch['text']}")
    return "\n\n".join(out)


# ---------------------------
# LLM WITH CONTEXT (PARAPHRASE)
# ---------------------------
def ask_llm_with_context(client: OpenAI, context: str, question: str) -> str:
    system = (
        "Uri umufasha uvuga Kinyarwanda. Subiza ikibazo ukoresheje amakuru aboneka mu CONTEXT gusa.\n"
        f"Nurangiza, ntukongeremo andi makuru atari mu CONTEXT. "
        f"Niba nta gisubizo gihari, subiza '{FALLBACK}'."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"CONTEXT:\n{context}\n\nIKIBAZO:\n{question}"},
    ]
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()


# ---------------------------
# INIT & SINGLETON
# ---------------------------
_INDEX = None
_META_ROWS = None
_SYNONYMS = None
_CLIENT = None


def ensure_index_loaded(path: str):
    if not os.path.exists(path):
        raise SystemExit(f"FAISS index not found at {path}. Run build_index.py first.")
    return faiss.read_index(path)


def _init_once():
    global _INDEX, _META_ROWS, _SYNONYMS, _CLIENT
    if _CLIENT is None:
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        _CLIENT = OpenAI(api_key=api_key) if api_key else OpenAI()
    if _INDEX is None:
        _INDEX = ensure_index_loaded(FAISS_PATH)
    if _META_ROWS is None:
        _META_ROWS = load_meta(META_PATH)
    if _SYNONYMS is None:
        _SYNONYMS = load_synonyms(SYN_PATH)


# ---------------------------
# MAIN RESPONSE FUNCTION
# ---------------------------
def get_response(question: str) -> str:
    _init_once()

    # 1️⃣ Check small talk
    small = handle_smalltalk(_CLIENT, question)
    if small is not None:
        return small

    # 2️⃣ Retrieve from PDFs
    chunks, scores = retrieve(_CLIENT, _INDEX, _META_ROWS, question, _SYNONYMS)
    if chunks:
        context = format_context(chunks)
        answer = ask_llm_with_context(_CLIENT, context, question)
        if answer and answer != FALLBACK and len(answer.strip()) > 20:
            return answer

    # 3️⃣ No relevant content found → strict fallback
    return FALLBACK


# ---------------------------
# CLI
# ---------------------------
def main():
    _init_once()

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:]).strip()
        print(get_response(question) if question else FALLBACK)
    else:
        print("Andika ikibazo cyawe (Ctrl+C gusohoka):")
        while True:
            try:
                question = input(">> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nMurakoze!")
                break
            print(get_response(question) if question else FALLBACK)


if __name__ == "__main__":
    main()
