"""Multilingual numeric, language and qualification patterns."""

from __future__ import annotations

import re

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
