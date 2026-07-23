from backend.services.search.skill_embeddings import (
    best_embedding_match,
    embedding_skill_similarity,
    embedding_skills_score,
    is_available,
)


def test_deterministic_skill_similarity_is_always_available():
    assert is_available() is True


def test_identical_skills_match_after_normalization():
    assert embedding_skill_similarity("Python", " python ") == 1.0
    assert embedding_skill_similarity("", "Python") == 0.0


def test_related_lexical_skill_names_match_without_a_model():
    assert embedding_skill_similarity("project management", "project-management") == 1.0
    assert best_embedding_match("React JS", ["Java", "ReactJS"], threshold=0.6) >= 0.6


def test_skill_score_is_reproducible_and_bounded():
    score = embedding_skills_score(
        ["Python", "React"],
        ["python", "ReactJS", "SQL"],
        threshold=0.6,
    )
    assert 0.5 <= score <= 1.0
