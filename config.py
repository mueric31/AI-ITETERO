from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

def pick_path(primary: Path, fallback: Path) -> str:
    return str(primary if primary.exists() else fallback)

PDF_PATHS = [
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

PDF_PATH   = os.getenv("PDF_PATH")   or pick_path(DATA / "imirire.pdf", DATA / "imirire.pdf")
FAISS_PATH = os.getenv("FAISS_PATH") or pick_path(DATA / "index.faiss", DATA / "index.faiss")
META_PATH  = os.getenv("META_PATH")  or pick_path(DATA / "meta.jsonl", DATA / "meta.jsonl")
SYN_PATH   = os.getenv("SYN_PATH")   or pick_path(DATA / "synonyms.json", DATA / "synonyms.json")

EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-large")
CHAT_MODEL  = os.getenv("CHAT_MODEL", "gpt-4o-mini")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
OVERLAP    = int(os.getenv("OVERLAP", "100"))

TOP_K           = int(os.getenv("TOP_K", "10"))
SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", "0.1"))

BOT_NAME         = os.getenv("BOT_NAME", "Umufasha w'Itetero")
GREETINGS_PERSIST = int(os.getenv("GREETINGS_PERSIST", "0"))