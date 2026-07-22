from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from backend.ai.retrieval import EvidenceDocument
from backend.services.search.prompt_compaction import compact_prompt_text
from backend.services.search.query_contracts import sanitize_prompt_text
from backend.services.utils import clean_html_tags

MATCH_EVIDENCE_CATALOG_VERSION = "5"
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
            r"\b(?:not\s+required|not\s+(?:a\s+)?requirement|"
            r"no\s+requirement\s+for|no\s+[^.;]{0,80}\s+(?:required|needed)|optional|"
            r"isn['’]t\s+required|(?:doesn['’]t|does\s+not)\s+(?:need|require)|"
            r"(?:don['’]t|doesn['’]t|do\s+not|does\s+not)\s+have\s+to|"
            r"needn['’]t|not\s+needed|not\s+a\s+must|"
            r"nicht\s+(?:erforderlich|notwendig|benötigt|benoetigt)|kein\s+muss|optional|"
            r"non\s+requis(?:e|es|s)?|pas\s+(?:requis|nécessaire|necessaire)|"
            r"facultati(?:f|ve)|optionnel(?:le)?|"
            r"non\s+richiest[oaie]|non\s+necessari[oaie]|facoltativ[oaie]|opzional[eaio])\b",
            re.IGNORECASE,
        ),
    ),
    (
        "exclusion",
        re.compile(
            r"\b(?:do(?:es)?\s+not\s+(?:know|have|use)|must\s+not\s+(?:know|have|use)|"
            r"(?:don['’]t|doesn['’]t)\s+(?:know|have|use)|"
            r"(?:haven['’]t|hasn['’]t)\s+(?:used|worked\s+with)|"
            r"lacks?(?:\s+experience)?\s+(?:with|in)?|"
            r"no\s+experience\s+(?:with|in)|never\s+(?:used|worked\s+with)|"
            r"without\s+(?!(?:(?:direct|close|constant)\s+)?(?:supervision|assistance|"
            r"support|restriction|relocation)\b)(?:any\s+)?(?:experience\s+(?:with|in)\s+)?"
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
            r"ne\b[^.;]{0,60}\b(?:connais|maîtrise|maitrise|utilise)\b[^.;]{0,30}\bpas|"
            r"aucune?\s+expérience\s+avec|jamais\s+utilisé|"
            r"sans\s+(?!(?:(?:supervision|assistance|aide|déménagement|demenagement))\b)"
            r"[\w+#.-]+|"
            r"interdit|exclu|"
            r"non\s+(?:conosco|conosce|abbiamo|ho|uso|usa|utilizzo|utilizza)|"
            r"nessuna?\s+esperienza\s+con|mai\s+usat[oa]|"
            r"senza\s+(?!(?:supervisione|assistenza|supporto|trasferimento)\b)[\w+#.-]+|"
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
            r"doit|devez|minimum|au\s+moins|"
            r"richiest[oaie]|obbligatori[oaie]|necessari[oaie]|deve|devi|"
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
    + r")\s*\+?\s*(?:years?|yrs?|jahre?n?|ans?|années?|anni?)\b",
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
_SKILL_STOPWORDS.update(_LANGUAGE_ALIASES)
_SKILL_STOPWORDS.update(_CEFR_RANK)
_SKILL_STOPWORDS.update(_NUMBER_WORDS)
_SKILL_STOPWORDS.update(word for phrase in _CEFR_RANK for word in phrase.split())

_ALTERNATIVE_CONNECTOR = re.compile(r"\b(?:or|either|oder|entweder|ou|soit|o|oppure)\b", re.I)


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
    """Split mixed-polarity requirement lists into independently classified clauses."""
    fragments: list[str] = []
    for sentence in _FRAGMENT_SPLIT.split(value):
        sentence = " ".join(sentence.split())
        if not sentence:
            continue
        parts = [
            part.strip(" ,-;/")
            for part in re.split(
                r"\s*(?:[,;/]|\b(?:and|but|whereas|while|und|aber|jedoch|während|"
                r"et|mais|tandis\s+que|e|ma|però|pero|mentre)\b)\s*",
                sentence,
                flags=re.IGNORECASE,
            )
            if part.strip(" ,-;/")
        ]
        # In lists such as "Python, FastAPI and Docker required", the trailing
        # marker governs preceding unmarked list items. Never propagate across a
        # clause that already carries its own polarity.
        marker_suffix = {
            "required": "required",
            "preferred": "preferred",
            "explicit_not_required": "optional",
            "exclusion": "prohibited",
        }
        for index in range(len(parts) - 2, -1, -1):
            next_status = _explicit_requirement_status(parts[index + 1])
            if _explicit_requirement_status(parts[index]) is None and next_status in marker_suffix:
                parts[index] = f"{parts[index]} {marker_suffix[str(next_status)]}"
        fragments.extend(parts)
    return fragments


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


def _skill_terms(value: str) -> set[str]:
    return {
        token.strip(".-").casefold()
        for token in re.findall(r"[\w+#.-]+", value, re.UNICODE)
        if len(token.strip(".-")) >= 2
        and not token.strip(".-").isdigit()
        and token.strip(".-").casefold() not in _SKILL_STOPWORDS
    }


def _skill_evidence(value: str, fallback: str) -> str:
    """Keep skill clauses separate from language, degree and tenure requirements."""
    relevant = [fragment for fragment in _all_fragments(value) if _skill_terms(fragment)]
    return "\n".join(relevant) or fallback


def _requirement_summary(
    dimensions: Mapping[str, str],
    *,
    source_kind: str,
) -> dict[str, Any]:
    skill_fragments = _all_fragments(str(dimensions.get("skill") or ""))
    experience_fragments = _all_fragments(str(dimensions.get("experience") or ""))
    language_fragments = _all_fragments(str(dimensions.get("language") or ""))
    qualification_fragments = _all_fragments(str(dimensions.get("qualification") or ""))
    if source_kind == "candidate":
        observed_languages: dict[str, int] = {}
        for fragment in language_fragments:
            if _requirement_status(fragment) in {"explicit_not_required", "exclusion"}:
                continue
            for language, rank in _languages(fragment).items():
                observed_languages[language] = max(observed_languages.get(language, 0), rank)
        positive_skill_fragments = [
            fragment
            for fragment in skill_fragments
            if _requirement_status(fragment) in {"present", "required", "preferred"}
        ]
        negative_skill_fragments = [
            fragment
            for fragment in skill_fragments
            if _requirement_status(fragment) in {"explicit_not_required", "exclusion"}
        ]
        return {
            "observed_experience_years": max(
                (
                    year
                    for fragment in experience_fragments
                    if _requirement_status(fragment) not in {"explicit_not_required", "exclusion"}
                    for year in _years(fragment)
                ),
                default=None,
            ),
            "observed_languages": dict(sorted(observed_languages.items())),
            "observed_qualification_rank": max(
                (
                    _qualification_rank(fragment)
                    for fragment in qualification_fragments
                    if _requirement_status(fragment) not in {"explicit_not_required", "exclusion"}
                ),
                default=0,
            ),
            "observed_skill_terms": sorted(
                {term for fragment in positive_skill_fragments for term in _skill_terms(fragment)}
            ),
            "negated_skill_terms": sorted(
                {term for fragment in negative_skill_fragments for term in _skill_terms(fragment)}
            ),
        }

    required_skill_terms: set[str] = set()
    required_skill_groups: list[list[str]] = []
    preferred_skill_terms: set[str] = set()
    present_skill_terms: set[str] = set()
    excluded_skill_terms: set[str] = set()
    for fragment in skill_fragments:
        status = _requirement_status(fragment)
        if status == "required":
            terms = _skill_terms(fragment)
            required_skill_terms.update(terms)
            if terms:
                if _ALTERNATIVE_CONNECTOR.search(fragment):
                    required_skill_groups.append(sorted(terms))
                else:
                    required_skill_groups.extend([term] for term in sorted(terms))
        elif status == "preferred":
            preferred_skill_terms.update(_skill_terms(fragment))
        elif status == "present":
            present_skill_terms.update(_skill_terms(fragment))
        elif status == "exclusion":
            excluded_skill_terms.update(_skill_terms(fragment))
    required_languages: dict[str, int] = {}
    for fragment in language_fragments:
        if _requirement_status(fragment) != "required":
            continue
        for language, rank in _languages(fragment).items():
            required_languages[language] = max(required_languages.get(language, 0), rank)
    required_years = [
        year
        for fragment in experience_fragments
        if _requirement_status(fragment) == "required"
        for year in _years(fragment)
    ]
    qualification_ranks = [
        _qualification_rank(fragment)
        for fragment in qualification_fragments
        if _requirement_status(fragment) == "required"
    ]
    return {
        "excluded_skill_terms": sorted(excluded_skill_terms),
        "preferred_skill_terms": sorted(preferred_skill_terms),
        "present_skill_terms": sorted(present_skill_terms),
        "required_experience_years": max(required_years, default=None),
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
    requirement_summary = _requirement_summary(summary_dimensions, source_kind="candidate")
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
    requirement_summary = _requirement_summary(summary_dimensions, source_kind="job")
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
