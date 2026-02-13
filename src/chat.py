# chat.py
import os, json, sys, re
import faiss
import numpy as np
from typing import List, Dict
from dotenv import load_dotenv
from openai import OpenAI

# Add parent dir to path for imports
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import (
    FAISS_PATH, META_PATH, SYN_PATH,
    EMBED_MODEL, CHAT_MODEL,
    TOP_K, SCORE_THRESHOLD,
)

from src.greetings_smart import handle_smalltalk

FALLBACK = "ntamakuru ndagira kuri iyi ngingo"

# --------------- I/O helpers ---------------

def load_meta(meta_path: str) -> List[Dict]:
    rows = []
    with open(meta_path, "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def load_synonyms(path: str) -> Dict[str, List[str]]:
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


# --------------- Query processing ---------------

def _clean_kiny_query(q: str) -> str:
    """
    Normalize common Kinyarwanda question fillers to improve retrieval.
    """
    ql = q.lower().strip()
    fillers = [
        r"^ese\s+",
        r"^none\s+se\s+",
        r"^none\s+",
        r"^mbese\s+",
        r"^ni\s+iki\s+",
        r"^niki\s+",
    ]
    for pat in fillers:
        ql = re.sub(pat, "", ql)
    return re.sub(r"\s+", " ", ql).strip()


def expand_query_with_synonyms(q: str, syn: Dict[str, List[str]]) -> str:
    """
    Expand query using synonyms.
    """
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


# --------------- Embedding & retrieval ---------------

def embed_query(client: OpenAI, text: str) -> np.ndarray:
    emb = client.embeddings.create(model=EMBED_MODEL, input=[text]).data[0].embedding
    x = np.array(emb, dtype="float32")
    faiss.normalize_L2(x.reshape(1, -1))
    return x


def _keyword_candidates(meta_rows: List[Dict], query: str, syn: Dict[str, List[str]], topn: int = 5):
    """
    Lightweight keyword fallback: rank chunks by query term frequency.
    """
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


def retrieve(client: OpenAI, index, meta_rows: List[Dict], question: str, syn: Dict[str, List[str]]):
    base_q = _clean_kiny_query(question)
    qx = expand_query_with_synonyms(base_q, syn)
    qvec = embed_query(client, qx)

    scores, idxs = index.search(qvec.reshape(1, -1), TOP_K)
    scores = scores[0].tolist()
    idxs = idxs[0].tolist()

    pairs = []
    for score, i in zip(scores, idxs):
        if i == -1:
            continue
        pairs.append((score, meta_rows[i]))

    # Filter by threshold
    good = [m for (s, m) in pairs if s >= SCORE_THRESHOLD]

    # Fallback: keyword search if nothing passed threshold
    if not good:
        kw = _keyword_candidates(meta_rows, question, syn, topn=5)
        if kw:
            good = kw[:3]

    return good, scores[: len(good)]


# --------------- LLM answering ---------------

def format_context(chunks: List[Dict]) -> str:
    out = []
    for i, ch in enumerate(chunks, 1):
        out.append(f"[Igice {i} | Page {ch.get('page','?')}] {ch['text']}")
    return "\n\n".join(out)


def is_parenting_related(client: OpenAI, question: str) -> bool:
    """
    Determine if the question is related to parenting for children 0-6 years old,
    including pregnancy, breastfeeding, maternal health, and first aid.
    """
    system = (
        "You are a classifier. Determine if the question is about ANY of these topics:\n\n"
        
        "PREGNANCY & MATERNAL HEALTH:\n"
        "- Pregnancy, prenatal care, nutrition during pregnancy\n"
        "- Prenatal checkups, ultrasound, partner involvement\n"
        "- Childbirth preparation, delivery planning, signs of labor\n"
        "- Postpartum care, maternal recovery\n\n"
        
        "BREASTFEEDING & INFANT FEEDING:\n"
        "- Breastfeeding (exclusive 6 months), proper technique\n"
        "- Milk supply, breast care, sore nipples\n"
        "- Introduction of complementary foods (6+ months)\n"
        "- Nutrition for children 0-6 years (5 food groups)\n\n"
        
        "FIRST AID & EMERGENCIES (for children 0-6 or mothers):\n"
        "- Fever management, choking, burns, cuts\n"
        "- Seizures, fractures, animal bites\n"
        "- Diarrhea treatment (ORS), dehydration\n"
        "- Head injuries, bleeding, poisoning\n\n"
        
        "FATHER'S ROLE & PARENTING:\n"
        "- Active father participation, shared responsibilities\n"
        "- Partner support during pregnancy and childcare\n"
        "- Bonding with children, family involvement\n\n"
        
        "CHILD DEVELOPMENT & EDUCATION (0-6 years):\n"
        "- Play importance, brain development, early learning\n"
        "- Developmental milestones, speech and language\n"
        "- Early childhood education, preparing for school\n"
        "- Reading, singing, storytelling to children\n\n"
        
        "POSITIVE DISCIPLINE & BEHAVIOR:\n"
        "- Non-violent discipline methods\n"
        "- Age-appropriate guidance and consequences\n"
        "- Managing tantrums, teaching self-control\n"
        "- Building trust, setting routines\n\n"
        
        "HYGIENE & SANITATION:\n"
        "- Handwashing (critical times)\n"
        "- Safe water (boiling, treatment)\n"
        "- Toilets/latrines, proper waste disposal\n"
        "- Food safety, compound cleanliness\n\n"
        
        "HEALTH & VACCINATIONS:\n"
        "- Vaccination schedules for children 0-6\n"
        "- Monthly health checkups, growth monitoring\n"
        "- Common childhood illnesses\n"
        "- When to seek medical help\n\n"
        
        "CHILDREN WITH DISABILITIES:\n"
        "- Inclusion, prevention, causes of disabilities\n"
        "- Support services, inclusive education\n"
        "- Equal rights and opportunities\n\n"
        
        "TECHNOLOGY & INTERNET SAFETY:\n"
        "- Safe use of digital devices for young children\n"
        "- Screen time management\n"
        "- Online dangers and parental guidance\n\n"
        
        "CHILD PROTECTION:\n"
        "- Preventing violence, abuse, neglect\n"
        "- Creating safe environments\n"
        "- Domestic violence effects on children\n\n"
        
        "FAMILY PLANNING:\n"
        "- Child spacing (recommended 2+ years)\n"
        "- Birth control methods\n"
        "- Family planning counseling\n\n"
        
        "Answer with ONLY 'YES' if the question is about ANY of these topics.\n"
        "Answer with ONLY 'NO' if about: children >6 years, weather, news, sports, politics, technology troubleshooting, or unrelated topics."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Is this question about parenting children 0-6 years, pregnancy, breastfeeding, or first aid?\n\nQuestion: {question}"},
    ]
    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            temperature=0.0,
            max_tokens=10,
        )
        answer = resp.choices[0].message.content.strip().upper()
        return "YES" in answer
    except Exception:
        return False


