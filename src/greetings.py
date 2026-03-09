"""
greetings.py — Human-like conversational handler (Kinyarwanda-first)

Handles greetings, emotions, daily life talk, and small talk so the
RAG pipeline only processes real health questions.

Includes harmful content detection (regex + LLM moderation) to block
inappropriate messages before any conversational reply is generated.
"""

import re
from openai import OpenAI

# ============================================================
# LAYER 1: Harmful content — fast regex block
# ============================================================

_HARMFUL_PATTERNS = [
    # Killing / violence
    r"\bkwica\b", r"\bnishe\b", r"\bicwa\b", r"\bnarice\b",
    r"\bkill\b", r"\bmurder\b", r"\bbomb\b", r"\bweapon\b",
    r"\bguhohotera\b", r"\bgukomeretsa\b",

    # Sexual / adultery
    r"\bguswera\b", r"\bkuryamana\b",
    r"\bsex\b", r"\bsexual\b", r"\bporn\w*\b",
    r"\bmalaya\b", r"\bprostitut\w*\b",
    r"\bnasambany\w*\b", r"\bsambany\w*\b",
    r"\bgusambana\b", r"\bubusambane\b", r"\buzinzi\b",

    # Sexual arousal / body parts
    r"\bumushyukwe\b",
    r"\bubusize\b",
    r"\bibitsina\b",
    r"\bingimbi\b",

    # Child abuse / underage
    r"\bumwana\s+(?:muto\s+)?utujuje\b",
    r"\butujuje\s+imyaka\b",
    r"\bn?(?:a|u)?koze\s+ubukwe\s+n.umwana\b",

    # Rape / assault
    r"\brape\b", r"\bku\s*ngufu\b", r"\bgufata\s+ku\s+ngufu\b",

    # Suicide / self-harm
    r"\bkwiyahur\w*\b", r"\bkwiyic\w*\b", r"\bsuicid\w*\b",

    # Insults
    r"\bfuck\b", r"\bshit\b", r"\bbitch\b", r"\basshole\b",
    r"\bimbwa\b", r"\bumupfu\b", r"\bigikoko\b",

    # Drugs
    r"\bheroin\b", r"\bcocain\w*\b", r"\bikiyobyabwenge\b",

    # Witchcraft
    r"\buroyi\b", r"\bumurozi\b", r"\bkuroga\b",

    # Bestiality
    r"\binyamanswa\b", r"\bibitungwa\b",

    # Homosexuality / LGBT (in Kinyarwanda context these are flagged per local law & app scope)
    # "umutinganyi" is the common slang for homosexual in Kinyarwanda
    r"\bumutinganyi\b",     # homosexual person (noun)
    r"\babaatinganyi\b",    # plural
    r"\bubutinganyi\b",     # homosexuality (abstract noun)
    r"\bgutin\w*gana\b",    # verb form — gutingana / gutinganira
    r"\btingana\b",
    r"\bgay\b",             r"\blesbien\w*\b",  r"\blesbian\w*\b",
    r"\bhomosexu\w*\b",     r"\blgbt\w*\b",
    r"\bqueer\b",           r"\bbisexu\w*\b",
    r"\btransgend\w*\b",    r"\btransexu\w*\b",

    # Anal / sodomy references
    r"\bmukibuno\b",
    r"\bmu\s+kibuno\b",
    r"\bkibuno\b",
    r"\bsodomi\w*\b",
    r"\bsodom\w*\b",

    # Fighting / physical assault
    r"\bkunyaga\b",
    r"\bkurwana\b",         r"\brwana\w*\b",
    r"\bkurwanya\b",
    r"\bnzarwane\b",        r"\bnzarwanye\b",
    r"\btuzarwane\b",       r"\bbazarwane\b",
    r"\bgukubita\w*\b",     r"\bnzakugubita\b",   r"\bgubita\w*\b",
    r"\bguhiga\b",
    r"\bgutoteza\b",        r"\bgutotez\w*\b",    r"\b\w*toteza\b",
    r"\bkuvirirana\b",
    r"\bfight\b",           r"\bfighting\b",
    r"\battack\b",          r"\battacking\b",
    r"\bbeat\s+up\b",

    # War / armed conflict
    r"\birwaniro\b",
    r"\burudaca\b",
    r"\bintambara\b",
    r"\bmilisi\b",
    r"\binterahamwe\b",
    r"\bimpuzamugambi\b",
    r"\bintwaro\b",
    r"\bbombe\b",           r"\bgrenade\b",
    r"\bigitero\b",
    r"\bkugaba\s+igitero\b",
    r"\bwar\b",             r"\bwarfare\b",
    r"\barmed\s+group\b",   r"\brebel\w*\b",
    r"\bterror\w*\b",       r"\bterroris\w*\b",
    r"\bjihad\b",           r"\bextremis\w*\b",

    # Revenge / retaliation
    r"\bkwishumbusha\b",    r"\bkwishumbush\w*\b",
    r"\bkwihora\b",         r"\bkwihor\w*\b",
    r"\bkugirira\s+nabi\b",
    r"\bkumarira\b",        r"\bkumarir\w*\b",    r"\bbamarir\w*\b",    r"\bnzabamarira\b",    r"\btuzabamarira\b",
    r"\brevenge\b",         r"\brevenging\b",
    r"\bretaliat\w*\b",     r"\bvengeance\b",
    r"\bkuhora\b",

    # Hate speech / ethnic incitement
    r"\binyenzi\b",
    r"\bibyitso\b",
    r"\bkubangamira\b",
    r"\bkurimbura\b",       r"\bkurimbur\w*\b",
    r"\bugandagira\b",
    r"\bjenocide\b",        r"\bgenocide\b",
    r"\bgutsemba\b",        r"\bgutsemb\w*\b",
    r"\bhate\s+speech\b",
    r"\bpropaganda\b",
    r"\bhutu\s+power\b",
    r"\bkubeshya\s+abantu\b",


    # Hate speech / ethnic incitement
    r"\binyenzi\b",
    r"\bibyitso\b",
    r"\bkubangamira\b",
    r"\bkurimbura\b",       r"\bkurimbur\w*\b",
    r"\bugandagira\b",
    r"\bjenocide\b",        r"\bgenocide\b",
    r"\bgutsemba\b",        r"\bgutsemb\w*\b",
    r"\bhate\s+speech\b",
    r"\bpropaganda\b",
    r"\bhutu\s+power\b",
    r"\bkubeshya\s+abantu\b",

    # Ethnic / tribal identity comparison or discrimination
    r"\bubwoko\b",                          # ethnicity / tribe (the word itself in this context)
    r"\bumwoko\b",                          # singular form
    r"\bamoko\b",                           # plural form
    r"\bhutu\b",            r"\btutsi\b",   # ethnic group names used in comparison/hate context
    r"\btwa\b",                             # third Rwandan ethnic group
    r"\bmututsi\b",         r"\bmuhutu\b",  r"\bmutwa\b",
    r"\babatutsi\b",        r"\babahutu\b", r"\babatwa\b",

    # Nationality / country comparisons framed as superiority
    r"\babarundi\b",        r"\bumurundi\b",
    r"\babakongo\b",        r"\bumukongo\b",
    r"\babanyarwanda\s+ni\s+\w+\s+kuruta\b",  # "Banyarwanda are better than..."
    r"\b\w+\s+ni\s+\w+\s+kuruta\s+\w+\b",    # "X are better than Y" pattern

    # Group superiority / inferiority language
    r"\bkuruta\s+abandi\b",                 # "better than others"
    r"\bbaruta\s+abandi\b",
    r"\bbaruta\b",                          # broad "surpass / are better than"
    r"\bni\s+\w+\s+kuruta\b",              # "are [adj] more than"
    r"\babantu\s+b[ae]\s+\w+\s+ni\s+\w+\s+kuruta\b",  # "people of X are more ... than"
    r"\b\w+\s+ni\s+mabi\s+kuruta\b",       # "X are worse than"
    r"\b\w+\s+ni\s+myiza\s+kuruta\b",      # "X are better than"

    # Religion-based comparison / discrimination
    r"\bgukristo\b",        r"\bubusilamu\b",
    r"\babakristo\s+ni\b",  r"\babasilamu\s+ni\b",
    r"\bumuzungu\b",        r"\babazungu\b",         # racial comparisons
    r"\bumukara\b",         r"\babakara\b",

    # General group hate / "I hate these people" type phrases
    r"\bnanga\s+ab\w+\b",                   # "I hate people of..."
    r"\bnanga\s+um\w+\b",                   # "I hate a person of..."
    r"\bundanga\s+ab\w+\b",
    r"\bundanga\s+um\w+\b",
    r"\babashaje\s+ni\s+\w+\s+kuruta\b",   # age-group comparisons
    r"\bukwiye\s+kwicwa\b",                 # "deserve to die"
    r"\bukwiye\s+gukurwa\b",               # "deserve to be removed"
    r"\bni\s+bo\s+batera\s+ingorane\b",    # "they are the ones causing problems"
    r"\bbi\s+bera\s+ingorane\b",
    r"\bni\s+bo\s+bica\b",                 # "they are the ones killing"
    r"\bni\s+bo\s+babica\b",

    # Job / profession comparison — ranking or judging which work is better/worse/more respectable
    # Kinyarwanda job words
    r"\bumurimo\s+w[ao]\s+\w+\s+ni\s+\w+\s+kuruta\b",  # "work of X is better than..."
    r"\bakazi\s+k[ao]\s+\w+\s+ni\s+\w+\s+kuruta\b",    # "job of X is better than..."
    r"\bumurimo\s+mwiza\s+kuruta\b",   # "better work than"
    r"\bumurimo\s+mubi\s+kuruta\b",    # "worse work than"
    r"\bakazi\s+mwiza\s+kuruta\b",
    r"\bakazi\s+kabi\s+kuruta\b",
    r"\bumurimo\s+w[ao]\s+\w+\s+ni\s+mubi\b",      # "work of X is bad"
    r"\bumurimo\s+w[ao]\s+\w+\s+ni\s+mwiza\b",     # "work of X is good"
    r"\bumurimo\s+w[ao]\s+\w+\s+ni\s+w[ao]\s+\w+\b",  # "work of X is that of Y" (comparison)

    # Common job names used in comparisons
    r"\bumuhinzi\s+ni\s+\w+\s+kuruta\b",   # farmer is ... than
    r"\bumucuruzi\s+ni\s+\w+\s+kuruta\b",  # trader is ... than
    r"\bumunyeshuri\s+ni\s+\w+\s+kuruta\b",# student is ... than
    r"\bumuganga\s+ni\s+\w+\s+kuruta\b",   # doctor is ... than
    r"\bumwarimu\s+ni\s+\w+\s+kuruta\b",   # teacher is ... than
    r"\bumusirikare\s+ni\s+\w+\s+kuruta\b",# soldier is ... than
    r"\bumukozi\s+ni\s+\w+\s+kuruta\b",    # worker is ... than

    # English job comparison phrases
    r"\b\w+\s+job\s+is\s+better\s+than\b",
    r"\b\w+\s+job\s+is\s+worse\s+than\b",
    r"\bbetter\s+job\s+than\b",
    r"\bworse\s+job\s+than\b",
    r"\bjobs?\s+(?:are|is)\s+(?:better|worse|superior|inferior)\b",
    r"\bprofession\s+(?:is|are)\s+(?:better|worse|superior|inferior)\b",

    # "farmers/doctors/teachers are better/worse than..." type phrases
    r"\babahinzi\s+ni\s+\w+\s+kuruta\b",
    r"\babaganga\s+ni\s+\w+\s+kuruta\b",
    r"\babarimu\s+ni\s+\w+\s+kuruta\b",
    r"\babacuruzi\s+ni\s+\w+\s+kuruta\b",

    # Generic "which work/job is best" ranking questions
    r"\bumurimo\s+(?:uwo|wose)\s+ni\s+mwiza\b",  # "all/any work is good" (ironic ranking)
    r"\bakazi\s+(?:keza|kabi)\s+ni\s+ak[ao]\b",
    r"\bwhich\s+(?:job|work|profession)\s+is\s+(?:the\s+)?(?:best|better|worst|worse)\b",
    r"\bwhat\s+(?:job|work)\s+is\s+(?:the\s+)?(?:best|better|worst|worse)\b",
    r"\bukuri\s+umurimo\s+mwiza\s+ni\s+uwuhe\b",  # "which is truly the best job"
    r"\bumurimo\s+mwiza\s+ni\s+uwuhe\b",
    r"\bumurimo\s+mubi\s+ni\s+uwuhe\b",
    r"\bakazi\s+keza\s+ni\s+akahe\b",
    r"\bakazi\s+kabi\s+ni\s+akahe\b",

    # "I love [group of people]" — romantic/general attraction to a gender/group class
    # Blocked because it opens door to inappropriate commentary about groups
    # NOTE: nkunda + specific family member words are SAFE (handled in _CONV_PATTERNS above)
    r"\bnkunda\s+abagore\b",      # "I love women" (as a group)
    r"\bnkunda\s+abagabo\b",      # "I love men" (as a group)
    r"\bnkunda\s+abana\s+bato\b", # "I love little children" (suspicious phrasing)
    r"\bnikundira\s+abagore\b",
    r"\bnikundira\s+abagabo\b",
    r"\bnikundira\s+abana\s+bato\b",
    r"\bundinda\s+abagore\b",
    r"\bundinda\s+abagabo\b",

    # Direct threats / intimidation
    r"\bnzakwica\b",        r"\bnzakwic\w*\b",
    r"\bnzakubica\b",
    r"\bngukomeretse\b",
    r"\bngutabaza\b",
    r"\bthreaten\w*\b",     r"\bintimidati\w*\b",
    r"\bnshaka\s+kwica\b",
    r"\bnshaka\s+gukubita\b",
    r"\bkugomba\s+kwica\b",
]

