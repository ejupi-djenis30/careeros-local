"""Embedding-based semantic skill similarity (Phase 1).

Provides a lazy-loaded, thread-safe singleton that wraps a sentence-transformers
model to compute cosine similarity between arbitrary skill strings.

The module degrades gracefully: if ``sentence-transformers`` is not installed, all
public functions return 0.0 / fall through to the taxonomy tiers downstream.

Usage::

    from backend.services.search.skill_embeddings import embedding_skill_similarity, is_available

    if is_available():
        score = embedding_skill_similarity("Projektleitung", "Project Management")
        # → ~0.85
"""

from __future__ import annotations

import logging
import threading
from functools import lru_cache
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# ─── availability flag ────────────────────────────────────────────────────────

try:
    import numpy as np  # type: ignore[import]
    from sentence_transformers import SentenceTransformer  # type: ignore[import]

    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    np = None  # type: ignore[assignment]
    SentenceTransformer = None  # type: ignore[assignment]
    _SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.info(
        "[SKILL_EMB] sentence-transformers not installed. "
        "Skill embedding tier is disabled. "
        "Install with: pip install sentence-transformers"
    )


def is_available() -> bool:
    """Return True when the sentence-transformers library is installed."""
    return _SENTENCE_TRANSFORMERS_AVAILABLE


# ─── singleton model cache ────────────────────────────────────────────────────

class _EmbeddingCache:
    """Thread-safe singleton that holds the loaded model and an LRU skill cache."""

    _instance: Optional["_EmbeddingCache"] = None
    _lock = threading.Lock()
    # Instance attributes initialised in __new__:
    _model: Any | None
    _model_name: str
    _model_lock: threading.Lock

    def __new__(cls) -> "_EmbeddingCache":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._model = None
                    obj._model_name = ""
                    obj._model_lock = threading.Lock()
                    cls._instance = obj
        return cls._instance

    def _load_model(self, model_name: str) -> None:
        with self._model_lock:
            if self._model is not None and self._model_name == model_name:
                return
            if not _SENTENCE_TRANSFORMERS_AVAILABLE:
                return
            try:
                logger.info("[SKILL_EMB] Loading embedding model: %s", model_name)
                self._model = SentenceTransformer(model_name)  # type: ignore[operator]
                self._model_name = model_name
                logger.info("[SKILL_EMB] Embedding model loaded successfully.")
            except Exception as exc:
                logger.error("[SKILL_EMB] Failed to load embedding model %r: %s", model_name, exc)
                self._model = None

    def get_model(self, model_name: str):

        if self._model is None or self._model_name != model_name:
            self._load_model(model_name)
        return self._model


_cache = _EmbeddingCache()


def _get_model():
    """Return the loaded SentenceTransformer model, or None if unavailable."""
    if not _SENTENCE_TRANSFORMERS_AVAILABLE:
        return None
    from backend.core.config import settings
    return _cache.get_model(settings.SKILL_EMBEDDING_MODEL)


# ─── per-process skill embedding LRU ─────────────────────────────────────────

@lru_cache(maxsize=2048)
def _embed_skill(skill_text: str, model_name: str):
    """Compute and cache the embedding for a single normalised skill string.

    Parameters are tuple-hashable so lru_cache works.  ``model_name`` is
    included so that the cache is invalidated when the model changes.

    Returns a 1-D numpy array, or None on failure.
    """
    model = _cache.get_model(model_name)
    if model is None:
        return None
    try:
        vec = model.encode(skill_text, normalize_embeddings=True, show_progress_bar=False)
        return vec
    except Exception as exc:
        logger.debug("[SKILL_EMB] Encoding failed for %r: %s", skill_text, exc)
        return None


def _cosine(a, b) -> float:
    """Cosine similarity of two normalised (unit) vectors."""
    # Both are already L2-normalised by encode(normalize_embeddings=True)
    return float(np.dot(a, b))  # type: ignore[union-attr]


# ─── public API ───────────────────────────────────────────────────────────────

def embedding_skill_similarity(skill_a: str, skill_b: str) -> float:
    """Return cosine similarity (0.0–1.0) between two skill strings.

    Returns 0.0 if:
    - sentence-transformers is not installed
    - either skill is empty
    - embedding fails for any reason

    The function uses an per-process LRU cache so that repeatedly comparing
    the same skills (very common in batch scoring) is essentially free.
    """
    if not _SENTENCE_TRANSFORMERS_AVAILABLE:
        return 0.0
    if not skill_a or not skill_b:
        return 0.0

    sa = skill_a.lower().strip()
    sb = skill_b.lower().strip()
    if sa == sb:
        return 1.0

    from backend.core.config import settings
    model_name = settings.SKILL_EMBEDDING_MODEL

    vec_a = _embed_skill(sa, model_name)
    vec_b = _embed_skill(sb, model_name)
    if vec_a is None or vec_b is None:
        return 0.0

    return max(0.0, min(1.0, _cosine(vec_a, vec_b)))


def best_embedding_match(
    query_skill: str,
    candidate_skills: List[str],
    threshold: float = 0.65,
) -> float:
    """Return the best cosine similarity of *query_skill* against all *candidate_skills*.

    Returns 0.0 if nothing exceeds *threshold*.
    """
    if not _SENTENCE_TRANSFORMERS_AVAILABLE or not query_skill or not candidate_skills:
        return 0.0

    best = 0.0
    for cs in candidate_skills:
        if not cs:
            continue
        sim = embedding_skill_similarity(query_skill, cs)
        if sim > best:
            best = sim
    return best if best >= threshold else 0.0


def embedding_skills_score(
    job_skills: List[str],
    profile_skills: List[str],
    threshold: float = 0.65,
) -> float:
    """Weighted semantic skill overlap using embeddings only (0.0–1.0).

    For each job_skill, finds the best-matching profile_skill by cosine
    similarity.  Skills below *threshold* are treated as no-match.

    This is called as a **fallback tier** inside ``semantic_skills_score()``
    after the taxonomy tiers have already been tried.

    Returns 0.0 if either list is empty or the library is unavailable.
    """
    if not _SENTENCE_TRANSFORMERS_AVAILABLE:
        return 0.0
    if not job_skills or not profile_skills:
        return 0.0

    total = 0.0
    matched = 0.0

    for js in job_skills:
        if not js:
            continue
        total += 1.0
        best = best_embedding_match(js, profile_skills, threshold=threshold)
        matched += best  # already 0.0 if below threshold

    return matched / total if total > 0 else 0.0


def preload_taxonomy_embeddings(taxonomy_skills: List[str], model_name: str = "") -> None:
    """Eagerly embed all taxonomy skill names to fill the LRU cache on startup.

    Call once at application startup after the taxonomy is loaded so that the
    first scoring request doesn't pay the model-load penalty.
    """
    if not _SENTENCE_TRANSFORMERS_AVAILABLE:
        return
    if not model_name:
        from backend.core.config import settings
        model_name = settings.SKILL_EMBEDDING_MODEL
    model = _cache.get_model(model_name)
    if model is None:
        return
    for skill in taxonomy_skills:
        if skill:
            _embed_skill(skill.lower().strip(), model_name)
    logger.info("[SKILL_EMB] Pre-loaded %d taxonomy skill embeddings.", len(taxonomy_skills))
