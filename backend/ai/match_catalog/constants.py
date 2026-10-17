"""Evidence catalog dimensions, budgets and status patterns."""

from __future__ import annotations

import re

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