_HARMFUL_COMPILED = [re.compile(p, re.IGNORECASE) for p in _HARMFUL_PATTERNS]

FALLBACK = "Munyihanganire, nta makuru mfite kuri iyi ngingo."


def is_harmful(question: str) -> bool:
    """Fast regex-based harmful content check."""
    q_lower = question.strip().lower()
    for pat in _HARMFUL_COMPILED:
        if pat.search(q_lower):
            return True
    return False


# ============================================================
# LAYER 2: LLM moderation — context-aware
# ============================================================

_MODERATION_PROMPT = """\
Usuzuma ubutumwa bw'umuntu kugira ngo ubone niba bufite ibintu bibi.

FATA NEZA: Reba INSHINGANO y'ubutumwa, si amagambo gusa.

Subiza "HARMFUL" iyo ubutumwa:
1. Bufite ntibazo yo kwica umuntu cyangwa kwiyica
2. Bufite ntibazo yo gusambana n'umwana muto (child abuse)
3. Bufite ntibazo yo gufata umuntu ku ngufu (rape)
4. Bufite ntibazo yo guhohotera cyangwa gutera umuntu inzara
5. Bufite amagambo mabi cyangwa insult ikomeye
6. Bufite ntibazo yo gusambana n'inyamanswa cyangwa ibitungwa (bestiality)
7. Bufite ikibazo cy'ubusambane, ubusambanyi, cyangwa imibonano ibananiye
8. Bufite amagambo ajyanye n'ibitsina, imibonano, cyangwa ibya gitsina
9. Bufite ikibazo cy'amarangamutima yo guhungabanya abandi
10. Bufite amagambo ajyanye n'ubutinganyi (homosexuality), LGBT, gay, lesbian, bisexual, transgender
11. Bufite amagambo ajyanye no gukora imibonano yo mu kibuno (anal/sodomy)
12. Bufite ikibazo cyo kumenya uburyo bwo gukora ibintu by'ubutinganyi
13. Bufite amagambo yo kurwana, gukubita, cyangwa guhohotera umuntu
14. Bufite amagambo ajyanye n'intambara, intwaro, amagitero, milisi, cyangwa terrorisme
15. Bufite amagambo yo kwihora, gutsindira, inzigo, cyangwa gushakira umuntu revenge
16. Bufite inkuru zo gusiga urwango hagati y'amoko, propaganda, cyangwa gukurura urugomo
17. Bufite amagambo y'inkozi z'ikibi (inyenzi, interahamwe) cyangwa isano n'itsembabwoko
18. Bufite amagambo ajyanye n'ubwoko (Hutu, Tutsi, Twa) mu buryo bwo gutandukanya cyangwa gusiga urwango
19. Bufite ibibazo byo gusesengura icyiza cyangwa ikibi cy'ubwoko, igihugu, idini, cyangwa itsinda ry'abantu
20. Bufite amagambo yo kwerekana ko abantu b'ubwoko runaka, igihugu, cyangwa idini ari beza kuruta abandi
21. Bufite ibibazo byo gutandukanya abantu hashingiwe ku bwoko, ubukristo, ubusilamu, ubwoko bw'umuzungu cyangwa umukara
22. Bufite ikibazo cyo kugereranya imirimo cyangwa inzego z'akazi hashingiwe ku gusesengura uwurusha ubundi (umuhinzi ni mubi kuruta umuganga, akazi keza ni akahe, umurimo mwiza ni uwuhe, n'ibindi)

FATA CYANE: Ibi bikurikira ni HARMFUL ntabwo SAFE:
- Ikibazo cyose gijyanye n'inyamanswa cyangwa ibitungwa mu nzira y'ubusambane → HARMFUL
- Amagambo ajyanye n'umushyukwe cyangwa ibya gitsina → HARMFUL
- Ibibazo byose by'ubusambane cyangwa imibonano → HARMFUL
- "umutinganyi", "ubutinganyi", "gutingana" mu nzira y'ibitsina → HARMFUL
- Ibibazo byose bijyanye na LGBT, gay, lesbian mu nzira y'imibonano → HARMFUL
- "mukibuno" cyangwa "mu kibuno" mu nzira y'imibonano → HARMFUL
- Ibibazo byose bijyanye no kurwana, gukubita, cyangwa guhohotera → HARMFUL
- Amagambo y'inzigo, kwihora, cyangwa gutera umuntu ubwoba → HARMFUL
- Amagambo yo gusiga urwango hagati y'amoko cyangwa gutera urugomo → HARMFUL
- Ibibazo byose byo kugereranya imirimo/akazi nk'uwurusha ubundi → HARMFUL
- "umurimo wa X ni mwiza kuruta wa Y", "akazi keza ni akahe", "umurimo mubi ni uwuhe" → HARMFUL
- Ijambo "ubwoko", "Hutu", "Tutsi", "Twa" rikoreshwa mu nzira yo gutandukanya abantu → HARMFUL
- Ibibazo byo kugereranya ubwoko runaka n'ubundi hashingiwe ku gusesengura uwo ari mwiza → HARMFUL
- Ikibazo cyose cyo kwerekana ko abantu b'igihugu, idini, cyangwa itsinda runaka ari beza kuruta abandi → HARMFUL

INGERO ZA "SAFE":
- "ngiye gukubita umwana wanjye kuko yakosheje" → SAFE (uburere)
- "muraho" / "mwaramutse" → SAFE (gusuhuza)
- "umwana wanjye arararira" → SAFE (ubuzima)
- "nishimye" → SAFE
- "urakoze" → SAFE
- "ndananiwe" → SAFE (umunaniro)

INGERO ZA "HARMFUL":
- "nigute nakwica umuntu" → HARMFUL
- "ndashaka gukora rape" → HARMFUL
- "nasambanyije umwana muto" → HARMFUL
- "nigute umuntu yakwiyahura neza" → HARMFUL
- "ngiye guswera umwana" → HARMFUL
- "gusambana n'inyamanswa" → HARMFUL
- "kamari yarongoye ihene" → HARMFUL
- "ndumva mfite umushyukwe" → HARMFUL
- "gusambana ni byiza se" → HARMFUL
- "ibitsina byanjye" → HARMFUL
- "kamali ni umutinganyi" → HARMFUL
- "ndashaka kuba umutinganyi" → HARMFUL
- "gay ni byiza" → HARMFUL
- "lesbian nshaka" → HARMFUL
- "ubwoko bwa Tutsi ni bwiza kuruta ubwa Hutu" → HARMFUL
- "abahutu batera ingorane" → HARMFUL
- "abatutsi ni bo babica" → HARMFUL
- "abanyarwanda ni beza kuruta abarundi" → HARMFUL
- "abakristo ni beza kuruta abasilamu" → HARMFUL
- "abazungu ni beza kuruta abakara" → HARMFUL
- "ese ubwoko bwawe ni ubwoko ki" → HARMFUL
- "abantu b'ubwoko bwa X bakwiye gukurwa" → HARMFUL
- "umurimo wa muganga ni mwiza kuruta uwa muhinzi" → HARMFUL
- "umuhinzi ni mubi kuruta umuganga" → HARMFUL
- "akazi keza ni akahe" → HARMFUL
- "which job is the best" → HARMFUL
- "umurimo mwiza ni uwuhe" → HARMFUL
- "abahinzi ni bato kuruta abaganga" → HARMFUL
- "nzakwica uwo muntu" → HARMFUL
- "ndashaka kwihora" → HARMFUL
- "tuzarwane" → HARMFUL
- "inyenzi zigaruke" → HARMFUL
- "intambara ni igisubizo" → HARMFUL
- "gutsemba abantu" → HARMFUL
- "tuzabamarira" → HARMFUL

Subiza GUSA ijambo rimwe: "HARMFUL" cyangwa "SAFE".
"""


