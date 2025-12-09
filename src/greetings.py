# greetings.py
import os, json, re, datetime, random

# ---------------- Config ----------------
_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "user_profile.json")
_BOT_NAME = os.getenv("BOT_NAME", "Umufasha w'Itetero")
_DEFAULT_NAME = "Nshuti"

# Default: session-only name (no disk). Set GREETINGS_PERSIST=1 to persist across runs.
_PERSIST = os.getenv("GREETINGS_PERSIST", "0").strip() == "1"

# Words that must never be saved as a name
_STOP_NAMES = {
    "nde","ninde","gute","amakuru","muraho","mwiriwe","mwaramutse","uraho",
    "bonjour","salut","hello","hi","bite","igicamunsi","bwakeye","se","c","hehe"
}

# ---------------- Random helpers ----------------
def _rnd(opts): return random.choice(opts)

_HINT_NAME = [
    "Niba ubishaka, ushobora kumbwira izina ryawe: 'Nitwa [izina]'.",
    "Ukeneye? Vuga uti: 'Nitwa [izina]'—bizanshoboza kukwita mu izina.",
    "Niba bigushobokeye, andika 'Nitwa [izina]'."
]
_STATUS_REPLY = [
    "Meze neza, {name}! 🫶 Mbwira ikibazo cyawe.",
    "Turi hamwe neza, {name}. Vuga icyo wifuza kumenya.",
    "Ndaho ntacyo, {name}! 😄 Tugitangiriraho iki?"
]
_SMALLTALK = [
    "Nshimishijwe no kuganira nawe, {name}. Dushobora kwinjira ku 'isuku', 'inkingo', 'uburere', 'ikoranabuhanga'… watangira n'ijambo rimwe.",
    "Yego {name}, turi kumwe! Vuga ikikuraje ishinga—twinjiremo gahoro gahoro.",
    "Nditeguye kukumva, {name}. Baza icyo wifuza, nguhe igisubizo kigufi kandi gihamye."
]
_THANKS = ["Urakoze cyane, {name}! 🙏","Ndabishimiye, {name}! 😊","Urakoze kubimbwira, {name}."]
_WRONG_NAME_PROMPT = [
    "Mbabarira niba nakwise nabi. Andika: 'Nitwa [izina]'.",
    "Yooo, niba izina ritari ryo, rinyibwirire neza: 'Nitwa [izina]'.",
    "Ndasaba imbabazi—unganirize izina ryawe: 'Nitwa [izina]'."
]
_CAPABILITIES = (
    "Dushobora kuganira kuri byinshi:\n"
    "• Uburere n'imyitwarire y'abana, gukina no kwiga hakiri kare\n"
    "• Isuku (intoki, amazi meza, ibiryo, umusarane)\n"
    "• Inkingo, ubutabazi bw'ibanze (impiswi, isereri…)\n"
    "• Ikoranabuhanga (umutekano kuri murandasi, gukoresha neza)\n"
    "• Uruhare rw'ababyeyi bombi mu kurera\n"
    "Andika ijambo ry'ingenzi: 'inkingo', 'isuku', 'impiswi', 'ikoranabuhanga'…"
)

# ---------------- Time & display ----------------
def _tod():
    h = datetime.datetime.now().hour
    if 5 <= h < 12:  return "mwaramutse"
    if 12 <= h < 18: return "mwiriwe"
    return "mwiriwe"

def _now_time(): return datetime.datetime.now().strftime("%H:%M")
def _nm(name: str | None) -> str: return name.strip() if name and name.strip() else _DEFAULT_NAME

def _greet_label_from_text(t: str) -> str | None:
    t = t.lower()
    if any(k in t for k in ["mwaramutse","bwakeye","good morning"]): return "Mwaramutse"
    if any(k in t for k in ["mwiriwe","bonsoir","good evening","igicamunsi","good afternoon"]): return "Mwiriwe"
    if any(k in t for k in ["muraho","uraho","hello","salut","hi"]): return None  # generic
    return None

# ---------------- Name memory (session-first) ----------------
_SESSION_NAME = None

def _load_profile_disk():
    try:
        with open(_PROFILE_PATH, "r", encoding="utf-8") as f:
            p = json.load(f)
    except Exception:
        p = {}
    nm = p.get("name")
    if isinstance(nm, str) and nm.strip().lower() in _STOP_NAMES:
        p.pop("name", None)
        _save_profile_disk(p)
    return p

