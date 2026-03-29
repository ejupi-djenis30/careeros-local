"""Post-LLM normalization validation and coercion layer.

Validates LLM-returned normalization fields against strict allowlists and
maps common hallucinations to their correct canonical values. Returns a
corrected dict along with a list of field names that required correction
(useful for triggering targeted re-normalization on low-confidence results).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Allowlist enums ──────────────────────────────────────────────────────────

VALID_DOMAINS = frozenset(
    {
        "general",
        "it",
        "finance",
        "medical",
        "engineering",
        "hospitality",
        "sales",
        "logistics",
        "administration",
        "legal",
        "education",
        "marketing",
        "consulting",
        "pharma",
        "construction",
    }
)

VALID_SENIORITY = frozenset({"junior", "mid", "senior"})

VALID_ROLE_TYPES = frozenset(
    {
        "technical",
        "manual",
        "administrative",
        "creative",
        "managerial",
        "service",
        "professional",
    }
)

VALID_EMPLOYMENT_MODES = frozenset({"remote", "hybrid", "on-site"})

VALID_CONTRACT_TYPES = frozenset({"permanent", "temporary", "internship", "freelance"})

VALID_QUALIFICATION_LEVELS = frozenset({"none", "vocational", "bachelor", "master", "phd"})

VALID_ENTRY_BARRIERS = frozenset({"none", "low", "medium", "high"})

# ─── Common LLM hallucination → canonical mapping ─────────────────────────────
# Maps values frequently returned by LLMs that are close but not in the allowlist.

_SENIORITY_MAP: Dict[str, str] = {
    # English expansions
    "entry": "junior",
    "entry-level": "junior",
    "entry level": "junior",
    "graduate": "junior",
    "intern": "junior",
    "trainee": "junior",
    "apprentice": "junior",
    "beginner": "junior",
    "intermediate": "mid",
    "experienced": "mid",
    "associate": "mid",
    "professional": "mid",
    "specialist": "mid",
    "lead": "senior",
    "principal": "senior",
    "staff": "senior",
    "head": "senior",
    "director": "senior",
    "manager": "senior",
    "expert": "senior",
    "architect": "senior",
    # German
    "berufseinsteiger": "junior",
    "einsteiger": "junior",
    "berufserfahren": "mid",
    "erfahren": "mid",
    "leitend": "senior",
    "führungskraft": "senior",
}

_DOMAIN_MAP: Dict[str, str] = {
    # Common expansions → canonical
    "information technology": "it",
    "software": "it",
    "tech": "it",
    "software development": "it",
    "it/tech": "it",
    "data science": "it",
    "fintech": "finance",
    "banking": "finance",
    "accounting": "finance",
    "healthcare": "medical",
    "health": "medical",
    "nursing": "medical",
    "pharmaceutical": "pharma",
    "drug development": "pharma",
    "mechanical engineering": "engineering",
    "electrical engineering": "engineering",
    "civil engineering": "engineering",
    "chemical engineering": "engineering",
    "warehouse": "logistics",
    "shipping": "logistics",
    "supply chain": "logistics",
    "restaurant": "hospitality",
    "hotel": "hospitality",
    "cleaning": "hospitality",
    "retail": "sales",
    "customer service": "sales",
    "hr": "administration",
    "human resources": "administration",
    "office": "administration",
    "secretarial": "administration",
    "law": "legal",
    "legal services": "legal",
    "teaching": "education",
    "academic": "education",
    "digital marketing": "marketing",
    "advertising": "marketing",
    "management consulting": "consulting",
    "strategy": "consulting",
    "construction work": "construction",
    "building": "construction",
}

_ROLE_TYPE_MAP: Dict[str, str] = {
    "physical": "manual",
    "hands-on": "manual",
    "labor": "manual",
    "labourer": "manual",
    "handwork": "manual",
    "it": "technical",
    "engineering": "technical",
    "developer": "technical",
    "office": "administrative",
    "clerical": "administrative",
    "customer-facing": "service",
    "hospitality": "service",
    "specialist": "professional",
    "expert": "professional",
    "leadership": "managerial",
    "supervisory": "managerial",
    "design": "creative",
    "artistic": "creative",
}

_QUALIFICATION_MAP: Dict[str, str] = {
    # None tier
    "no qualification": "none",
    "no degree": "none",
    "none required": "none",
    "not required": "none",
    "any": "none",
    # Vocational
    "apprenticeship": "vocational",
    "vocational training": "vocational",
    "eidg. dipl.": "vocational",
    "eidg dipl": "vocational",
    "fachausweis": "vocational",
    "berufslehre": "vocational",
    "certificate": "vocational",
    "diploma": "vocational",
    "associate": "vocational",
    # Bachelor
    "university": "bachelor",
    "college": "bachelor",
    "degree": "bachelor",
    "bachelor's": "bachelor",
    "b.sc.": "bachelor",
    "b.a.": "bachelor",
    "undergraduate": "bachelor",
    # Master
    "master's": "master",
    "m.sc.": "master",
    "m.a.": "master",
    "mba": "master",
    "postgraduate": "master",
    # PhD
    "doctorate": "phd",
    "ph.d.": "phd",
    "dr.": "phd",
    "doctoral": "phd",
}

_ENTRY_BARRIER_MAP: Dict[str, str] = {
    "no barrier": "none",
    "open": "none",
    "accessible": "none",
    "entry level": "low",
    "beginner friendly": "low",
    "basic": "low",
    "moderate": "medium",
    "standard": "medium",
    "intermediate": "medium",
    "strict": "high",
    "expert only": "high",
    "highly specialized": "high",
}

_EMPLOYMENT_MODE_MAP: Dict[str, str] = {
    "full remote": "remote",
    "home office": "remote",
    "telework": "remote",
    "teletravail": "remote",
    "telelavoro": "remote",
    "fully remote": "remote",
    "partially remote": "hybrid",
    "occasional home office": "hybrid",
    "on site": "on-site",
    "office": "on-site",
    "in-person": "on-site",
    "in person": "on-site",
    "presence": "on-site",
}

_CONTRACT_TYPE_MAP: Dict[str, str] = {
    "fixed-term": "temporary",
    "fix-term": "temporary",
    "befristet": "temporary",
    "zeitlich begrenzt": "temporary",
    "temp": "temporary",
    "contractor": "temporary",
    "unbefristet": "permanent",
    "open-ended": "permanent",
    "indefinite": "permanent",
    "festanstellung": "permanent",
    "full-time": "permanent",
    "self-employed": "freelance",
    "independent": "freelance",
    "trainee": "internship",
    "praktikum": "internship",
    "stage": "internship",
}


def _remap(value: str, mapping: Dict[str, str]) -> Optional[str]:
    """Try to remap a value using the provided mapping. Returns None if no match."""
    v = value.strip().lower()
    return mapping.get(v)


def validate_normalized_job(
    raw: Dict[str, Any], job_index: int = 0
) -> Tuple[Dict[str, Any], List[str]]:
    """Validate and coerce a single normalized job dict.

    Checks every enum field against its allowlist. Invalid values are:
    1. Tried against the hallucination-remapping tables.
    2. If still unresolvable, set to None and recorded in `corrected_fields`.

    Args:
        raw: The normalized dict as returned by the LLM.
        job_index: Index in the batch (for logging only).

    Returns:
        (corrected_dict, corrected_fields) where corrected_fields lists the
        field names that were modified or nulled.
    """
    corrected: Dict[str, Any] = dict(raw)
    corrected_fields: List[str] = []

    def _fix_enum(field: str, valid_set: frozenset, remap: Dict[str, str]):
        val = corrected.get(field)
        if val is None:
            return
        val_lower = str(val).strip().lower()
        if val_lower in valid_set:
            if val_lower != val:
                corrected[field] = val_lower
            return
        # Try remapping
        remapped = _remap(val_lower, remap)
        if remapped and remapped in valid_set:
            logger.debug(
                "[NORM_VALIDATE] job[%d] field=%s: '%s' → '%s' (remapped)",
                job_index,
                field,
                val,
                remapped,
            )
            corrected[field] = remapped
            corrected_fields.append(field)
        else:
            logger.warning(
                "[NORM_VALIDATE] job[%d] field=%s: '%s' is invalid and cannot be remapped — nulling",
                job_index,
                field,
                val,
            )
            corrected[field] = None
            corrected_fields.append(field)

    _fix_enum("seniority", VALID_SENIORITY, _SENIORITY_MAP)
    _fix_enum("domain", VALID_DOMAINS, _DOMAIN_MAP)
    _fix_enum("role_type", VALID_ROLE_TYPES, _ROLE_TYPE_MAP)
    _fix_enum("employment_mode", VALID_EMPLOYMENT_MODES, _EMPLOYMENT_MODE_MAP)
    _fix_enum("contract_type", VALID_CONTRACT_TYPES, _CONTRACT_TYPE_MAP)
    _fix_enum("qualification_level", VALID_QUALIFICATION_LEVELS, _QUALIFICATION_MAP)
    _fix_enum("entry_barrier", VALID_ENTRY_BARRIERS, _ENTRY_BARRIER_MAP)

    # Validate confidence is in [0, 1]
    conf = corrected.get("confidence")
    if conf is not None:
        try:
            conf_f = max(0.0, min(1.0, float(conf)))
            if conf_f != conf:
                corrected["confidence"] = conf_f
        except (TypeError, ValueError):
            corrected["confidence"] = 0.0
            corrected_fields.append("confidence")

    # Validate integer fields are non-negative
    for int_field in (
        "experience_min_years",
        "experience_max_years",
        "workload_min",
        "workload_max",
        "salary_min_chf",
        "salary_max_chf",
    ):
        val = corrected.get(int_field)
        if val is not None:
            try:
                iv = int(val)
                if iv < 0:
                    corrected[int_field] = 0
                    corrected_fields.append(int_field)
            except (TypeError, ValueError):
                corrected[int_field] = None
                corrected_fields.append(int_field)

    # Coerce career_changer_friendly to strict bool
    ccf = corrected.get("career_changer_friendly")
    if ccf is not None and not isinstance(ccf, bool):
        if isinstance(ccf, str):
            corrected["career_changer_friendly"] = ccf.lower() in {"true", "1", "yes"}
        else:
            corrected["career_changer_friendly"] = bool(ccf)

    return corrected, corrected_fields


def validate_normalized_batch(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[int]]:
    """Validate a full batch of normalized job rows.

    Returns:
        (corrected_rows, indices_needing_review) where indices_needing_review
        lists job indices where corrections were applied (candidates for re-normalization).
    """
    corrected_rows: List[Dict[str, Any]] = []
    indices_needing_review: List[int] = []

    for i, row in enumerate(rows):
        corrected, corrected_fields = validate_normalized_job(row, job_index=i)
        corrected_rows.append(corrected)
        if corrected_fields:
            indices_needing_review.append(i)
            logger.info(
                "[NORM_VALIDATE] job[%d] corrected %d fields: %s",
                i,
                len(corrected_fields),
                corrected_fields,
            )

    return corrected_rows, indices_needing_review