def is_harmful_llm(question: str, client: OpenAI) -> bool:
    """LLM-based context-aware harmful content check (fallback returns False on error)."""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _MODERATION_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
            max_tokens=5,
        )
        verdict = resp.choices[0].message.content.strip().upper()
        return verdict == "HARMFUL"
    except Exception:
        return False


# ============================================================
# Broad conversation detector  (original logic)
# ============================================================

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

    # Identity / capability / bio
    r"\bwowe\s+ni\s+nde\b", r"\buri\s+nde\b", r"\buri\s+iki\b",
    r"\bwho\s+are\s+you\b", r"\bwhat\s+are\s+you\b",
    r"\bwhat\s+can\s+you\b", r"\bcan\s+you\s+help\b",
    r"\bwitwa\s+nde\b",     r"\bwitwa\b",
    r"\bubumenyi\b",        r"\bbumenyi\b",
    r"\bubukura\b",         r"\bukura\s+hehe\b",
    r"\bwakozwe\b",         r"\bwakozwe\s+nande\b",
    r"\bwakozwe\s+hifashishijwe\b",
    r"\bibisubizo\b",       r"\bubikura\b",
    r"\bnde\s+wakugize\b",  r"\bwagenzwe\s+nande\b",
    r"\bwavuye\s+hehe\b",   r"\bwatangiye\s+hehe\b",
    r"\bumuntu\s+wakugize\b",
    r"\bsource\b",          r"\bdata\b",
    r"\binformation\b",     r"\btraining\b",

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

    # Love for family / specific people (safe — must NOT be blocked)
    r"\bnkunda\s+umwana\b",       r"\bnkunda\s+abana\b",
    r"\bnkunda\s+umuhungu\b",     r"\bnkunda\s+umukobwa\b",
    r"\bnkunda\s+mama\b",         r"\bnkunda\s+papa\b",
    r"\bnkunda\s+umuryango\b",    r"\bnkunda\s+inshuti\b",
    r"\bnkunda\s+umugabo\b",      r"\bnkunda\s+umugore\b",
    r"\bnkunda\s+se\b",           r"\bnkunda\s+nyina\b",
    r"\bnkunda\s+murumuna\b",     r"\bnkunda\s+mukuru\b",
    r"\bnkunda\s+igihugu\b",      r"\bnkunda\s+rwanda\b",
    r"\bnkunda\s+imana\b",
    r"\bnkunda\s+akazi\b",        r"\bnkunda\s+umurimo\b",
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


