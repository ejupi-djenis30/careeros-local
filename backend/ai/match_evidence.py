from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from backend.ai.retrieval import EvidenceDocument
from backend.services.search.prompt_compaction import compact_prompt_text
from backend.services.search.query_contracts import sanitize_prompt_text
from backend.services.utils import clean_html_tags

MATCH_EVIDENCE_CATALOG_VERSION = "8"
MATCH_EVIDENCE_DESCRIPTION_CHARS = 6_000
_FRAGMENT_SPLIT = re.compile(r"(?:\n+|(?<=[.!?;])\s+)")
_DIMENSIONS = (
    "skill",
    "experience",
    "intent",
    "language",
    "location",
    "transferability",
    "qualification",
)
_MAX_PROMPT_QUOTES_PER_DIMENSION = 4
_MAX_QUOTE_CHARS = 240
_CANDIDATE_EVIDENCE_CHARS = 2_700
_JOB_EVIDENCE_CHARS = 2_700
_DIMENSION_PATTERNS = {
    "experience": re.compile(
        r"\b(?:experience|years?|senior|junior|lead|erfahrung|berufserfahrung|jahre?n?|"
        r"expérience|ans?|années?|esperienza|anni?|responsabile)\b",
        re.IGNORECASE,
    ),
    "language": re.compile(
        r"\b(?:language|sprache|langue|lingua|english|englisch|anglais|inglese|german|"
        r"deutsch|allemand|tedesco|french|französisch|franzoesisch|français|francais|"
        r"francese|italian|italienisch|italien|italiano|native|fluent|fließend|fliessend|"
        r"courant|courante|fluente|muttersprachlich|maternelle|madrelingua|"
        r"a1|a2|b1|b2|c1|c2)\b",
        re.IGNORECASE,
    ),
    "location": re.compile(
        r"\b(?:remote|hybrid|on-site|onsite|location|relocation|standort|arbeitsort|"
        r"vor\s+ort|umzug|télétravail|teletravail|hybride|sur\s+site|localisation|"
        r"déménagement|demenagement|remoto|ibrido|in\s+presenza|sede|località|localita|"
        r"trasferimento)\b|\b(?:based\s+in|ansässig\s+in|basé[e]?\s+à|con\s+sede\s+a)\b",
        re.IGNORECASE,
    ),
    "qualification": re.compile(
        r"\b(?:degree|bachelor(?:'s)?|phd|doctorate|diploma|education|qualification|"
        r"apprenticeship|master|msc|m\.sc\.|abschluss|studium|ausbildung|masterabschluss|"
        r"bachelorabschluss|doktorat|diplôme|diplome|licence|formation|doctorat|"
        r"apprentissage|laurea|magistrale|triennale|dottorato|istruzione|"
        r"qualifica|apprendistato)\b|\bmaster(?:'s)?\s+(?:degree|diploma|in|of)\b",
        re.IGNORECASE,
    ),
}
_REQUIREMENT_STATUS_PATTERNS = (
    (
        "explicit_not_required",
        re.compile(
            r"\b(?:not\s+(?:required|mandatory|needed|necessary|essential|"
            r"(?:a\s+)?requirement|(?:a\s+)?must)|"
            r"no\s+requirement\s+for|"
            r"no\s+[^.;]{0,80}\s+(?:required|needed|necessary|mandatory|essential)|optional|"
            r"isn['’]t\s+required|(?:doesn['’]t|does\s+not)\s+(?:need|require)|"
            r"(?:don['’]t|doesn['’]t|do\s+not|does\s+not)\s+have\s+to|"
            r"needn['’]t|not\s+needed|not\s+a\s+must|"
            r"nicht\b[^.;]{0,30}\b(?:erforderlich|notwendig|benötigt|benoetigt|zwingend)|"
            r"kein(?:e|en)?\s+(?:muss|voraussetzung|pflicht)|muss\s+nicht|optional|"
            r"non\s+requis(?:e|es|s)?|"
            r"pas\s+(?:requis(?:e|es|s)?|nécessaire|necessaire|obligatoire)|"
            r"facultati(?:f|ve)|optionnel(?:le)?|"
            r"non\b[^.;]{0,20}\b(?:richiest[oaie]|necessari[oaie]|obbligatori[oaie])|"
            r"facoltativ[oaie]|opzional[eaio])\b",
            re.IGNORECASE,
        ),
    ),
    (
        "exclusion",
        re.compile(
            r"\b(?:do(?:es)?\s+not\s+(?:know|have|use)|must\s+not\s+(?:know|have|use)|"
            r"must\s+not\s+be\s+(?:used|utilized|known|permitted)|"
            r"cannot\s+(?:know|have|use)|"
            r"(?:don['’]t|doesn['’]t)\s+(?:know|have|use)|"
            r"(?:haven['’]t|hasn['’]t)\s+(?:used|worked\s+with)|"
            r"(?:have|has)\s+not\s+(?:used|worked\s+with)|"
            r"lacks?(?:\s+experience)?\s+(?:with|in)?|"
            r"no\s+experience\s+(?:with|in)|never\s+(?:used|worked\s+with)|"
            r"without\s+(?!(?:(?:direct|close|constant)\s+)?(?:supervision|assistance|"
            r"restriction|relocation)\b)(?:any\s+)?(?:experience\s+(?:with|in)\s+)?"
            r"[\w+#.-]+|"
            r"prohibited|forbidden|not\s+permitted|"
            r"darf\b[^.;]{0,60}\bnicht|"
            r"(?:kenne|kennt|beherrsche|beherrscht)\b[^.;]{0,60}\bnicht|"
            r"keine?\s+erfahrung\s+mit|nie\s+(?:verwendet|benutzt)|"
            r"(?:habe|hat|haben)\b[^.;]{0,30}\b(?:nie|niemals)\b[^.;]{0,30}"
            r"(?:verwendet|benutzt|gearbeitet)|"
            r"ohne\s+(?!(?:(?:direkte|direkter|direkten|ständige|staendige)\s+)?"
            r"(?:aufsicht|unterstützung|unterstuetzung|hilfe|umzug)\b)[\w+#.-]+|"
            r"(?:verwendet|benutzt)\s+kein(?:e|en)?|verboten|ausgeschlossen|"
            r"(?:ne|n['’])\b[^.;]{0,60}\b(?:connais|connaît|connait|maîtrise|"
            r"maitrise|utilise)\b[^.;]{0,30}\bpas\b(?!\s+seulement\b)|"
            r"(?:ne|n['’])\b[^.;]{0,40}\b(?:doit|doivent)\b[^.;]{0,30}\b"
            r"pas\b(?!\s+seulement\b)|"
            r"aucune?\s+expérience\s+avec|jamais\s+utilisé|"
            r"sans\s+(?!(?:(?:supervision|assistance|aide|déménagement|demenagement))\b)"
            r"[\w+#.-]+|"
            r"interdit|exclu|"
            r"non\s+(?:conosco|conosce|abbiamo|ho|uso|usa|utilizzo|utilizza)|"
            r"non\b(?!\s+solo\b)[^.;]{0,30}\b(?:deve|devono)\b[^.;]{0,40}\b"
            r"(?:usare|utilizzare|essere\s+(?:usat|utilizzat)\w*)|"
            r"nessuna?\s+esperienza\s+con|mai\s+usat[oa]|"
            r"senza\s+(?!(?:supervisione|assistenza|trasferimento)\b)[\w+#.-]+|"
            r"vietat[oaie]|esclus[oaie]|"
            r"no\s+(?!explicit\b|[^.;]{0,80}\b(?:required|needed)\b)[\w+#.-]+)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "required",
        re.compile(
            r"\b(?:required|requires?|mandatory|must\s+(?:have|know|use|be)|"
            r"must[ -]have|is\s+a\s+must|essential|requirements?|"
            r"need(?:ed|s)?|minimum|at\s+least|"
            r"erforderlich|vorausgesetzt|pflicht|zwingend|notwendig|benötigt|benoetigt|"
            r"muss|müssen|muessen|mindestens|"
            r"requis(?:e|es|s)?|exigé(?:e|es|s)?|obligatoire|nécessaire|necessaire|"
            r"doit|doivent|devez|minimum|au\s+moins|"
            r"richiest[oaie]|obbligatori[oaie]|necessari[oaie]|deve|devono|devi|"
            r"minimo|almeno)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "preferred",
        re.compile(
            r"\b(?:preferred|desirable|nice[ -]to[ -]have|a\s+plus|"
            r"bevorzugt|wünschenswert|wuenschenswert|von\s+vorteil|idealerweise|"
            r"préféré(?:e)?|prefere(?:e)?|souhaité(?:e)?|un\s+plus|idéalement|idealement|"
            r"preferit[oa]|preferibile|gradit[oa]|desiderabile|un\s+plus|idealmente)\b",
            re.IGNORECASE,
        ),
    ),
)
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    "ein": 1,
    "eins": 1,
    "eine": 1,
    "zwei": 2,
    "drei": 3,
    "vier": 4,
    "fünf": 5,
    "fuenf": 5,
    "sechs": 6,
    "sieben": 7,
    "acht": 8,
    "neun": 9,
    "zehn": 10,
    "un": 1,
    "une": 1,
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
    "uno": 1,
    "una": 1,
    "due": 2,
    "tre": 3,
    "quattro": 4,
    "cinque": 5,
    "sei": 6,
    "sette": 7,
    "otto": 8,
    "nove": 9,
    "dieci": 10,
}
_YEARS_PATTERN = re.compile(
    r"\b(?P<years>\d{1,2}|"
    + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
    + r")\s*\+?\s*(?:years?|yrs?|jahre?n?|ans?|années?|ann(?:o|i))\b",
    re.IGNORECASE,
)
_LANGUAGE_ALIASES = {
    "english": "english",
    "englisch": "english",
    "anglais": "english",
    "inglese": "english",
    "german": "german",
    "deutsch": "german",
    "allemand": "german",
    "tedesco": "german",
    "french": "french",
    "französisch": "french",
    "franzoesisch": "french",
    "français": "french",
    "francais": "french",
    "francese": "french",
    "italian": "italian",
    "italienisch": "italian",
    "italien": "italian",
    "italiano": "italian",
    "spanish": "spanish",
    "spanisch": "spanish",
    "espagnol": "spanish",
    "spagnolo": "spanish",
}
_CEFR_RANK = {
    "a1": 1,
    "a2": 2,
    "b1": 3,
    "b2": 4,
    "c1": 5,
    "fluent": 5,
    "fließend": 5,
    "fliessend": 5,
    "courant": 5,
    "courante": 5,
    "fluente": 5,
    "c2": 6,
    "native": 7,
    "muttersprachlich": 7,
    "langue maternelle": 7,
    "natif": 7,
    "madrelingua": 7,
}
_QUALIFICATION_PATTERNS = (
    (
        5,
        re.compile(r"\b(?:phd|doctorate|doctoral|doktorat|doctorat|dottorato)\b", re.IGNORECASE),
    ),
    (
        4,
        re.compile(
            r"\b(?:master(?:'s)?|msc|m\.sc\.|masterabschluss|maîtrise|maitrise|"
            r"laurea\s+(?:magistrale|specialistica))\b",
            re.IGNORECASE,
        ),
    ),
    (
        3,
        re.compile(
            r"\b(?:bachelor(?:'s)?|bsc|b\.sc\.|bachelorabschluss|licence|"
            r"laurea\s+triennale)\b",
            re.IGNORECASE,
        ),
    ),
    (
        2,
        re.compile(r"\b(?:diploma|diplom|diplôme|diplome|associate(?:'s)?)\b", re.IGNORECASE),
    ),
    (
        1,
        re.compile(
            r"\b(?:apprenticeship|certificate|ausbildung|zertifikat|apprentissage|"
            r"certificat|apprendistato|certificato)\b",
            re.IGNORECASE,
        ),
    ),
)
_SKILL_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "backend",
    "bachelor",
    "be",
    "been",
    "candidate",
    "doctoral",
    "doctorate",
    "degree",
    "diploma",
    "delivery",
    "do",
    "does",
    "engineer",
    "evidence",
    "experience",
    "explicit",
    "for",
    "frontend",
    "have",
    "in",
    "is",
    "know",
    "language",
    "least",
    "master",
    "minimum",
    "must",
    "need",
    "needs",
    "no",
    "not",
    "of",
    "or",
    "preferred",
    "phd",
    "prohibited",
    "required",
    "requirement",
    "requires",
    "role",
    "senior",
    "service",
    "services",
    "skill",
    "skills",
    "the",
    "to",
    "transferability",
    "use",
    "uses",
    "using",
    "with",
    "years",
}
_SKILL_STOPWORDS.update(
    {
        # Requirement scaffolding and English contractions.
        "advanced",
        "any",
        "candidates",
        "command",
        "demonstrated",
        "essential",
        "excellent",
        "expertise",
        "familiarity",
        "good",
        "knowledge",
        "mandatory",
        "optional",
        "proficiency",
        "proficient",
        "proven",
        "requirements",
        "solid",
        "strong",
        "without",
        "worked",
        "working",
        "don",
        "doesn",
        "haven",
        "hasn",
        "isn",
        "needn",
        "either",
        # German grammar, polarity and typed-requirement vocabulary.
        "aber",
        "abschluss",
        "als",
        "ausbildung",
        "benoetigt",
        "benötigt",
        "berufserfahrung",
        "bachelorabschluss",
        "bevorzugt",
        "die",
        "ein",
        "eine",
        "einen",
        "einer",
        "entweder",
        "erfahrung",
        "erforderlich",
        "ist",
        "jahre",
        "jahren",
        "kein",
        "keine",
        "mindestens",
        "masterabschluss",
        "muss",
        "müssen",
        "muessen",
        "nicht",
        "notwendig",
        "oder",
        "pflicht",
        "sind",
        "und",
        "vorausgesetzt",
        "wünschenswert",
        "wuenschenswert",
        "zwingend",
        "doktorat",
        "studium",
        "zertifikat",
        # French grammar, polarity and typed-requirement vocabulary.
        "ans",
        "années",
        "annees",
        "au",
        "avec",
        "dans",
        "de",
        "des",
        "diplôme",
        "diplome",
        "doctorat",
        "doit",
        "expérience",
        "experience",
        "est",
        "exigé",
        "exige",
        "facultatif",
        "facultative",
        "formation",
        "la",
        "le",
        "les",
        "licence",
        "minimum",
        "nécessaire",
        "necessaire",
        "non",
        "obligatoire",
        "ou",
        "pas",
        "préféré",
        "prefere",
        "requis",
        "requise",
        "requises",
        "soit",
        "souhaité",
        "souhaite",
        "apprentissage",
        "certificat",
        # Italian grammar, polarity and typed-requirement vocabulary.
        "almeno",
        "anni",
        "con",
        "deve",
        "di",
        "esperienza",
        "dottorato",
        "facoltativo",
        "facoltativa",
        "gradito",
        "gradita",
        "laurea",
        "magistrale",
        "minimo",
        "necessario",
        "necessaria",
        "necessari",
        "necessarie",
        "non",
        "obbligatorio",
        "obbligatoria",
        "obbligatori",
        "obbligatorie",
        "opzionale",
        "oppure",
        "preferibile",
        "preferito",
        "preferita",
        "richiesto",
        "richiesta",
        "richiesti",
        "richieste",
        "sono",
        "triennale",
        "apprendistato",
        "certificato",
        "istruzione",
        "qualifica",
    }
)
_SKILL_STOPWORDS.update(
    {
        # Natural-language requirement scaffolding and contractions.
        "ability",
        "aren",
        "assistance",
        "before",
        "cannot",
        "close",
        "constant",
        "currently",
        "daily",
        "didn",
        "direct",
        "exposure",
        "hadn",
        "hands-on",
        "necessary",
        "needed",
        "now",
        "plus",
        "practical",
        "relocation",
        "restriction",
        "roles",
        "supervision",
        "today",
        "understanding",
        "used",
        "wasn",
        "weren",
        # German scaffolding and bounded-negation verbs.
        "bekannt",
        "benutzt",
        "benutzen",
        "beherrschung",
        "aufsicht",
        "darf",
        "direkte",
        "direkten",
        "direkter",
        "direktes",
        "fundiert",
        "fundierte",
        "fundierten",
        "fundierter",
        "fundiertes",
        "gute",
        "guten",
        "guter",
        "gutes",
        "habe",
        "haben",
        "hat",
        "kenntnis",
        "kenntnisse",
        "nie",
        "niemals",
        "ohne",
        "praktisch",
        "praktische",
        "praktischen",
        "praktischer",
        "praktisches",
        "sein",
        "umgang",
        "verwendet",
        "verwenden",
        "voraussetzung",
        "werden",
        # French scaffolding and bounded-negation verbs.
        "bon",
        "bonne",
        "bonnes",
        "candidat",
        "candidats",
        "connaissance",
        "connaissances",
        "connaître",
        "connaitre",
        "directe",
        "directes",
        "doivent",
        "être",
        "etre",
        "excellente",
        "excellentes",
        "je",
        "maîtrise",
        "maitrise",
        "moins",
        "ne",
        "pratique",
        "pratiques",
        "sans",
        "seulement",
        "solide",
        "solides",
        "sont",
        "supervision",
        "utilise",
        "utilisé",
        "utilisee",
        "utilisée",
        "utiliser",
        # Italian scaffolding and bounded-negation verbs.
        "abbiamo",
        "anno",
        "buon",
        "buona",
        "buono",
        "candidato",
        "candidati",
        "conoscenza",
        "conoscenze",
        "conoscere",
        "devono",
        "diretta",
        "dirette",
        "diretti",
        "diretto",
        "essere",
        "ha",
        "ho",
        "il",
        "ottima",
        "ottimo",
        "pratica",
        "pratiche",
        "pratici",
        "pratico",
        "senza",
        "solo",
        "solida",
        "solido",
        "supervisione",
        "usare",
        "usata",
        "usate",
        "usati",
        "usato",
        "utilizzare",
        "utilizzata",
        "utilizzate",
        "utilizzati",
        "utilizzato",
    }
)
_SKILL_STOPWORDS.update(_LANGUAGE_ALIASES)
_SKILL_STOPWORDS.update(_CEFR_RANK)
_SKILL_STOPWORDS.update(_NUMBER_WORDS)
_SKILL_STOPWORDS.update(word for phrase in _CEFR_RANK for word in phrase.split())

