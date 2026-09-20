"""Linear-time detection of unresolved application-material placeholders."""

from __future__ import annotations

_BRACKETED_NAMES = frozenset(
    {"company", "recipient", "name", "date", "role", "address", "employer"}
)
_BRACKETED_PREFIXES = ("insert", "todo")
_INSTRUCTION_WORDS = frozenset({"todo", "fixme", "xxx"})


def contains_unresolved_placeholder(text: str) -> bool:
    """Return whether *text* contains a known placeholder in one linear scan."""
    bracket_start: int | None = None
    word_start: int | None = None

    for index, character in enumerate(text):
        if character == "[":
            # Restarting at the innermost opener also handles malformed nested input
            # without repeatedly rescanning the same suffix.
            bracket_start = index + 1
        elif character == "]" and bracket_start is not None:
            placeholder = text[bracket_start:index].strip().casefold()
            if placeholder in _BRACKETED_NAMES or placeholder.startswith(_BRACKETED_PREFIXES):
                return True
            bracket_start = None

        if character == "_" or character.isalnum():
            if word_start is None:
                word_start = index
        elif word_start is not None:
            if text[word_start:index].casefold() in _INSTRUCTION_WORDS:
                return True
            word_start = None

    return word_start is not None and text[word_start:].casefold() in _INSTRUCTION_WORDS
