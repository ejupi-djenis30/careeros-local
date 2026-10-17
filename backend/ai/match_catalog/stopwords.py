"""Compose the original skill exclusions without mutating vocabulary inputs."""

from .value_patterns import _CEFR_RANK, _LANGUAGE_ALIASES, _NUMBER_WORDS
from .vocabulary_base import _BASE_SKILL_STOPWORDS, _REQUIREMENT_SKILL_STOPWORDS
from .vocabulary_extended import _GRAMMAR_SKILL_STOPWORDS

_SKILL_STOPWORDS = _BASE_SKILL_STOPWORDS.copy()
_SKILL_STOPWORDS.update(_REQUIREMENT_SKILL_STOPWORDS)
_SKILL_STOPWORDS.update(_GRAMMAR_SKILL_STOPWORDS)
_SKILL_STOPWORDS.update(_LANGUAGE_ALIASES)
_SKILL_STOPWORDS.update(_CEFR_RANK)
_SKILL_STOPWORDS.update(_NUMBER_WORDS)
_SKILL_STOPWORDS.update(word for phrase in _CEFR_RANK for word in phrase.split())
