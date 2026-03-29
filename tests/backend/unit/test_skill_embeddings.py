"""Unit tests for backend/services/search/skill_embeddings.py.

Covers the graceful-degradation path when sentence-transformers is NOT
installed (the standard test environment) as well as the public API contracts.
"""

from unittest.mock import patch

# ─── is_available ─────────────────────────────────────────────────────────────


class TestIsAvailable:
    def test_is_available_returns_bool(self):
        from backend.services.search.skill_embeddings import is_available

        result = is_available()
        assert isinstance(result, bool)

    def test_is_available_false_when_import_missing(self):
        """Simulate sentence-transformers not installed."""
        import backend.services.search.skill_embeddings as mod

        original = mod._SENTENCE_TRANSFORMERS_AVAILABLE
        try:
            mod._SENTENCE_TRANSFORMERS_AVAILABLE = False
            assert mod.is_available() is False
        finally:
            mod._SENTENCE_TRANSFORMERS_AVAILABLE = original


# ─── embedding_skill_similarity — unavailable path ────────────────────────────


class TestEmbeddingSkillSimilarityUnavailable:
    """Tests the fast-return paths that don't need the actual model."""

    def _with_unavailable(self):
        import backend.services.search.skill_embeddings as mod

        return patch.object(mod, "_SENTENCE_TRANSFORMERS_AVAILABLE", False)

    def test_returns_zero_when_library_unavailable(self):
        from backend.services.search.skill_embeddings import embedding_skill_similarity

        with self._with_unavailable():
            result = embedding_skill_similarity("Python", "Python programming")
        assert result == 0.0

    def test_returns_zero_for_empty_skill_a(self):
        from backend.services.search.skill_embeddings import embedding_skill_similarity

        with self._with_unavailable():
            result = embedding_skill_similarity("", "Python")
        assert result == 0.0

    def test_returns_zero_for_empty_skill_b(self):
        from backend.services.search.skill_embeddings import embedding_skill_similarity

        with self._with_unavailable():
            result = embedding_skill_similarity("Python", "")
        assert result == 0.0

    def test_returns_zero_for_both_empty(self):
        from backend.services.search.skill_embeddings import embedding_skill_similarity

        with self._with_unavailable():
            result = embedding_skill_similarity("", "")
        assert result == 0.0

    def test_identical_skills_returns_one_when_available(self):
        """When library IS available, identical (case-normalised) skills = 1.0."""
        import backend.services.search.skill_embeddings as mod

        original = mod._SENTENCE_TRANSFORMERS_AVAILABLE
        try:
            mod._SENTENCE_TRANSFORMERS_AVAILABLE = True
            result = mod.embedding_skill_similarity("python", "PYTHON")
            assert result == 1.0
        finally:
            mod._SENTENCE_TRANSFORMERS_AVAILABLE = original


# ─── EmbeddingCache singleton ─────────────────────────────────────────────────


class TestEmbeddingCacheSingleton:
    def test_singleton_returns_same_instance(self):
        from backend.services.search.skill_embeddings import _EmbeddingCache

        a = _EmbeddingCache()
        b = _EmbeddingCache()
        assert a is b

    def test_get_model_returns_none_when_unavailable(self):
        import backend.services.search.skill_embeddings as mod

        original = mod._SENTENCE_TRANSFORMERS_AVAILABLE
        try:
            mod._SENTENCE_TRANSFORMERS_AVAILABLE = False
            cache = mod._EmbeddingCache()
            model = cache.get_model("some-model")
            assert model is None
        finally:
            mod._SENTENCE_TRANSFORMERS_AVAILABLE = original
