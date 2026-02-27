"""
greetings.py — Human-like conversational handler (Kinyarwanda-first)

Handles greetings, emotions, daily life talk, and small talk so the
RAG pipeline only processes real health questions.
"""

import re
from openai import OpenAI

# ---------------------------
# Broad conversation detector
# ---------------------------

# Patterns that signal conversational (non-health) messages
_CONV_PATTERNS = [
    # Greetings
    r"\bmwaramutse\b", r"\bmwiriwe\b",    r"\bnimuhere\b",
    r"\bwiriwe\b",     r"\bwaramutse\b",  r"\bumeze\s+ute\b",
    r"\bumeze\s+neza\b", r"\bikomeye\b",  r"\baho\s+uri\b",
    r"\bamakuru\b",    r"\bnihabwa\b",    r"\binkuru\b",
    r"\bwitwa\b",      r"\bmuraho\b",     r"\bwiriwe\b",
    r"\bhello\b",      r"\bhi\b",         r"\bhey\b",
    r"\bbonjour\b",    r"\bgood\s+morning\b", r"\bgood\s+afternoon\b",

    # Emotions — positive
    r"\bnishimye\b",   r"\bundishimye\b", r"\bishimye\b",
    r"\bnishima\b",    r"\bundishima\b",  r"\bsangiye\b",
    r"\bhappy\b",      r"\bjoyful\b",     r"\bglad\b",

    # Emotions — negative / difficult
    r"\bnabaye\b",     r"\bubabaye\b",    r"\bnababye\b",
    r"\bmbabaye\b",    r"\bunabaye\b",    r"\bnababajwe\b",
    r"\bndicaye\b",    r"\bndicaye\b",    r"\buricaye\b",
    r"\bnkaye\b",      r"\bnkabaye\b",    r"\bnkababaye\b",
    r"\bsad\b",        r"\bunhappy\b",    r"\bdepressed\b",
    r"\bworried\b",    r"\banxious\b",

    # Tiredness / stress
    r"\bnuranye\b",    r"\bundanye\b",    r"\buranye\b",
    r"\bnkonje\b",     r"\bnshobora\s+gukomeza\b",
    r"\btired\b",      r"\bexhausted\b",  r"\bstressed\b",

    # Daily life topics
    r"\bisoko\b",      r"\bimboga\b",     r"\bibiribwa\b",
    r"\bugari\b",      r"\burugali\b",    r"\bifunguro\b",
    r"\bgurura\b",     r"\bugura\b",      r"\bgura\b",
    r"\bumurimo\b",    r"\bkazi\b",       r"\bwork\b",
    r"\bschool\b",     r"\bushuri\b",     r"\bbugesera\b",
    r"\bimana\b",      r"\bumuryango\b",  r"\bfamily\b",
    r"\bfriends\b",    r"\babantu\b",     r"\bbagenzi\b",
    r"\bimyaka\b",     r"\bbirori\b",     r"\bkuganira\b",

    # Business / dreams / plans
    r"\bbusiness\b",   r"\bntangize\b",   r"\bgutera\b",
    r"\bshishikaje\b", r"\bnshishikaje\b",r"\bplans\b",
    r"\bimpano\b",     r"\bintego\b",     r"\bsucceed\b",
    r"\bgoals\b",      r"\bdreams\b",     r"\bideyi\b",

    # Thanks & farewells
    r"\burakoze\b",    r"\bmurakoze\b",   r"\bturabonana\b",
    r"\bgenda\s+neza\b", r"\bbye\b",      r"\bau\s+revoir\b",
    r"\bthank\b",      r"\bthanks\b",     r"\bmerci\b",

    # Identity / capability
    r"\bwowe\s+ni\s+nde\b", r"\buri\s+nde\b", r"\buri\s+iki\b",
    r"\bwho\s+are\s+you\b", r"\bwhat\s+are\s+you\b",
    r"\bwhat\s+can\s+you\b", r"\bcan\s+you\s+help\b",

    # Affirmatives
    r"\bbyiza\b",  r"\bokay\b", r"\bok\b", r"\bneza\b",
    r"\bgreat\b",  r"\bvery\s+good\b",

    # Misfortune / loss / hardship
    r"\bibyago\b", r"\bnibye\b", r"\bbanyibye\b",
    r"\bnapfushije\b", r"\btwapfushije\b",
    r"\birukanywe\b", r"\birukanwe\b",
    r"\bnarirukanwe\b", r"\bihene\b",

    # Sadness & grief expressions
    r"\bagahinda\b", r"\bamarira\b",
    r"\bndababaye\b", r"\bmfite\s+agahinda\b",

    # Weather & cold
    r"\bimbeho\b", r"\bnakonje\b",
    r"\birere\b", r"\bikirere\b",
    r"\bimvura\b", r"\bubukonje\b",

    # Stress / uncertainty
    r"\bsinzi\s+uko\b", r"\bnabuze\b",
    r"\bnabuze\s+icyo\b", r"\bntazi\b",

    # School & exams
    r"\bikizamini\b", r"\bexam\b",
    r"\bku\s+ishuri\b", r"\bkwiga\b",

    # New beginnings & achievements
    r"\btangira\s+akazi\b", r"\bnatangiye\b",
    r"\bnagize\s+akazi\b",
    r"\bnaguze\b", r"\bimodoka\b",
    r"\binzozi\b", r"\bnageze\s+ku\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _CONV_PATTERNS]

# Health signals — force RAG pipeline regardless of other matches
_HEALTH_SIGNALS = {
    "ubuzima", "umwana", "indwara", "umubyeyi", "gutunga",
    "dawa", "muganga", "amagara", "akanwa", "inda",
    "kuvuka", "babyeyi", "imirire", "urwaruka", "uburwayi",
    "gusiga", "inkingo", "gutanga", "gukurikirana",
    "medical", "health", "baby", "child", "sick", "pain",
    "pregnant", "birth", "nutrition", "breastfeed", "vaccine",
    "kunywa", "kurya",
}


def is_small_talk(question: str) -> bool:
    q_lower = question.strip().lower()
    has_health = any(hw in q_lower for hw in _HEALTH_SIGNALS)
    if has_health:
        return False
    for pat in _COMPILED:
        if pat.search(q_lower):
            return True
    if len(q_lower.split()) <= 4:
        return True
    return False


# ---------------------------
# LLM-powered conversational reply
# ---------------------------

_SYSTEM_PROMPT = """\
Witwa "Inzozi". Uri inshuti y'umuturage kandi uri umufasha w'ubuzima uvuga Kinyarwanda.

AMATEGEKO Y'INGENZI:

• Subiza nk'inshuti ifite umutima.
• Interuro 2–3 gusa.
• Niba umuntu avuze inkuru nziza cyangwa gahunda nshya (akazi, kwiga, umushinga):
  - Mushimire.
  - Mumuhe ubutwari.
  - NTUBAZE ikibazo gikurikira.
  - Vuga uti: nta makuru menshi mfite kuri ibyo.

• Niba ari ibiganiro bisanzwe — subiza neza.
• Niba ari agahinda cyangwa ibyago — garagaza impuhwe.
NTUVUGE KO URI AI.
"""


def get_smalltalk_response(question: str, client: OpenAI) -> str:
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0.8,
            max_tokens=150,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return _canned_reply(question)


# ---------------------------
# Canned fallback (no API needed)
# ---------------------------

def _canned_reply(question: str) -> str:
    q = question.lower()

    # Learning / training / career paths
    if any(w in q for w in ["kwiga", "amashanyarazi", "umwuga", "training", "kwitoza"]):
        return (
            "Ni byiza cyane! Nshimye ko ufite gahunda yo kwiga cyangwa gukorera umwuga mwiza. "
            "Nta makuru menshi mfite kuri ibyo."
        )

    # Positive emotions
    if any(w in q for w in ["nishimye", "nishima", "sangiye", "happy", "glad"]):
        return "Ni byiza cyane kumva uri gushimwa! Ese hari ikintu cyihariye cyabiteye?"

    # Negative emotions / stress
    if any(w in q for w in ["mbabaye", "ubabaye", "nabaye", "ndicaye", "sad", "worried"]):
        return "Munyihanganire, nta makuru mfite kuri iyi ngingo."

    # Tiredness
    if any(w in q for w in ["nuranye", "nkonje", "tired", "exhausted"]):
        return "Ndabumva, akazi kenshi burya gashobora gutera umunaniro. Fata umwanya wo kuruhuka."

    # Daily life / market / food
    if any(w in q for w in ["isoko", "imboga", "ibiribwa", "ugari", "ifunguro"]):
        return "Isoko ni inzira nziza y'ubuzima! Ese wahuye n'ingorane zo kubona ibyo ushaka?"

    # Business / plans
    if any(w in q for w in ["business", "ntangize", "shishikaje", "intego", "ideyi"]):
        return "Ni byiza cyane kugira intego! Inzozi zitera imbere."

    # Children / family (non-medical)
    if any(w in q for w in ["abana", "umuryango", "family"]):
        return "Umuryango mwiza ni ubutunzi bw'ingenzi!"

    # Thanks
    if any(w in q for w in ["urakoze", "murakoze", "thank", "merci"]):
        return "Murakoze! Nishimiye guganira nawe."

    # Farewells
    if any(w in q for w in ["bye", "turabonana", "genda neza"]):
        return "Turabonana! Mwirinde kandi mugire amahoro."

    # Identity
    if any(w in q for w in ["nde", "iki", "who are you", "witwa"]):
        return "Nitwa ITETERO — inshuti yawe kandi umufasha w'ubuzima."

    # Loss / grief
    if any(w in q for w in ["napfushije", "twapfushije", "agahinda"]):
        return "Ndihanganisha nawe cyane. Niba wifuza kuganira, ndahari."

    # Theft / misfortune
    if any(w in q for w in ["banyibye", "ibyago"]):
        return "Mbega ibyago! Ndumva bikubabaje."

    # Job loss
    if "irukan" in q:
        return "Biragoye kubyakira. Ariko amahirwe mashya aracyaza."

    # Cold / weather
    if any(w in q for w in ["nkonje", "imbeho", "ikirere"]):
        return "Ubukonje burakaze! Gerageza kwifubika no kunywa ibishyushye."

    # Exams
    if "ikizamini" in q:
        return "Nkwifurije gutsinda ikizamini cyawe!"

    # New job
    if "tangiye akazi" in q:
        return "Ni inkuru nziza! Gutangira akazi gashya bizana amahirwe mashya."

    # Bought something / achievement
    if any(w in q for w in ["naguze", "imodoka", "inzozi"]):
        return "Wow! Gusohoza inzozi birashimishije cyane."

    # Default greeting
    return "Muraho! Ndishimye kukubona. Mbaza ikibazo cyawe!"