def _save_profile_disk(p):
    try:
        with open(_PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _get_name():
    global _SESSION_NAME
    if _SESSION_NAME:
        return _SESSION_NAME
    if _PERSIST:
        return _load_profile_disk().get("name")
    return None

def _set_name(name: str):
    global _SESSION_NAME
    _SESSION_NAME = name
    if _PERSIST:
        p = _load_profile_disk()
        p["name"] = name
        _save_profile_disk(p)

def _clear_name():
    global _SESSION_NAME
    _SESSION_NAME = None
    if _PERSIST:
        p = _load_profile_disk()
        p.pop("name", None)
        _save_profile_disk(p)

# ---------------- Text utils ----------------
def _strip_fillers(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"\s+(?:c|se)[\.\!\?]*\s*$", "", t, flags=re.I)
    for pat in [r"^\s*none\s+se\s+", r"^\s*none\s+", r"^\s*ese\s+", r"^\s*mbese\s+", r"^\s*sha\s+", r"^\s*basi\s+"]:
        t = re.sub(pat, "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()

def _canon_name(raw: str) -> str:
    # Fixed: dash must be at the end of character class or escaped
    cleaned = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ'' \-]", " ", (raw or "")).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    if not cleaned or cleaned.lower() in _STOP_NAMES:
        return ""
    return cleaned.title()

def _looks_like_name_question(text: str) -> bool:
    t = (text or "").strip().lower()
    return bool(re.search(r"\bnitwa\s+nde\b", t) or re.search(r"nakubwiye\s+ko\s+nitwa\s+nde\b", t))

def _extract_name_positive(text: str, allow_ndi: bool = True) -> str | None:
    """
    Extracts name only from positive claims like "Nitwa X", "Izina ryanjye ni X", optionally "Ndi X".
    """
    if _looks_like_name_question(text):
        return None
    low = (text or "").lower()
    if re.search(r"\b(sindi|ntabwo\s+nitwa|ntitwa|si\s*nitwa)\b", low):
        return None
    # Fixed: dash at the end of character class
    pats = [
        r"(?:izina\s*rya[nyj]e\s*ni|amazina\s*ya[nyj]e\s*ni|nitwa|nditwa)\s+([A-Za-zÀ-ÖØ-öø-ÿ'' \-]{2,})",
        r"(?:my\s+name\s+is)\s+([A-Za-zÀ-ÖØ-öø-ÿ'' \-]{2,})",
        r"(?:name)\s*[:=]\s*([A-Za-zÀ-ÖØ-öø-ÿ'' \-]{2,})",
    ]
    if allow_ndi:
        pats.append(r"(?<!\bsi)\bndi\s+([A-Za-zÀ-ÖØ-öø-ÿ'' \-]{2,})")

    for pat in pats:
        m = re.search(pat, text, flags=re.I)
        if m:
            cand = _canon_name(m.group(1))
            if cand:
                return cand
    return None

def _parse_negation(text: str) -> tuple[str | None, str | None]:
    """
    "sindi Eric, nitwa John" -> wrong=Eric, right=John
    "ntabwo nitwa Eric" -> wrong=Eric, right=None
    """
    wrong, right = None, None
    m = re.search(r"\b(sindi|ntabwo\s+nitwa|ntitwa|si\s*nitwa)\s+([^\s,\.!?]+)", text, flags=re.I)
    if m:
        wrong = _canon_name(m.group(2))
    n = _extract_name_positive(text, allow_ndi=False)
    if n:
        right = n
    return wrong, right

# ---------------- Intent detectors ----------------
def _is_greeting(t: str) -> bool:
    t = t.lower()
    return any(k in t for k in ["muraho","muraho neza","uraho","uraho neza","mwiriwe","wiriwe","mwaramutse","bwakeye","igicamunsi","bonjour","hello","salut","hi"])

def _is_status(t: str) -> bool:
    t = t.lower()
    return any(k in t for k in ["amakuru yawe","amakuru yanyu","mumeze gute","umeze ute","ni iki gishya","imeze ite","bimeze gute"])

def _is_here(t: str) -> bool:
    t = t.lower()
    return any(k in t for k in ["uraho","uri online","wari uraho","wiriwe ute se"])

def _is_thanks(t: str) -> bool:
    t = t.lower()
    return any(k in t for k in ["urakoze","murakoze","thanks","thank you","merci"])

def _is_help_cmd(t: str) -> bool: return t.strip().lower()=="/help"
def _is_reset_cmd(t: str) -> bool: return t.strip().lower()=="/reset"

def _is_capability(t: str) -> bool:
    t = t.lower()
    return any(k in t for k in [
        "ushobora iki","ufasha iki","twaganira kuki","ibyo tuganiraho","menu","topics",
        "ni biki uzi","ni biki uzi cyane","ni ubuhe bumenyi ufite","ubumenyi ufite","ubushobozi ufite"
    ])

def _is_time_question(t: str) -> bool:
    t = t.lower()
    return bool(re.search(r"(saa\s*ngapi|sa+\s*ngapi|sangapi|sangahe|igihe\s*ki|ni\s*iki\s*gihe)", t))

def _is_location_question(t: str) -> bool:
    t = t.lower()
    return any(k in t for k in ["uri he","uba he","ukorera hehe","aho uba","ubahe"])

def _is_city_status(t: str) -> bool:
    t = t.lower()
    return ("kigali" in t or "rwanda" in t) and any(x in t for x in ["byifashe gute","amakuru","bimeze gute","mumeze gute"])

def _asks_to_recall_name_raw(t: str) -> bool:
    t = t.lower()
    pats = [
        r"(?:uribuka|urakibuka|uracyibuka|wibuka).*(?:izina|amazina|name)",
        r"\bharya\s+(?:nitwa|ndi)\s+nde\b",
        r"nakubwiye\s+ko\s+(?:nitwa|ndi)\s+nde\b",
        r"\buracyanyibuka\s*se\b",
        r"\buracyanyibuka\b",
        r"\bwampaye\s+izina\s*se\b"
    ]
    return any(re.search(p, t) for p in pats)

def _is_affection(t: str) -> bool:
    t = t.lower()
    return any(k in t for k in ["ndakunda","ndagukunda","ndakunze","ndagukunda cyane","ndakunda cyane","nakwikundiye","nagukunze","ndabikunze"])

# ---------------- Public entrypoint ----------------
def handle_smalltalk(text: str) -> str | None:
    """
    Small-talk handler. Returns answer or None if not small talk.
    """
    if not text or not text.strip():
        return None

    # Commands
    if _is_help_cmd(text):
        return (
            "👉 **Ubufasha /help**\n"
            "- Izina (OPTIONAL): _Nitwa [izina]_\n"
            "- Amakuru: _amakuru yawe_, _umeze ute_\n"
            "- Igihe: _saa ngapi ubu?_\n"
            "- Uko mfasha: _ni biki uzi_, _ibyo tuganiraho_\n"
            "- Kwibutsa izina: _urakibuka izina ryanjye?_\n"
            "- Gusiba izina: _/reset_"
        )
    if _is_reset_cmd(text):
        _clear_name()
        return "Nesheje izina ryari ryabitswe muri iyi session. Dukomeze nk'Inshuti'—ushobora kuvuga 'Nitwa [izina]' igihe icyo ari cyo cyose."

    # Negation/correction
    wrong, right = _parse_negation(text)
    if wrong:
        if right:
            _set_name(right)
            return f"Byiza! Noneho ndakwita {right}."
        return _rnd(_WRONG_NAME_PROMPT)

    # Optional name capture
    maybe = _extract_name_positive(text)
    if maybe:
        _set_name(maybe)
        return _rnd([
            f"Nishimiye kukumenya, {maybe}! 🎉 Baza ikibazo cyawe mu Kinyarwanda.",
            f"Ndanezerewe kukumenya, {maybe}! ✨ Ni iki twatangiriraho?",
            f"Byiza cyane, {maybe}! 😊 Tangiye umbaza icyo wifuza kumenya."
        ])

    # Intents
    raw = (text or "").strip()
    low = _strip_fillers(text).lower()
    uname = _nm(_get_name())

    # Greeting
    if _is_greeting(low):
        label = _greet_label_from_text(raw) or _tod().capitalize()
        base = f"{label}, {uname}! Nitwa {_BOT_NAME}."
        return base if random.random() > 0.30 else f"{base} {_rnd(_HINT_NAME)}"

    # Status / presence
    if _is_status(low) or _is_here(low):
        return _rnd(_STATUS_REPLY).format(name=uname)

    # Time
    if _is_time_question(low):
        return f"Ubu ni saa {_now_time()}, {uname}. ⏰"

    # Location
    if _is_location_question(low):
        return f"{uname}, ndi porogaramu ikorera kuri mudasobwa/seriveri; mpora ndi hano kugufasha. 🤖"

    # City/country status
    if _is_city_status(low):
        return f"{uname}, sinafata amakuru y'ubu-hubu y'aho uri. Ariko nshobora kuguha inama rusange ku isuku, inkingo, n'ibindi."

    # Capabilities / topics
    if _is_capability(low) or "ibyo tuganiraho" in low:
        return f"{uname}, dore ibyo nshoboye cyane:\n{_CAPABILITIES}"

    # Recall name
    if _asks_to_recall_name_raw(raw):
        prof = _get_name()
        return f"Yego, ndaribuka. Witwa {prof}." if prof else f"Nta zina nari mfite. {_rnd(_HINT_NAME)}"

    # Thanks
    if _is_thanks(low):
        return _rnd(_THANKS).format(name=uname)

    # Affection & friendly small talk
    if _is_affection(low):
        return f"Nawe urakoze kubivuga, {uname}! 💙 Ndi hano kugufasha igihe cyose."
    if re.search(r"\bturi\s*(?:ba|sa)?ngahe\b", low):
        return "Turi babiri—wowe nanjye 🙂."
    if any(k in low for k in ["nifuza\s+kuganira", "kuganira nawe", "tuganire", "duganire", "uzi iki","ushobora iki","ufasha iki"]):
        return _rnd(_SMALLTALK).format(name=uname)

    # Not small talk
    return None