_LANGUAGE_ALIAS_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(re.escape(alias) for alias in sorted(_LANGUAGE_ALIASES, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)
_LANGUAGE_LEVEL_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(re.escape(level) for level in sorted(_CEFR_RANK, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)
_ConnectorKind = Literal[
    "start",
    "list",
    "additive",
    "adversative",
    "alternative",
    "scoped_absence",
]
_MarkerDirection = Literal["none", "forward", "backward", "both", "local"]


@dataclass(slots=True)
class _ClauseSegment:
    text: str
    connector: _ConnectorKind
    connector_text: str = ""
    explicit_status: str | None = None
    inherited_status: str | None = None
    marker_direction: _MarkerDirection = "none"
    marker_start: int | None = None
    marker_end: int | None = None
    absence_scope: bool = False

    @property
    def status(self) -> str:
        if self.absence_scope:
            return "exclusion"
        return self.explicit_status or self.inherited_status or "present"


_STRUCTURAL_CONNECTOR_PATTERN = re.compile(
    r"(?P<additive_correlative>,?\s*\b(?:but\s+also|sondern\s+auch|"
    r"mais\s+aussi|ma\s+anche)\b)|"
    r"(?P<alternative>,?\s*\b(?:or|oder|ou|oppure|o)\b)|"
    r"(?P<scoped_absence>\b(?:without|ohne|sans|senza)\b)|"
    r"(?P<adversative>,?\s*\b(?:but|whereas|while|aber|jedoch|während|"
    r"mais|tandis\s+que|ma|però|pero|mentre)\b|;)|"
    r"(?P<additive>\b(?:and|plus|und|et|e)\b)|"
    r"(?P<list>[,/])",
    re.IGNORECASE,
)
_FORWARD_MODAL_MARKER = re.compile(
    r"^(?:must\s+(?:have|know|use)|must-have|"
    r"muss|müssen|muessen|doit|doivent|devez|deve|devono|devi)$",
    re.IGNORECASE,
)
_PASSIVE_MODAL_MARKER = re.compile(r"^must\s+be$", re.IGNORECASE)
_MODAL_ACTION_WORD_PATTERN = re.compile(
    r"\b(?:know|known|use|used|have|"
    r"kenne|kennt|kennen|beherrsche|beherrscht|beherrschen|"
    r"verwende|verwendet|verwenden|benutze|benutzt|benutzen|nutze|nutzt|nutzen|"
    r"connais|connaît|connait|connaître|connaitre|"
    r"maîtrise|maitrise|maîtriser|maitriser|utilise|utiliser|"
    r"conosco|conosce|conoscere|padroneggiare|"
    r"uso|usa|usare|utilizzo|utilizza|utilizzare)\b",
    re.IGNORECASE,
)
_CLAUSE_GRAMMAR_PRONOUN_PATTERN = re.compile(
    r"\b(?:ich|wir|er|sie|es|das|je|nous|il|elle|on|io|lo|la|li|le)\b",
    re.IGNORECASE,
)
_REASSERTION_GRAMMARS = (
    (
        re.compile(
            r"\b(?:now|currently|today)\b[^.;]{0,60}\b"
            r"(?:use|using|work(?:ing)?\s+with|know|have)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:now|currently|today)\b[^.;]{0,40}\b"
            r"(?:use|using|work(?:ing)?\s+with|know|have)\s+(?:it|them)\b",
            re.IGNORECASE,
        ),
    ),
    (
        re.compile(
            r"\b(?:jetzt|derzeit|heute|inzwischen)\b[^.;]{0,60}\b"
            r"(?:verwende|verwenden|benutze|benutzen|nutze|nutzen|kenne|kennen)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:jetzt|derzeit|heute|inzwischen)\b[^.;]{0,60}\b"
            r"(?:verwende|verwenden|benutze|benutzen|nutze|nutzen|kenne|kennen)"
            r"\b[^.;]{0,25}\b(?:es|sie|das)\b",
            re.IGNORECASE,
        ),
    ),
    (
        re.compile(
            r"\b(?:maintenant|actuellement|aujourd['’]hui)\b[^.;]{0,60}\b"
            r"(?:utilise|utiliser|travaille|connais|maîtrise|maitrise)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:maintenant|actuellement|aujourd['’]hui)\b[^.;]{0,40}"
            r"(?:l['’]|le|la|les)\s*"
            r"(?:utilise|utiliser|connais|maîtrise|maitrise)\b",
            re.IGNORECASE,
        ),
    ),
    (
        re.compile(
            r"\b(?:ora|adesso|attualmente|oggi)\b[^.;]{0,60}\b"
            r"(?:uso|usa|usare|utilizzo|utilizza|conosco|conosce)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:ora|adesso|attualmente|oggi)\b[^.;]{0,40}\b"
            r"(?:lo|la|li|le)\s+"
            r"(?:uso|usa|usare|utilizzo|utilizza|conosco|conosce)\b",
            re.IGNORECASE,
        ),
    ),
)
_STRUCTURED_EXCLUSION_GRAMMARS = (
    re.compile(
        r"\b(?:kenne|kennt|verwende|verwendet|benutze|benutzt|nutze|nutzt|"
        r"beherrsche|beherrscht)\b[^.;]{0,60}\bnicht\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:ne|n['’])[^.;]{0,60}\b"
        r"(?:connais|connaît|connait|utilise|maîtrise|maitrise)\b"
        r"[^.;]{0,30}\bpas\b(?!\s+seulement\b)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bnon\s+(?:conosco|conosce|uso|usa|utilizzo|utilizza)\b",
        re.IGNORECASE,
    ),
)
_CLASSIFICATION_CONTRACTIONS = (
    (re.compile(r"\bcan['’]t\b", re.IGNORECASE), "cannot"),
    (re.compile(r"\bwon['’]t\b", re.IGNORECASE), "will not"),
    (re.compile(r"\bisn['’]t\b", re.IGNORECASE), "is not"),
    (re.compile(r"\baren['’]t\b", re.IGNORECASE), "are not"),
    (re.compile(r"\bwasn['’]t\b", re.IGNORECASE), "was not"),
    (re.compile(r"\bweren['’]t\b", re.IGNORECASE), "were not"),
    (re.compile(r"\bdon['’]t\b", re.IGNORECASE), "do not"),
    (re.compile(r"\bdoesn['’]t\b", re.IGNORECASE), "does not"),
    (re.compile(r"\bdidn['’]t\b", re.IGNORECASE), "did not"),
    (re.compile(r"\bhaven['’]t\b", re.IGNORECASE), "have not"),
    (re.compile(r"\bhasn['’]t\b", re.IGNORECASE), "has not"),
    (re.compile(r"\bhadn['’]t\b", re.IGNORECASE), "had not"),
    (re.compile(r"\bmustn['’]t\b", re.IGNORECASE), "must not"),
    (re.compile(r"\bneedn['’]t\b", re.IGNORECASE), "need not"),
)


def _classification_text(value: str) -> str:
    normalized = value.replace("’", "'").replace("‘", "'")
    for pattern, replacement in _CLASSIFICATION_CONTRACTIONS:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def _connector_kind(match: re.Match[str]) -> _ConnectorKind:
    if match.lastgroup == "additive_correlative":
        return "additive"
    if match.lastgroup == "alternative":
        return "alternative"
    if match.lastgroup == "scoped_absence":
        return "scoped_absence"
    if match.lastgroup == "adversative":
        return "adversative"
    if match.lastgroup == "additive":
        return "additive"
    return "list"


def _raw_clause_segments(sentence: str) -> list[_ClauseSegment]:
    segments: list[_ClauseSegment] = []
    cursor = 0
    pending_connector: _ConnectorKind = "start"
    pending_text = ""
    for match in _STRUCTURAL_CONNECTOR_PATTERN.finditer(sentence):
        chunk = sentence[cursor : match.start()].strip(" ,-;/")
        if chunk:
            segments.append(
                _ClauseSegment(
                    text=chunk,
                    connector=pending_connector,
                    connector_text=pending_text,
                )
            )
        pending_connector = _connector_kind(match)
        pending_text = match.group(0).strip(" ,;/")
        cursor = match.end()
    tail = sentence[cursor:].strip(" ,-;/")
    if tail:
        segments.append(
            _ClauseSegment(
                text=tail,
                connector=pending_connector,
                connector_text=pending_text,
            )
        )
    return segments


def _has_requirement_subject(value: str) -> bool:
    return bool(
        _skill_terms(value)
        or _LANGUAGE_ALIAS_PATTERN.search(value)
        or _YEARS_PATTERN.search(value)
        or any(pattern.search(value) for _rank, pattern in _QUALIFICATION_PATTERNS)
    )


def _marker_direction(
    value: str,
    status: str,
    match: re.Match[str],
) -> _MarkerDirection:
    if status == "exclusion":
        return "local"
    marker = match.group(0)
    if status == "required" and _PASSIVE_MODAL_MARKER.fullmatch(marker):
        return "both"
    if status == "required" and _FORWARD_MODAL_MARKER.fullmatch(marker):
        return "forward"
    left_has_subject = _has_requirement_subject(value[: match.start()])
    right_has_subject = _has_requirement_subject(value[match.end() :])
    if right_has_subject and not left_has_subject:
        return "forward"
    if left_has_subject and not right_has_subject:
        return "backward"
    if match.start() <= len(value) - len(value.lstrip()) + 1 and right_has_subject:
        return "forward"
    return "local"


def _annotate_explicit_status(segment: _ClauseSegment) -> None:
    normalized = _classification_text(segment.text)
    structured_exclusion = next(
        (
            match
            for pattern in _STRUCTURED_EXCLUSION_GRAMMARS
            if (match := pattern.search(normalized)) is not None
        ),
        None,
    )
    if structured_exclusion is not None:
        segment.explicit_status = "exclusion"
        segment.marker_direction = "local"
        segment.marker_start = structured_exclusion.start()
        segment.marker_end = structured_exclusion.end()
        return
    for status, pattern in _REQUIREMENT_STATUS_PATTERNS:
        match = pattern.search(normalized)
        if match is None:
            continue
        segment.explicit_status = status
        segment.marker_direction = _marker_direction(normalized, status, match)
        segment.marker_start = match.start()
        segment.marker_end = match.end()
        return


def _classify_clause_commas(segments: list[_ClauseSegment]) -> None:
    for index in range(1, len(segments)):
        segment = segments[index]
        if segment.connector != "list":
            continue
        previous = segments[index - 1]
        if previous.explicit_status is not None and previous.marker_direction in {
            "backward",
            "local",
        }:
            segment.connector = "adversative"


def _apply_absence_scope(segments: list[_ClauseSegment]) -> None:
    absence_active = False
    for segment in segments:
        if segment.connector in {"start", "adversative"}:
            absence_active = False
        if segment.connector == "scoped_absence":
            absence_active = True
        segment.absence_scope = absence_active


def _apply_status_propagation(segments: list[_ClauseSegment]) -> None:
    group_start = 0
    for group_end in [
        *(
            index
            for index, segment in enumerate(segments)
            if index > 0 and segment.connector == "adversative"
        ),
        len(segments),
    ]:
        group = segments[group_start:group_end]
        explicit_statuses = [
            segment.explicit_status for segment in group if segment.explicit_status is not None
        ]
        for segment in group:
            if segment.explicit_status is not None or not explicit_statuses:
                continue
            unique_statuses = set(explicit_statuses)
            if len(unique_statuses) == 1:
                segment.inherited_status = explicit_statuses[0]
        group_start = group_end


def _structured_clauses(value: str) -> list[_ClauseSegment]:
    clauses: list[_ClauseSegment] = []
    for sentence in _FRAGMENT_SPLIT.split(value):
        normalized = " ".join(sentence.split())
        if not normalized:
            continue
        sentence_segments = _raw_clause_segments(normalized)
        for segment in sentence_segments:
            _annotate_explicit_status(segment)
        _classify_clause_commas(sentence_segments)
        _apply_absence_scope(sentence_segments)
        _apply_status_propagation(sentence_segments)
        clauses.extend(sentence_segments)
    return clauses


def _positive_reassertion(value: str) -> bool:
    normalized = _classification_text(value)
    return any(positive.search(normalized) for positive, _anaphoric in _REASSERTION_GRAMMARS)


def _anaphoric_reassertion(value: str) -> bool:
    normalized = _classification_text(value)
    return any(anaphoric.search(normalized) for _positive, anaphoric in _REASSERTION_GRAMMARS)


def _segment_fragment(segment: _ClauseSegment) -> str:
    fragment = segment.text
    if segment.connector == "scoped_absence" and segment.connector_text:
        fragment = f"{segment.connector_text} {fragment}"
    if segment.absence_scope and _skill_terms(segment.text):
        fragment = f"{fragment} prohibited"
    elif segment.explicit_status is None and segment.inherited_status is not None:
        marker = {
            "explicit_not_required": "optional",
            "exclusion": "prohibited",
            "preferred": "preferred",
            "required": "required",
        }.get(segment.inherited_status)
        if marker is not None:
            fragment = f"{fragment} {marker}"
    return fragment.strip()


def _matching_fragments(text: str, dimension: str) -> str:
    pattern = _DIMENSION_PATTERNS[dimension]
    return "\n".join(
        fragment
        for sentence in _FRAGMENT_SPLIT.split(text)
        for fragment in _all_fragments(sentence)
        if pattern.search(fragment)
    )


def _source_fingerprint(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _quote_hash(dimension: str, text: str) -> str:
    return hashlib.sha256(f"{dimension}\0{text}".encode("utf-8")).hexdigest()


def _catalog_fingerprint(
    quotes: Mapping[str, Mapping[str, Any]],
    *,
    requirement_summary: Mapping[str, Any],
    coverage_complete: Mapping[str, bool],
) -> str:
    return _source_fingerprint(
        {
            "catalog_version": MATCH_EVIDENCE_CATALOG_VERSION,
            "quotes": {
                quote_id: {
                    "dimension": quote.get("dimension"),
                    "has_positive_evidence": quote.get("has_positive_evidence"),
                    "requirement_status": quote.get("requirement_status"),
                    "text_hash": quote.get("text_hash"),
                }
                for quote_id, quote in sorted(quotes.items())
            },
            "coverage_complete": dict(sorted(coverage_complete.items())),
            "requirement_summary": requirement_summary,
        }
    )


def _explicit_requirement_status(value: str) -> str | None:
    value = _classification_text(value)
    for status, pattern in _REQUIREMENT_STATUS_PATTERNS:
        if pattern.search(value):
            return status
    return None


def _is_missing_evidence(value: str) -> bool:
    normalized = " ".join(value.casefold().split())
    return (
        not normalized
        or normalized.startswith("no explicit ")
        or "no description provided" in normalized
        or normalized.endswith(" is empty.")
    )


def _requirement_status(value: str) -> str:
    # Synthetic catalog fallbacks deliberately contain words such as
    # "requirement". They must remain unknown rather than being promoted to a
    # real requirement by the marker parser below.
    if _is_missing_evidence(value):
        return "unknown"
    explicit = _explicit_requirement_status(value)
    if explicit is not None:
        return explicit
    return "present"


def _all_fragments(value: str) -> list[str]:
    """Project structured clauses into independently classifiable quote text."""
    return [_segment_fragment(segment) for segment in _structured_clauses(value)]


def _years(value: str) -> list[int]:
    result: list[int] = []
    for match in _YEARS_PATTERN.finditer(value):
        raw = match.group("years").casefold()
        result.append(int(raw) if raw.isdigit() else _NUMBER_WORDS[raw])
    return result


def _languages(value: str) -> dict[str, int]:
    normalized = value.casefold()
    level_pattern = "|".join(
        re.escape(level) for level in sorted(_CEFR_RANK, key=len, reverse=True)
    )
    level_matches = list(re.finditer(rf"\b(?:{level_pattern})\b", normalized, re.IGNORECASE))
    result: dict[str, int] = {}
    for alias, canonical in _LANGUAGE_ALIASES.items():
        for language_match in re.finditer(rf"\b{re.escape(alias)}\b", normalized):
            nearest = min(
                level_matches,
                key=lambda level: min(
                    abs(level.start() - language_match.end()),
                    abs(language_match.start() - level.end()),
                ),
                default=None,
            )
            rank = _CEFR_RANK[nearest.group(0).casefold()] if nearest is not None else 0
            result[canonical] = max(result.get(canonical, 0), rank)
    return result


def _qualification_rank(value: str) -> int:
    return max(
        (rank for rank, pattern in _QUALIFICATION_PATTERNS if pattern.search(value)), default=0
    )


def _skill_parse_text(value: str, *, modal_frame: bool = False) -> str:
    if not modal_frame:
        return value
    masked = _MODAL_ACTION_WORD_PATTERN.sub(
        lambda match: " " * len(match.group(0)),
        value,
    )
    return _CLAUSE_GRAMMAR_PRONOUN_PATTERN.sub(
        lambda match: " " * len(match.group(0)),
        masked,
    )


def _skill_term_mentions(
    value: str,
    *,
    modal_frame: bool = False,
) -> list[tuple[int, int, str]]:
    mentions: list[tuple[int, int, str]] = []
    parsed = _skill_parse_text(value, modal_frame=modal_frame)
    for token_match in re.finditer(r"[\w+#.-]+", parsed, re.UNICODE):
        token = token_match.group(0).strip(".-").casefold()
        if len(token) < 2 or token.isdigit() or token in _SKILL_STOPWORDS:
            continue
        components = [
            component
            for component in token.split("-")
            if len(component) >= 2 and not component.isdigit() and component not in _SKILL_STOPWORDS
        ]
        if len(components) < len(token.split("-")):
            mentions.extend(
                (token_match.start(), token_match.end(), component) for component in components
            )
        else:
            mentions.append((token_match.start(), token_match.end(), token))
    return mentions


def _skill_terms(value: str, *, modal_frame: bool = False) -> set[str]:
    return {term for _start, _end, term in _skill_term_mentions(value, modal_frame=modal_frame)}


def _segment_skill_text(segment: _ClauseSegment) -> tuple[str, bool]:
    if segment.absence_scope:
        return segment.text, False
    if segment.explicit_status == "exclusion":
        return segment.text, True
    marker_start = segment.marker_start
    marker_end = segment.marker_end
    if segment.marker_direction == "forward" and marker_end is not None:
        scope = segment.text[marker_end:]
    elif segment.marker_direction == "backward" and marker_start is not None:
        scope = segment.text[:marker_start]
    else:
        scope = segment.text
    marker = (
        segment.text[marker_start:marker_end]
        if marker_start is not None and marker_end is not None
        else ""
    )
    modal_frame = bool(
        _FORWARD_MODAL_MARKER.fullmatch(marker) or _PASSIVE_MODAL_MARKER.fullmatch(marker)
    )
    modal_frame = modal_frame or segment.explicit_status == "exclusion"
    modal_frame = modal_frame or _positive_reassertion(segment.text)
    return scope, modal_frame


def _segment_skill_terms(segment: _ClauseSegment) -> set[str]:
    scope, modal_frame = _segment_skill_text(segment)
    return _skill_terms(scope, modal_frame=modal_frame)


def _required_value_groups(
    clauses: Sequence[_ClauseSegment],
    values_for: Callable[[_ClauseSegment], Collection[str]],
) -> list[list[str]]:
    all_groups: list[list[str]] = []
    group_start = 0
    boundaries = [
        *(
            index
            for index, clause in enumerate(clauses)
            if index > 0 and clause.connector == "adversative"
        ),
        len(clauses),
    ]
    for group_end in boundaries:
        local_groups: list[list[str]] = []
        chunk: list[str] = []
        chunk_has_alternative = False

        def flush_chunk() -> None:
            nonlocal chunk, chunk_has_alternative
            if not chunk:
                return
            unique = list(dict.fromkeys(chunk))
            if chunk_has_alternative:
                local_groups.append(sorted(unique))
            else:
                local_groups.extend([value] for value in unique)
            chunk = []
            chunk_has_alternative = False

        for clause in clauses[group_start:group_end]:
            if clause.status != "required" or clause.absence_scope:
                flush_chunk()
                continue
            values = sorted({str(value) for value in values_for(clause)})
            for value_index, value in enumerate(values):
                connector = clause.connector if value_index == 0 else "additive"
                if not chunk:
                    chunk = [value]
                    continue
                if connector == "alternative":
                    chunk.append(value)
                    chunk_has_alternative = True
                elif connector == "list":
                    chunk.append(value)
                else:
                    flush_chunk()
                    chunk = [value]
        flush_chunk()
        all_groups.extend(sorted(local_groups, key=lambda group: tuple(group)))
        group_start = group_end
    return all_groups


def _skill_evidence(value: str, fallback: str) -> str:
    """Keep skill clauses separate from language, degree and tenure requirements."""
    relevant = [
        fragment
        for fragment in _all_fragments(value)
        if _skill_terms(fragment) or _positive_reassertion(fragment)
    ]
    return "\n".join(relevant) or fallback


def _requirement_summary(
    dimensions: Mapping[str, str],
    *,
    source_kind: str,
    source_text: str | None = None,
) -> dict[str, Any]:
    clauses = _structured_clauses(
        source_text if source_text is not None else str(dimensions.get("skill") or "")
    )
    if source_kind == "candidate":
        observed_languages: dict[str, int] = {}
        for clause in clauses:
            if clause.status in {"explicit_not_required", "exclusion"}:
                continue
            for language, rank in _languages(clause.text).items():
                observed_languages[language] = max(observed_languages.get(language, 0), rank)
        skill_state: dict[str, bool] = {}
        pending_negative_terms: set[str] = set()
        for clause in clauses:
            status = clause.status
            terms = _segment_skill_terms(clause)
            if status in {"explicit_not_required", "exclusion"}:
                for term in terms:
                    skill_state[term] = False
                pending_negative_terms = terms
                continue
            if _positive_reassertion(clause.text):
                if _anaphoric_reassertion(clause.text):
                    terms = set(pending_negative_terms) if pending_negative_terms else set()
                if not terms and pending_negative_terms:
                    terms = set(pending_negative_terms)
            for term in terms:
                skill_state[term] = True
            pending_negative_terms = set()
        return {
            "observed_experience_years": max(
                (
                    year
                    for clause in clauses
                    if clause.status not in {"explicit_not_required", "exclusion"}
                    for year in _years(clause.text)
                ),
                default=None,
            ),
            "observed_languages": dict(sorted(observed_languages.items())),
            "observed_qualification_rank": max(
                (
                    _qualification_rank(clause.text)
                    for clause in clauses
                    if clause.status not in {"explicit_not_required", "exclusion"}
                ),
                default=0,
            ),
            "observed_skill_terms": sorted(
                term for term, positive in skill_state.items() if positive
            ),
            "negated_skill_terms": sorted(
                term for term, positive in skill_state.items() if not positive
            ),
        }

    required_skill_terms: set[str] = set()
    required_skill_groups: list[list[str]] = []
    preferred_skill_terms: set[str] = set()
    present_skill_terms: set[str] = set()
    excluded_skill_terms: set[str] = set()
    for clause in clauses:
        status = clause.status
        terms = _segment_skill_terms(clause)
        if status == "required":
            required_skill_terms.update(terms)
        elif status == "preferred":
            preferred_skill_terms.update(terms)
        elif status == "present":
            present_skill_terms.update(terms)
        elif status == "exclusion":
            excluded_skill_terms.update(terms)
    required_skill_groups.extend(_required_value_groups(clauses, _segment_skill_terms))
    required_languages: dict[str, int] = {}
    for clause in clauses:
        if clause.status != "required" or clause.absence_scope:
            continue
        for language, rank in _languages(clause.text).items():
            required_languages[language] = max(required_languages.get(language, 0), rank)
    required_language_groups = [
        {language: required_languages[language] for language in group}
        for group in _required_value_groups(
            clauses,
            lambda clause: _languages(clause.text),
        )
    ]
    required_years = [
        year
        for clause in clauses
        if clause.status == "required" and not clause.absence_scope
        for year in _years(clause.text)
    ]
    qualification_ranks = [
        _qualification_rank(clause.text)
        for clause in clauses
        if clause.status == "required" and not clause.absence_scope
    ]
    return {
        "excluded_skill_terms": sorted(excluded_skill_terms),
        "preferred_skill_terms": sorted(preferred_skill_terms),
        "present_skill_terms": sorted(present_skill_terms),
        "required_experience_years": max(required_years, default=None),
        "required_language_groups": required_language_groups,
        "required_languages": dict(sorted(required_languages.items())),
        "required_qualification_rank": max(qualification_ranks, default=0),
        "required_skill_groups": required_skill_groups,
        "required_skill_terms": sorted(required_skill_terms),
    }


def _coverage_complete(
    dimensions: Mapping[str, str],
    *,
    source_kind: str,
) -> dict[str, bool]:
    # The complete server-side clause catalog and summaries are independent of
    # the bounded prompt projection. A long CV or more than four CV clauses must
    # never force a neutral score merely because the model sees a compact view.
    _ = dimensions, source_kind
    return {dimension: True for dimension in _DIMENSIONS}


def _quote_fragments(value: str, fallback: str) -> list[str]:
    fragments = _all_fragments(value)
    if not fragments:
        fragments = [fallback]
    unique: list[str] = []
    seen: set[str] = set()
    for fragment in fragments:
        key = fragment.casefold()
        if fragment and key not in seen:
            seen.add(key)
            unique.append(fragment)
    return unique


def _has_positive_evidence(value: str, *, source_kind: str) -> bool:
    normalized = " ".join(value.casefold().split())
    if _is_missing_evidence(normalized):
        return False
    if source_kind == "candidate" and _requirement_status(value) in {
        "explicit_not_required",
        "exclusion",
    }:
        return False
    informative = set(re.findall(r"[\w+#.-]+", normalized)) - {
        "expected",
        "location",
        "role",
        "search",
        "strategy",
        "title",
    }
    return any(token.strip(".-") for token in informative)


def _atomic_quotes(
    base_id: str,
    dimensions: Mapping[str, str],
    *,
    max_document_chars: int,
    source_kind: str,
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Build a compact, bounded quote catalog while preserving every dimension.

    One quote per dimension is reserved first. Additional fragments are admitted in
    round-robin order so a later sentence (for example a concrete skill) remains
    selectable without allowing long CVs or job ads to consume the model context.
    """
    candidates = {
        dimension: _quote_fragments(
            str(dimensions.get(dimension) or ""),
            f"No explicit {dimension} evidence.",
        )
        for dimension in _DIMENSIONS
    }
    quotes: dict[str, dict[str, Any]] = {}
    lines = ["ATOMIC_EVIDENCE_QUOTES"]

    for dimension in _DIMENSIONS:
        for fragment_index, fragment in enumerate(candidates[dimension]):
            quote_id = f"{base_id}:{dimension}:{fragment_index}"
            quotes[quote_id] = {
                "dimension": dimension,
                "has_positive_evidence": _has_positive_evidence(fragment, source_kind=source_kind),
                "requirement_status": _requirement_status(fragment),
                "text": fragment,
                "text_hash": _quote_hash(dimension, fragment),
            }

    def add_prompt_quote(dimension: str, fragment_index: int) -> bool:
        fragment = candidates[dimension][fragment_index]
        quote_id = f"{base_id}:{dimension}:{fragment_index}"
        line = f"{quote_id} | {compact_prompt_text(fragment, _MAX_QUOTE_CHARS)}"
        projected = "\n".join((*lines, line))
        if len(projected) > max_document_chars:
            return False
        lines.append(line)
        return True

    for dimension in _DIMENSIONS:
        if not add_prompt_quote(dimension, 0):
            raise ValueError("atomic evidence budget cannot represent every match dimension")
    for fragment_index in range(1, _MAX_PROMPT_QUOTES_PER_DIMENSION):
        for dimension in _DIMENSIONS:
            if fragment_index < len(candidates[dimension]):
                add_prompt_quote(dimension, fragment_index)
    text = "\n".join(lines)
    if len(text) > max_document_chars:
        raise AssertionError("atomic evidence exceeded its deterministic document budget")
    return text, quotes


def candidate_evidence_document(profile: Mapping[str, Any]) -> EvidenceDocument:
    role = sanitize_prompt_text(profile.get("role_description") or "", max_chars=1000)
    strategy = sanitize_prompt_text(profile.get("search_strategy") or "", max_chars=1000)
    raw_cv = clean_html_tags(str(profile.get("cv_content") or ""))
    cv = compact_prompt_text(raw_cv, 4000)
    location_filter = sanitize_prompt_text(profile.get("location_filter") or "", max_chars=500)
    language = _matching_fragments(cv, "language")
    location = _matching_fragments(cv, "location")
    qualification = _matching_fragments(cv, "qualification")
    dimensions = {
        "skill": _skill_evidence(cv, "No explicit skill evidence in raw candidate profile."),
        "experience": _matching_fragments(cv, "experience")
        or "No explicit experience evidence in raw candidate profile.",
        "intent": f"Expected Role: {role}. Search Strategy: {strategy}",
        "language": language or "No explicit language evidence in raw candidate profile.",
        "location": "\n".join(
            part
            for part in (
                f"Preferred Location: {location_filter}." if location_filter else "",
                location,
            )
            if part
        )
        or "No explicit location evidence in raw candidate profile.",
        "transferability": _skill_evidence(
            cv, "No explicit transferability evidence in raw candidate profile."
        ),
        "qualification": qualification
        or "No explicit qualification evidence in raw candidate profile.",
    }
    text, quotes = _atomic_quotes(
        "candidate:profile",
        dimensions,
        max_document_chars=_CANDIDATE_EVIDENCE_CHARS,
        source_kind="candidate",
    )
    summary_dimensions = {
        **dimensions,
        "skill": _skill_evidence(raw_cv, "No explicit skill evidence in raw candidate profile."),
        "experience": _matching_fragments(raw_cv, "experience")
        or "No explicit experience evidence in raw candidate profile.",
        "language": _matching_fragments(raw_cv, "language")
        or "No explicit language evidence in raw candidate profile.",
        "location": "\n".join(
            part
            for part in (
                f"Preferred Location: {location_filter}." if location_filter else "",
                _matching_fragments(raw_cv, "location"),
            )
            if part
        )
        or "No explicit location evidence in raw candidate profile.",
        "transferability": _skill_evidence(
            raw_cv, "No explicit transferability evidence in raw candidate profile."
        ),
        "qualification": _matching_fragments(raw_cv, "qualification")
        or "No explicit qualification evidence in raw candidate profile.",
    }
    # Keep the complete server-side catalog even when the prompt projection is
    # compact. The model proposes scores; it never selects these quote IDs.
    _, quotes = _atomic_quotes(
        "candidate:profile",
        summary_dimensions,
        max_document_chars=_CANDIDATE_EVIDENCE_CHARS,
        source_kind="candidate",
    )
    requirement_summary = _requirement_summary(
        summary_dimensions,
        source_kind="candidate",
        source_text=raw_cv,
    )
    coverage_complete = _coverage_complete(summary_dimensions, source_kind="candidate")
    if not cv:
        text += "\nSOURCE_STATUS: Candidate CV is empty."
    return EvidenceDocument(
        id="candidate:profile",
        kind="candidate",
        text=text,
        validation_metadata={
            "source_fingerprint": _source_fingerprint(
                {
                    "cv_content": str(profile.get("cv_content") or ""),
                    "role_description": str(profile.get("role_description") or ""),
                    "search_strategy": str(profile.get("search_strategy") or ""),
                    "location_filter": str(profile.get("location_filter") or ""),
                }
            ),
            "catalog_fingerprint": _catalog_fingerprint(
                quotes,
                requirement_summary=requirement_summary,
                coverage_complete=coverage_complete,
            ),
            "catalog_version": MATCH_EVIDENCE_CATALOG_VERSION,
            "coverage_complete": coverage_complete,
            "quotes": quotes,
            "requirement_summary": requirement_summary,
        },
    )


def job_evidence_document(
    job: Mapping[str, Any],
    row_index: int,
    *,
    description_limit: int,
) -> EvidenceDocument:
    # The catalog is canonical and deliberately independent of runtime prompt tuning.
    # A model with a smaller context still receives the same bounded quote set, so a
    # persisted quote ID cannot silently change meaning when settings change.
    _ = description_limit
    raw_description = clean_html_tags(str(job.get("description") or ""))
    description = compact_prompt_text(raw_description, MATCH_EVIDENCE_DESCRIPTION_CHARS)
    language_evidence = (
        "\n".join(part for part in (_matching_fragments(description, "language"),) if part)
        or "No explicit language requirement in raw job evidence."
    )
    qualification_evidence = (
        "\n".join(part for part in (_matching_fragments(description, "qualification"),) if part)
        or "No explicit qualification requirement in raw job evidence."
    )
    title = sanitize_prompt_text(job.get("title") or "", max_chars=500)
    location = sanitize_prompt_text(job.get("location") or "", max_chars=500)
    dimensions = {
        "skill": _skill_evidence(description, "No explicit skill requirement in raw job evidence."),
        "experience": _matching_fragments(description, "experience")
        or "No explicit experience requirement in raw job evidence.",
        "intent": f"Title: {title}." if title else "No explicit intent evidence.",
        "language": language_evidence,
        "location": f"Location: {location}. {_matching_fragments(description, 'location')}",
        "transferability": _skill_evidence(
            description, "No explicit transferability requirement in raw job evidence."
        ),
        "qualification": qualification_evidence,
    }
    text, quotes = _atomic_quotes(
        f"job:{row_index}",
        dimensions,
        max_document_chars=_JOB_EVIDENCE_CHARS,
        source_kind="job",
    )
    summary_dimensions = {
        **dimensions,
        "skill": _skill_evidence(
            raw_description, "No explicit skill requirement in raw job evidence."
        ),
        "experience": _matching_fragments(raw_description, "experience")
        or "No explicit experience requirement in raw job evidence.",
        "intent": f"Title: {title}." if title else "No explicit intent evidence.",
        "language": _matching_fragments(raw_description, "language")
        or "No explicit language requirement in raw job evidence.",
        "location": f"Location: {location}. {_matching_fragments(raw_description, 'location')}",
        "transferability": _skill_evidence(
            raw_description, "No explicit transferability requirement in raw job evidence."
        ),
        "qualification": _matching_fragments(raw_description, "qualification")
        or "No explicit qualification requirement in raw job evidence.",
    }
    _, quotes = _atomic_quotes(
        f"job:{row_index}",
        summary_dimensions,
        max_document_chars=_JOB_EVIDENCE_CHARS,
        source_kind="job",
    )
    requirement_summary = _requirement_summary(
        summary_dimensions,
        source_kind="job",
        source_text=raw_description,
    )
    coverage_complete = _coverage_complete(summary_dimensions, source_kind="job")
    return EvidenceDocument(
        id=f"job:{row_index}",
        kind="job",
        text=text,
        validation_metadata={
            "source_fingerprint": _source_fingerprint(
                {
                    "company": str(job.get("company") or ""),
                    "description": clean_html_tags(str(job.get("description") or "")),
                    "location": str(job.get("location") or ""),
                    "title": clean_html_tags(str(job.get("title") or "")),
                    "workload": str(job.get("workload") or ""),
                }
            ),
            "catalog_fingerprint": _catalog_fingerprint(
                quotes,
                requirement_summary=requirement_summary,
                coverage_complete=coverage_complete,
            ),
            "catalog_version": MATCH_EVIDENCE_CATALOG_VERSION,
            "coverage_complete": coverage_complete,
            "quotes": quotes,
            "requirement_summary": requirement_summary,
        },
    )


def match_input_fingerprint(
    candidate: EvidenceDocument,
    job: EvidenceDocument,
) -> str:
    canonical = json.dumps(
        {
            "candidate": {
                "catalog_fingerprint": candidate.validation_metadata.get("catalog_fingerprint"),
                "catalog_version": candidate.validation_metadata.get("catalog_version"),
                "id": candidate.id,
                "source_fingerprint": candidate.validation_metadata.get("source_fingerprint"),
            },
            "job": {
                "catalog_fingerprint": job.validation_metadata.get("catalog_fingerprint"),
                "catalog_version": job.validation_metadata.get("catalog_version"),
                "id": job.id,
                "source_fingerprint": job.validation_metadata.get("source_fingerprint"),
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def match_quote_bindings(
    candidate: EvidenceDocument,
    job: EvidenceDocument,
) -> dict[str, dict[str, Any]]:
    bindings: dict[str, dict[str, Any]] = {}
    for document in (candidate, job):
        quotes = document.validation_metadata.get("quotes")
        if not isinstance(quotes, Mapping):
            continue
        for quote_id, quote in quotes.items():
            if isinstance(quote_id, str) and isinstance(quote, Mapping):
                bindings[quote_id] = dict(quote)
    return bindings


def fingerprint_match_input_rows(
    evidence: Sequence[EvidenceDocument],
) -> list[str]:
    candidate = next((item for item in evidence if item.id == "candidate:profile"), None)
    if candidate is None:
        return []
    jobs = sorted(
        (item for item in evidence if item.kind == "job" and item.id.startswith("job:")),
        key=lambda item: int(item.id.split(":", 1)[1]),
    )
    return [match_input_fingerprint(candidate, job) for job in jobs]