# ============================================================
# Bio / identity detector — precise matching with rich answers
# ============================================================

# Each entry: (compiled_patterns_list, answer_string)
# Checked in order — first match wins.
_BIO_QA = [
    (
        # "witwa nde" / "uri nde" / "ni nde uri" / "who are you"
        [re.compile(p, re.IGNORECASE) for p in [
            r"\bwitwa\s+nde\b", r"\buri\s+nde\b", r"\bni\s+nde\s+uri\b",
            r"\bwowe\s+ni\s+nde\b", r"\bwho\s+are\s+you\b", r"\buri\s+iki\b",
        ]],
        (
            "Nitwa Baza Itetero — inshuti yawe yo mu burere bw'abana. "
            "Ndi umufasha w'ubwenge buhangano wakoreshejwe inshuti z'abana bo mu Rwanda, "
            "kugira ngo nfashe ababyeyi no abarezi mu bibazo by'uburere, imirire, "
            "n'ubuzima bw'abana kuva kuvuka kugeza ku myaka 6."
        ),
    ),
    (
        # "ubumenyi ufite ubukura hehe" / "ubumenyi bwawe" / "ubukura hehe"
        [re.compile(p, re.IGNORECASE) for p in [
            r"\bubumenyi\s+ufite\b", r"\bubumenyi\s+bwawe\b",
            r"\bubukura\s+hehe\b",   r"\bukura\s+hehe\b",
            r"\bubumenyi\s+ubukura\b",
            r"\bni\s+ubuhe\s+bumenyi\b", r"\bubuhe\s+bumenyi\b",
        ]],
        (
            "Ubumenyi bwanjye bwakuwe mu bitabo n'inyandiko z'inzobere mu burere bw'abana, "
            "harimo amabwiriza ya WHO, UNICEF, n'inzobere zo mu Rwanda mu by'imirire, "
            "ubuzima, n'iterambere ry'abana. "
            "Nkubwira ibyo bwije kuri:\n"
            "• Imirire myiza kuva ku mwana akivuka kugeza ku myaka 6\n"
            "• Inkingo n'uburyo bwo gukurikirana ubuzima bw'umwana\n"
            "• Iterambere ry'ubwenge, ijambo, n'imyitwarire by'umwana\n"
            "• Uburere buboneye n'uburyo bwo gukemura ibibazo by'abana"
        ),
    ),
    (
        # "wakozwe hifashishijwe iki" / "wakozwe niki" / "made with what"
        [re.compile(p, re.IGNORECASE) for p in [
            r"\bwakozwe\s+hifashishijwe\b", r"\bwakozwe\s+niki\b",
            r"\bhifashishijwe\s+iki\b",      r"\btekinoloji\b",
            r"\bkoreshwa\s+iki\b",
        ]],
        (
            "Nakozwe hifashishijwe ubwenge buhangano (Artificial Intelligence). "
            "Nkoreshwa imodeli y'ururimi nkuru (Large Language Model) ifatanya n'urutabo rw'amakuru "
            "rwihariye ku burere bw'abana bo mu Rwanda (RAG — Retrieval-Augmented Generation). "
            "Ibi birantuma nsubiza ibibazo bifatiye ku makuru nyayo, si gutekereza gusa."
        ),
    ),
    (
        # "wakozwe nande" / "nde wakugize" / "who made you" / "umuntu wakugize"
        [re.compile(p, re.IGNORECASE) for p in [
            r"\bwakozwe\s+nande\b",    r"\bnde\s+wakugize\b",
            r"\bumuntu\s+wakugize\b",  r"\bwagenzwe\s+nande\b",
            r"\bwho\s+made\s+you\b",   r"\bwho\s+built\s+you\b",
            r"\bwakozwe\b",
        ]],
        (
            "Nakoze n'itsinda ry'inzobere mu Rwanda ryifashishije ubwenge buhangano "
            "no guhuza amakuru y'inzobere mu burere bw'abana. "
            "Intego yabo ni ugufasha ababyeyi n'abarezi bose mu Rwanda "
            "kubona inama z'ubumenyi ku burere bw'abana mu rurimi rwabo rw'amavuko."
        ),
    ),
    (
        # "ibisubizo utanga ubikura hehe" / "ubikura hehe" / "source yawe"
        [re.compile(p, re.IGNORECASE) for p in [
            r"\bibisubizo\s+utanga\b",  r"\bubikura\s+hehe\b",
            r"\bigisubizo\s+ubikura\b", r"\bsource\b",
            r"\bdata\s+yawe\b",         r"\bamakuru\s+yawe\b",
            r"\bavuye\s+hehe\b",        r"\bwavuye\s+hehe\b",
        ]],
        (
            "Ibisubizo byanjye bivuye mu inzego eshatu:\n"
            "1. Inyandiko z'inzobere — amabwiriza ya WHO, UNICEF, n'ubushakashatsi bw'abasomi "
            "mu by'iterambere ry'abana\n"
            "2. Amabwiriza ya leta y'u Rwanda — MINISANTE, RBC, n'uturere tw'ubuzima\n"
            "3. Ubumenyi bw'inzobere zo mu Rwanda mu burere bw'abana n'imirire\n"
            "Ibisubizo byose bifatiye ku makuru nyayo, ntabwo ari ivangura gusa."
        ),
    ),
    (
        # "ubwenge ufite ubukurahe" / "capabilities" / "what can you do"
        [re.compile(p, re.IGNORECASE) for p in [
            r"\bubwenge\s+ufite\b",    r"\bushobora\s+iki\b",
            r"\bwhat\s+can\s+you\b",   r"\bcan\s+you\s+help\b",
            r"\bnshobora\s+kukubaza\b", r"\binfasha\s+iki\b",
            r"\bukora\s+iki\b",
        ]],
        (
            "Nshobora kukugira inama kuri ibi:\n"
            "• Imirire y'umwana — gutunga, kurya, n'ibiribwa bikwiye mu myaka yose\n"
            "• Inkingo — gahunda n'akamaro kwazo\n"
            "• Iterambere ry'umwana — ijambo, gutekereza, gukina, n'imyitwarire\n"
            "• Indwara zisanzwe z'abana n'uko wazihanganira\n"
            "• Uburere buboneye — imigenzereze myiza n'uko ugira umwana indangagaciro\n"
            "Mbaza ikibazo cyangwa nyine bwira ikintu ushaka kumenya!"
        ),
    ),
]


