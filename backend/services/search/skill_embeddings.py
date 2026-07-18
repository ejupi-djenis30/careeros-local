"""Deterministic local skill similarity.

The legacy module name is preserved for callers, but this implementation never imports or
downloads model weights. Optional semantic embeddings can later be provided by the same
validated local inference boundary.
"""

from difflib import SequenceMatcher
from functools import lru_cache
from typing import List


def is_available() -> bool:
    return True


def _normalize(value: str) -> str:
    return " ".join(
        "".join(char if char.isalnum() else " " for char in value.lower()).split()
    )


@lru_cache(maxsize=4096)
def embedding_skill_similarity(skill_a: str, skill_b: str) -> float:
    """Return a reproducible lexical similarity without network or model loading."""
    left = _normalize(skill_a)
    right = _normalize(skill_b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    token_score = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    sequence_score = SequenceMatcher(None, left, right).ratio()
    return round(max(token_score, sequence_score * 0.9), 6)


def best_embedding_match(
    query_skill: str,
    candidate_skills: List[str],
    threshold: float = 0.65,
) -> float:
    if not query_skill or not candidate_skills:
        return 0.0
    best = max(
        (embedding_skill_similarity(query_skill, item) for item in candidate_skills if item),
        default=0.0,
    )
    return best if best >= threshold else 0.0


def embedding_skills_score(
    job_skills: List[str],
    profile_skills: List[str],
    threshold: float = 0.65,
) -> float:
    valid_job_skills = [item for item in job_skills if item]
    if not valid_job_skills or not profile_skills:
        return 0.0
    return sum(
        best_embedding_match(item, profile_skills, threshold=threshold)
        for item in valid_job_skills
    ) / len(valid_job_skills)


def preload_taxonomy_embeddings(taxonomy_skills: List[str], model_name: str = "") -> None:
    """Warm the deterministic cache; ``model_name`` remains for call compatibility."""
    del model_name
    for skill in taxonomy_skills:
        if skill:
            embedding_skill_similarity(skill, skill)
