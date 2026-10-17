"""Structural connectors and multilingual requirement grammar."""

from __future__ import annotations

import re

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