def get_bio_response(question: str) -> str | None:
    """
    Return a specific bio/identity answer if the question matches a known pattern.
    Returns None if no bio pattern matches (caller should proceed normally).
    """
    q_lower = question.strip().lower()
    for patterns, answer in _BIO_QA:
        for pat in patterns:
            if pat.search(q_lower):
                return answer
    return None


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


# ============================================================
# LLM-powered conversational reply  (original system prompt)
# ============================================================

_SYSTEM_PROMPT = """\
Witwa "Baza itetero". Umufasha ukoresha ubwenge buhangano mu rurimi rw'ikinyarwanda ufite amakuru yuko warera umwana kuva 0 kugeza ku myaka 6 n'uburyo umubyeyi ashobora guha umwana uburere buboneye.

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

IBIKOMEZA BIRABUJIJWE — NTUKORE IBYAKURIKIRA:
• NTUVUGE ijambo ku birebana n'urukundo rw'umuntu ku itsinda ry'abantu (abagore, abagabo, abana bato, ubwoko, igihugu, idini) — subiza uti: "Nta makuru mfite kuri iyi ngingo."
• NTUGERERANYA ubwoko, igihugu, idini, imirimo, cyangwa itsinda ry'abantu nk'uwurusha ubundi — subiza uti: "Nta makuru mfite kuri iyi ngingo."
• NTUVUGE ko umuntu cyangwa itsinda ry'abantu ari beza/babi kuruta abandi.
• NTUVUGE ko umurimo runaka ari mwiza/mubi kuruta undi.

NTUVUGE KO URI AI.
"""