def ask_llm_with_context(client: OpenAI, context: str, question: str) -> str:
    """
    Ask LLM using PDF context. Returns answer or FALLBACK if context doesn't have answer.
    """
    system = (
        "Uri umufasha uvuga Kinyarwanda. Subiza ikibazo ukoresheje amabwire aboneka mu CONTEXT.\n\n"
        
        "AMATEGEKO AKURIKIZWA:\n"
        "1. Niba CONTEXT ifite igisubizo cyuzuye → tanga igisubizo.\n"
        "2. Niba CONTEXT ifite amakuru y'umwe mu bisobanuro by'ijambo (nk'umuhondo = amashereka CYANGWA indwara) → tanga icyo uhasanze kandi uvuge ko hashobora kubaho ibindi bisobanuro.\n"
        "3. Niba CONTEXT ifite amakuru menshi ariko atuzuye → tanga ibyo uhasanze.\n"
        f"4. GUSA niba CONTEXT idafite aho ihuriye n'ikibazo → subiza '{FALLBACK}'.\n\n"
        
        "IBYITONDERWA BYIHARIYE:\n"
        "- 'Umuhondo' bishobora kuba: amashereka ya mbere (colostrum) CYANGWA indwara y'umuhondo (jaundice)\n"
        "- Niba CONTEXT ivuga kimwe muri ibyo, tanga icyo uhasanze kandi uvuge: 'Niba wari kubaza ku bindi bisobanuro...'\n"
        "- Irinde gukabya cyangwa guhanga ibisubizo bidashingiye ku CONTEXT."
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


def ask_llm_general(client: OpenAI, question: str) -> str:
    """
    Ask LLM without PDF context - uses its general knowledge about parenting.
    Only used when question is parenting-related but not found in PDFs.
    Covers: children 0-6 years, pregnancy, breastfeeding, maternal health, and first aid.
    """
    system = (
        "You are a helpful parenting and maternal health assistant with comprehensive expertise in:\n\n"
        
        "PREGNANCY & MATERNAL HEALTH: Prenatal care, nutrition during pregnancy, prenatal checkups, "
        "ultrasound, partner involvement, childbirth preparation, delivery planning, signs of labor, "
        "postpartum care, maternal recovery.\n\n"
        
        "BREASTFEEDING & NUTRITION: Exclusive breastfeeding (6 months), proper technique, milk supply "
        "management, breast care, sore nipples, complementary foods introduction (6+ months), "
        "nutrition for children 0-6 years (5 food groups), balanced meals.\n\n"
        
        "FIRST AID & EMERGENCIES: Fever management, choking response, burn treatment, cuts and bleeding, "
        "seizures/convulsions, fractures, animal bites, diarrhea treatment (ORS), dehydration, "
        "head injuries, poisoning response.\n\n"
        
        "FATHER'S ROLE: Active participation in childcare, shared household responsibilities, "
        "bonding with children, supporting pregnant partners, involvement in prenatal care.\n\n"
        
        "CHILD DEVELOPMENT (0-6 years): Play importance, brain development, early learning, "
        "developmental milestones, speech and language, early childhood education, preparing for school, "
        "reading and storytelling.\n\n"
        
        "POSITIVE DISCIPLINE: Non-violent discipline methods, age-appropriate guidance, managing tantrums, "
        "teaching self-control, building trust, setting routines, consequences without punishment.\n\n"
        
        "HYGIENE & SANITATION: Handwashing (critical times), safe water preparation (boiling/treatment), "
        "proper toilet/latrine use, food safety, compound cleanliness, disease prevention.\n\n"
        
        "HEALTH & VACCINATIONS: Vaccination schedules for children 0-6, monthly health checkups, "
        "growth monitoring, common childhood illnesses, when to seek medical help.\n\n"
        
        "CHILDREN WITH DISABILITIES: Inclusion strategies, prevention, causes of disabilities, "
        "support services, inclusive education, equal rights.\n\n"
        
        "TECHNOLOGY SAFETY: Age-appropriate use of digital devices, screen time management, "
        "online safety, parental guidance on internet use.\n\n"
        
        "CHILD PROTECTION: Preventing violence/abuse/neglect, creating safe environments, "
        "effects of domestic violence on children.\n\n"
        
        "FAMILY PLANNING: Child spacing (recommend 2+ years), birth control methods, family planning counseling.\n\n"
        
        "Provide accurate, practical, and culturally sensitive advice. "
        "Answer in Kinyarwanda if the question is in Kinyarwanda, otherwise answer in the language of the question. "
        "Keep answers concise, practical, and focused on children aged 0-6 years or pregnant/nursing mothers. "
        "If the question involves medical emergencies, always advise seeking immediate medical attention."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()
    return resp.choices[0].message.content.strip()


# --------------- Init & public API ---------------

_INDEX = None
_META_ROWS = None
_SYNONYMS = None
_CLIENT = None


def ensure_index_loaded(path: str):
    if not os.path.exists(path):
        raise SystemExit(f"FAISS index not found at {path}. Run build_index.py first.")
    return faiss.read_index(path)


def _init_once():
    """Lazy init: load once."""
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


def get_response(question: str) -> str:
    """
    Main function to get chatbot response with the following logic:
    1. Check for small talk/greetings first (handle with greetings.py)
    2. Try to find answer in PDFs
    3. If found in PDFs, return that answer
    4. If not found in PDFs:
       - If question is parenting-related (0-6 years, pregnancy, breastfeeding, first aid), use OpenAI general knowledge
       - If question is NOT parenting-related, return "no information" message
    """
    _init_once()

    # Check for small talk first (greetings, emotions, daily life conversation)
    # AI-powered: uses OpenAI to intelligently detect and respond naturally
    small = handle_smalltalk(_CLIENT, question)
    if small is not None:
        return small

    # Try to retrieve relevant chunks from PDFs
    chunks, scores = retrieve(_CLIENT, _INDEX, _META_ROWS, question, _SYNONYMS)
    
    # If we found relevant chunks in PDFs, try to get answer from them
    pdf_answer = None
    if chunks and len(chunks) > 0:
        context = format_context(chunks)
        pdf_answer = ask_llm_with_context(_CLIENT, context, question)
        
        # If the LLM found a real answer in the context (not the fallback message)
        if pdf_answer and pdf_answer != FALLBACK and len(pdf_answer) > 20:
            return pdf_answer
    
    # No good answer found in PDFs - check if question is parenting-related
    if is_parenting_related(_CLIENT, question):
        # Question is about parenting (0-6 years), pregnancy, breastfeeding, or first aid - use OpenAI general knowledge
        return ask_llm_general(_CLIENT, question)
    else:
        # Question is NOT about parenting - inform user
        return "Mbabarira, nta makuru mfite kuri iyi ngingo. Nshobora gufasha kubijanye n'uburere bw'abana bafite imyaka 0-6, inda, konsa, n'ubufasha bw'ibanze gusa."


# --------------- CLI main ---------------

def main():
    _init_once()

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:]).strip()
        if not question:
            print(FALLBACK)
            return

        # Use the unified get_response function
        answer = get_response(question)
        print(answer)
    else:
        print("Andika ikibazo cyawe (Ctrl+C gusohoka):")
        while True:
            try:
                question = input(">> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nMurakoze!")
                break

            if not question:
                print(FALLBACK)
                continue

            # Use the unified get_response function
            answer = get_response(question)
            print(answer)


if __name__ == "__main__":
    main()
