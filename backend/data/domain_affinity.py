"""Domain affinity matrix for weighted cross-domain similarity scoring.

Replaces the binary RELATED_DOMAIN_GROUPS logic with a continuous affinity
score (0.0–1.0) between any two job domains. This enables nuanced pre-scoring
and filtering: a job in a "close" domain gets a better pre-score than one in a
completely unrelated domain, without requiring the binary pass/fail of the old system.

Usage::

    affinity = get_domain_affinity("it", "consulting")   # → 0.5
    affinity = get_domain_affinity("it", "it")           # → 1.0
    affinity = get_domain_affinity("it", "construction") # → 0.05
"""

from typing import Dict

# Affinity matrix: symmetric, values 0.0–1.0
# 1.0 = same domain (handled automatically in get_domain_affinity)
# 0.7-0.9 = very closely related (same sector, complementary skills)
# 0.4-0.65 = moderately related (overlapping skills / transferable)
# 0.1-0.35 = weakly related (generic skills transfer, but domain very different)
# 0.0-0.09 = essentially unrelated

_AFFINITY_MATRIX: Dict[str, Dict[str, float]] = {
    "it": {
        "engineering": 0.55,
        "consulting": 0.5,
        "marketing": 0.45,  # digital marketing / growth engineering
        "finance": 0.35,  # fintech overlap
        "administration": 0.3,
        "education": 0.3,
        "pharma": 0.25,  # bioinformatics, data science
        "medical": 0.2,
        "logistics": 0.2,
        "sales": 0.2,
        "legal": 0.15,
        "hospitality": 0.1,
        "construction": 0.1,
        "general": 0.3,
    },
    "engineering": {
        "it": 0.55,
        "construction": 0.65,
        "pharma": 0.45,
        "medical": 0.35,
        "logistics": 0.35,
        "consulting": 0.4,
        "administration": 0.2,
        "finance": 0.15,
        "education": 0.2,
        "sales": 0.15,
        "marketing": 0.15,
        "legal": 0.1,
        "hospitality": 0.05,
        "general": 0.25,
    },
    "finance": {
        "administration": 0.65,
        "consulting": 0.7,
        "legal": 0.45,
        "it": 0.35,
        "sales": 0.35,
        "education": 0.2,
        "pharma": 0.15,
        "medical": 0.15,
        "engineering": 0.15,
        "marketing": 0.25,
        "logistics": 0.15,
        "hospitality": 0.1,
        "construction": 0.1,
        "general": 0.3,
    },
    "consulting": {
        "finance": 0.7,
        "it": 0.5,
        "administration": 0.55,
        "legal": 0.5,
        "education": 0.45,
        "marketing": 0.45,
        "engineering": 0.4,
        "sales": 0.4,
        "pharma": 0.3,
        "medical": 0.2,
        "logistics": 0.15,
        "hospitality": 0.1,
        "construction": 0.1,
        "general": 0.35,
    },
    "medical": {
        "pharma": 0.8,
        "education": 0.55,  # healthcare training / teaching
        "administration": 0.35,
        "legal": 0.25,
        "consulting": 0.2,
        "engineering": 0.35,  # biomedical engineering
        "logistics": 0.2,
        "it": 0.2,
        "sales": 0.15,
        "finance": 0.15,
        "marketing": 0.15,
        "hospitality": 0.1,
        "construction": 0.05,
        "general": 0.2,
    },
    "pharma": {
        "medical": 0.8,
        "engineering": 0.45,
        "education": 0.35,
        "consulting": 0.3,
        "legal": 0.25,
        "it": 0.25,
        "administration": 0.25,
        "logistics": 0.2,
        "finance": 0.15,
        "sales": 0.2,
        "marketing": 0.2,
        "hospitality": 0.05,
        "construction": 0.05,
        "general": 0.2,
    },
    "marketing": {
        "sales": 0.8,
        "consulting": 0.45,
        "it": 0.45,
        "administration": 0.4,
        "education": 0.35,
        "finance": 0.25,
        "legal": 0.2,
        "hospitality": 0.2,  # events marketing
        "medical": 0.15,
        "pharma": 0.2,
        "logistics": 0.1,
        "engineering": 0.15,
        "construction": 0.05,
        "general": 0.3,
    },
    "sales": {
        "marketing": 0.8,
        "consulting": 0.4,
        "hospitality": 0.55,  # client-facing service
        "administration": 0.35,
        "it": 0.2,
        "finance": 0.35,
        "pharma": 0.2,
        "medical": 0.15,
        "education": 0.25,
        "legal": 0.2,
        "engineering": 0.15,
        "logistics": 0.3,
        "construction": 0.1,
        "general": 0.4,
    },
    "logistics": {
        "construction": 0.45,
        "engineering": 0.35,
        "administration": 0.4,
        "sales": 0.3,
        "hospitality": 0.25,
        "it": 0.2,
        "finance": 0.15,
        "marketing": 0.1,
        "consulting": 0.15,
        "education": 0.1,
        "medical": 0.2,
        "pharma": 0.2,
        "legal": 0.1,
        "general": 0.5,
    },
    "administration": {
        "finance": 0.65,
        "legal": 0.55,
        "consulting": 0.55,
        "marketing": 0.4,
        "sales": 0.35,
        "it": 0.3,
        "education": 0.4,
        "logistics": 0.4,
        "medical": 0.35,
        "pharma": 0.25,
        "engineering": 0.2,
        "hospitality": 0.25,
        "construction": 0.15,
        "general": 0.45,
    },
    "legal": {
        "administration": 0.55,
        "consulting": 0.5,
        "finance": 0.45,
        "medical": 0.25,
        "pharma": 0.25,
        "it": 0.15,
        "education": 0.3,
        "sales": 0.2,
        "marketing": 0.2,
        "engineering": 0.1,
        "logistics": 0.1,
        "hospitality": 0.1,
        "construction": 0.1,
        "general": 0.25,
    },
    "education": {
        "consulting": 0.45,
        "administration": 0.4,
        "medical": 0.55,
        "legal": 0.3,
        "marketing": 0.35,
        "it": 0.3,
        "finance": 0.2,
        "hospitality": 0.2,
        "pharma": 0.35,
        "sales": 0.25,
        "engineering": 0.2,
        "logistics": 0.1,
        "construction": 0.1,
        "general": 0.3,
    },
    "hospitality": {
        "sales": 0.55,
        "administration": 0.25,
        "marketing": 0.2,
        "education": 0.2,
        "medical": 0.1,
        "logistics": 0.25,
        "consulting": 0.1,
        "finance": 0.1,
        "it": 0.1,
        "engineering": 0.05,
        "pharma": 0.05,
        "legal": 0.1,
        "construction": 0.1,
        "general": 0.4,
    },
    "construction": {
        "engineering": 0.65,
        "logistics": 0.45,
        "administration": 0.15,
        "it": 0.1,
        "finance": 0.1,
        "marketing": 0.05,
        "sales": 0.1,
        "legal": 0.1,
        "medical": 0.05,
        "pharma": 0.05,
        "education": 0.1,
        "hospitality": 0.1,
        "consulting": 0.1,
        "general": 0.3,
    },
    "general": {
        "logistics": 0.5,
        "hospitality": 0.4,
        "administration": 0.45,
        "sales": 0.4,
        "marketing": 0.3,
        "education": 0.3,
        "it": 0.3,
        "finance": 0.3,
        "consulting": 0.35,
        "construction": 0.3,
        "engineering": 0.25,
        "legal": 0.25,
        "medical": 0.2,
        "pharma": 0.2,
    },
}


def get_domain_affinity(domain_a: str, domain_b: str) -> float:
    """Return affinity score (0.0–1.0) between two domains.

    - 1.0 = same domain
    - Scores are symmetric (A→B == B→A)
    - Defaults to 0.1 for unknown domain combinations
    """
    a = str(domain_a or "general").strip().lower()
    b = str(domain_b or "general").strip().lower()
    if a == b:
        return 1.0
    score = _AFFINITY_MATRIX.get(a, {}).get(b)
    if score is None:
        score = _AFFINITY_MATRIX.get(b, {}).get(a)
    return score if score is not None else 0.1


def domains_are_related(domain_a: str, domain_b: str, threshold: float = 0.35) -> bool:
    """Return True when affinity between two domains meets the threshold.

    Default threshold of 0.35 matches the previous binary related-group logic.
    """
    return get_domain_affinity(domain_a, domain_b) >= threshold