def get_smalltalk_response(question: str, client: OpenAI) -> str:
    """
    Generate a conversational reply.

    Processing order:
      1. Regex harmful check  →  return FALLBACK immediately
      2. LLM moderation check →  return FALLBACK immediately
      3. LLM-powered friendly reply (original behaviour)
      4. Canned fallback if the API call fails
    """
    # --- Harmful content gate ---
    if is_harmful(question):
        return FALLBACK

    if is_harmful_llm(question, client):
        return FALLBACK

    # --- Bio / identity check (precise, no LLM needed) ---
    bio_reply = get_bio_response(question)
    if bio_reply:
        return bio_reply

    # --- Normal conversational reply ---
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


# ============================================================
# Canned fallback — no API needed  (original logic)
# ============================================================

def _canned_reply(question: str) -> str:
    q = question.lower()

    # Love for a specific family member / country / job — safe and positive
    _FAMILY_LOVE_WORDS = [
        "nkunda umwana", "nkunda abana", "nkunda umuhungu", "nkunda umukobwa",
        "nkunda mama", "nkunda papa", "nkunda se", "nkunda nyina",
        "nkunda umuryango", "nkunda inshuti", "nkunda murumuna", "nkunda mukuru",
        "nkunda umugabo", "nkunda umugore",
        "nkunda igihugu", "nkunda rwanda", "nkunda imana",
        "nkunda akazi", "nkunda umurimo",
    ]
    if any(w in q for w in _FAMILY_LOVE_WORDS):
        return "Ni byiza cyane gukunda abantu bakuzengurutse! Urukundo n'ubwitange ni inkingi y'umuryango mwiza."


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

    # Identity / bio
    if any(w in q for w in ["nde", "iki", "who are you", "witwa", "wakozwe", "ubumenyi",
                             "ubukura", "source", "ibisubizo", "ubwenge"]):
        bio = get_bio_response(q)
        if bio:
            return bio
        return (
            "Nitwa Baza Itetero — inshuti yawe mu burere bw'abana. "
            "Nfasha ku bibazo by'uburere, imirire, ubuzima, no gukura kw'abana "
            "kuva kuvuka kugeza ku myaka 6."
        )

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