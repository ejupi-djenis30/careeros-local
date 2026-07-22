from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.ai import match_evidence
from backend.ai.attestation import MatchAttestationError, validate_match_attestation
from backend.ai.audit import fingerprint_output
from backend.ai.contracts import JobMatchResult, ValidationCode
from backend.ai.grounding import validate_grounding
from backend.ai.match_evidence import (
    candidate_evidence_document,
    job_evidence_document,
    match_input_fingerprint,
    match_quote_bindings,
)
from backend.ai.match_policy import (
    derive_match_outcome,
    derive_match_presentation,
    enforce_match_score_policy,
)
from backend.ai.matching import _materialize_match_citations
from backend.ai.retrieval import EvidenceDocument, retrieve_evidence

DIMENSIONS = (
    "skill",
    "experience",
    "intent",
    "language",
    "location",
    "transferability",
    "qualification",
)
SCORE_FIELDS = {
    "skill": "skill_match_score",
    "experience": "experience_match_score",
    "intent": "intent_match_score",
    "language": "language_match_score",
    "location": "location_match_score",
    "transferability": "transferability_score",
    "qualification": "qualification_gap_score",
}


def _payload(scores: dict[str, int], citations: list[dict] | None = None) -> JobMatchResult:
    _ = citations
    row = {field: scores.get(dimension, 50) for dimension, field in SCORE_FIELDS.items()}
    return JobMatchResult.model_validate({"results": [row]})


def _citation(dimension: str, *, row: int = 0, quote: int = 0) -> dict[str, str]:
    return {
        "type": dimension,
        "job_evidence_id": f"job:{row}",
        "candidate_evidence_id": "candidate:profile",
        "job_quote_id": f"job:{row}:{dimension}:{quote}",
        "candidate_quote_id": f"candidate:profile:{dimension}:{quote}",
    }


def test_atomic_catalog_preserves_later_skills_and_fits_three_job_batch() -> None:
    long_cv = " ".join(f"Background sentence {index}." for index in range(30))
    long_cv += " Later I shipped production Python and FastAPI services."
    candidate = candidate_evidence_document(
        {
            "cv_content": long_cv,
            "role_description": "Backend Engineer",
            "search_strategy": "Python platform roles",
        }
    )
    jobs = [
        job_evidence_document(
            {
                "title": "Backend Engineer",
                "description": (
                    "General platform context. Later the role requires production Python "
                    "and FastAPI services. Fluent English C1. Based in Zurich."
                ),
                "location": "Zurich",
            },
            index,
            description_limit=400,
        )
        for index in range(3)
    ]

    bundle = retrieve_evidence(
        "job match",
        (candidate, *jobs),
        max_context_chars=12_000,
        require_all=True,
    )

    candidate_python_ids = [
        quote_id
        for quote_id, quote in candidate.validation_metadata["quotes"].items()
        if "Python" in quote["text"]
    ]
    assert candidate_python_ids
    assert any(quote_id in bundle.context for quote_id in candidate_python_ids)
    assert len(bundle.context) <= 12_000
    assert bundle.truncated is False
    assert all(len(document.text) <= 2_700 for document in (candidate, *jobs))


def test_dense_sentence_keeps_complete_dimension_quotes_within_budget() -> None:
    dense = (
        "We require a senior software engineer with eight years experience, fluent German "
        "C1 and English C1, based in Zurich onsite, with a master degree in computer science "
        "and proven Python architecture leadership skills."
    )
    document = job_evidence_document(
        {"title": "Senior Engineer", "description": dense, "location": "Zurich"},
        0,
        description_limit=400,
    )
    quotes = document.validation_metadata["quotes"]

    assert {quote["dimension"] for quote in quotes.values()} == set(DIMENSIONS)
    assert any("Python architecture" in quote["text"] for quote in quotes.values())
    assert len(document.text) <= 2_700


def test_keyword_boundaries_do_not_invent_language_or_degree_evidence() -> None:
    document = job_evidence_document(
        {"description": "Built B2B products and mastered Python."},
        0,
        description_limit=1_800,
    )
    quotes = document.validation_metadata["quotes"]

    for dimension in ("language", "qualification"):
        quote = quotes[f"job:0:{dimension}:0"]
        assert quote["has_positive_evidence"] is False
        assert quote["text"].startswith("No explicit")


def test_missing_evidence_cannot_create_a_positive_match() -> None:
    candidate = candidate_evidence_document({})
    job = job_evidence_document({}, 0, description_limit=1_800)
    output = _payload(
        {dimension: 80 for dimension in DIMENSIONS},
        [_citation(dimension) for dimension in DIMENSIONS],
    )

    issues = validate_grounding(output, (candidate, job))

    assert ValidationCode.SEMANTIC_INVALID in {issue.code for issue in issues}


def test_one_sided_missing_evidence_allows_gap_but_rejects_strength() -> None:
    candidate = candidate_evidence_document({})
    job = job_evidence_document(
        {"description": "Production Python is required."},
        0,
        description_limit=1_800,
    )
    citation = [_citation("skill")]

    positive_issues = validate_grounding(
        _payload({"skill": 80}, citation),
        (candidate, job),
    )
    gap_issues = validate_grounding(
        _payload({"skill": 20, "transferability": 40}, citation),
        (candidate, job),
    )

    assert ValidationCode.SEMANTIC_INVALID in {issue.code for issue in positive_issues}
    assert gap_issues == []


def test_matching_quotes_reject_an_opposite_extreme_score() -> None:
    candidate = candidate_evidence_document({"cv_content": "Production Python services."})
    job = job_evidence_document(
        {"description": "Production Python services are required."},
        0,
        description_limit=1_800,
    )

    issues = validate_grounding(
        _payload({"skill": 1}, [_citation("skill")]),
        (candidate, job),
    )

    assert ValidationCode.SEMANTIC_INVALID in {issue.code for issue in issues}


def test_partial_word_overlap_does_not_turn_java_into_javascript() -> None:
    candidate = candidate_evidence_document({"cv_content": "JavaScript applications."})
    job = job_evidence_document(
        {"description": "Java applications are required."},
        0,
        description_limit=1_800,
    )

    issues = validate_grounding(
        _payload({"skill": 80}, [_citation("skill")]),
        (candidate, job),
    )

    assert ValidationCode.SEMANTIC_INVALID in {issue.code for issue in issues}


@pytest.mark.parametrize(
    "job_text",
    [
        "Python is not required.",
        "We do not use Python.",
        "Candidates must not know Python.",
        "Python is prohibited.",
    ],
)
def test_negative_job_polarity_cannot_support_a_positive_skill_score(job_text: str) -> None:
    candidate = candidate_evidence_document({"cv_content": "Five years of Python delivery."})
    job = job_evidence_document({"description": job_text}, 0, description_limit=1_800)

    issues = validate_grounding(
        _payload({"skill": 100}, [_citation("skill")]),
        (candidate, job),
    )

    assert ValidationCode.SEMANTIC_INVALID in {issue.code for issue in issues}


@pytest.mark.parametrize(
    ("dimension", "candidate_text", "job_text"),
    [
        ("experience", "2 years of Python experience.", "10 years of Python experience required."),
        ("language", "German B1.", "German C2 required."),
        ("qualification", "Bachelor degree.", "Master degree required."),
    ],
)
def test_typed_minimum_mismatch_caps_model_scores(
    dimension: str, candidate_text: str, job_text: str
) -> None:
    candidate = candidate_evidence_document({"cv_content": candidate_text})
    job = job_evidence_document({"description": job_text}, 0, description_limit=1_800)

    issues = validate_grounding(
        _payload({dimension: 100}, [_citation(dimension)]),
        (candidate, job),
    )

    assert ValidationCode.SEMANTIC_INVALID in {issue.code for issue in issues}


def test_language_score_requires_coverage_of_every_required_language() -> None:
    candidate = candidate_evidence_document({"cv_content": "English C1."})
    job = job_evidence_document(
        {"description": "English C1 and German C2 required."},
        0,
        description_limit=1_800,
    )

    issues = validate_grounding(
        _payload({"language": 100}, [_citation("language")]),
        (candidate, job),
    )

    assert ValidationCode.SEMANTIC_INVALID in {issue.code for issue in issues}


def test_neutral_model_score_cannot_omit_a_missing_mandatory_language() -> None:
    candidate = candidate_evidence_document({"cv_content": "English C1."})
    job = job_evidence_document(
        {"description": "German C2 required."},
        0,
        description_limit=1_800,
    )
    proposed = _payload({"language": 50}).model_dump(mode="json")

    enforced = enforce_match_score_policy(proposed, (candidate, job))

    assert enforced["results"][0]["language_match_score"] == 30


def test_long_candidate_profile_does_not_force_supported_skill_to_neutral() -> None:
    candidate = candidate_evidence_document(
        {"cv_content": "Python. Java. Go. Rust. Docker. FastAPI."}
    )
    job = job_evidence_document(
        {"description": "FastAPI"},
        0,
        description_limit=1_800,
    )
    proposed = _payload({"skill": 80}).model_dump(mode="json")

    enforced = enforce_match_score_policy(proposed, (candidate, job))

    assert candidate.validation_metadata["coverage_complete"]["skill"] is True
    assert enforced["results"][0]["skill_match_score"] == 80


@pytest.mark.parametrize(
    ("job_text", "required", "excluded"),
    [
        ("Python required, Java not required.", {"python"}, set()),
        ("Requires Python/does not use Java.", {"python"}, {"java"}),
    ],
)
def test_mixed_polarity_skill_clauses_are_bound_independently(
    job_text: str,
    required: set[str],
    excluded: set[str],
) -> None:
    summary = job_evidence_document(
        {"description": job_text}, 0, description_limit=1_800
    ).validation_metadata["requirement_summary"]

    assert set(summary["required_skill_terms"]) == required
    assert set(summary["excluded_skill_terms"]) == excluded


def test_optional_language_clause_does_not_become_mandatory() -> None:
    summary = job_evidence_document(
        {"description": "German C2 required/English optional."},
        0,
        description_limit=1_800,
    ).validation_metadata["requirement_summary"]

    assert summary["required_languages"] == {"german": 6}


@pytest.mark.parametrize(("candidate_text", "rank"), [("Fluent German", 5), ("Native German", 7)])
def test_language_words_have_conservative_server_ranks(candidate_text: str, rank: int) -> None:
    summary = candidate_evidence_document({"cv_content": candidate_text}).validation_metadata[
        "requirement_summary"
    ]

    assert summary["observed_languages"]["german"] == rank


@pytest.mark.parametrize(
    "candidate_text",
    [
        "I do not know Python.",
        "No experience with Python.",
        "I never used Python.",
        "Worked without Python.",
    ],
)
def test_candidate_negation_never_supports_a_skill_strength(candidate_text: str) -> None:
    candidate = candidate_evidence_document({"cv_content": candidate_text})
    job = job_evidence_document(
        {"description": "Python required."},
        0,
        description_limit=1_800,
    )
    proposed = _payload({"skill": 100}).model_dump(mode="json")

    enforced = enforce_match_score_policy(proposed, (candidate, job))

    assert (
        "python" not in candidate.validation_metadata["requirement_summary"]["observed_skill_terms"]
    )
    assert enforced["results"][0]["skill_match_score"] <= 40


@pytest.mark.parametrize(
    ("required_clause", "preferred_clause", "optional_clause", "excluded_clause"),
    [
        (
            "Python is required.",
            "Python is preferred.",
            "Python is optional.",
            "Python is prohibited.",
        ),
        (
            "Python ist erforderlich.",
            "Python ist wünschenswert.",
            "Python ist optional.",
            "Python darf nicht verwendet werden.",
        ),
        (
            "Python est requis.",
            "Python est souhaité.",
            "Python est facultatif.",
            "Python est interdit.",
        ),
        (
            "Python è richiesto.",
            "Python è preferibile.",
            "Python è opzionale.",
            "Python è vietato.",
        ),
    ],
    ids=("english", "german", "french", "italian"),
)
def test_multilingual_skill_polarity_controls_server_caps(
    required_clause: str,
    preferred_clause: str,
    optional_clause: str,
    excluded_clause: str,
) -> None:
    missing_candidate = candidate_evidence_document({"cv_content": "Java."})
    present_candidate = candidate_evidence_document({"cv_content": "Python."})
    proposal = _payload({"skill": 100, "transferability": 100}).model_dump(mode="json")

    def scores(candidate: EvidenceDocument, clause: str) -> dict[str, int]:
        job = job_evidence_document({"description": clause}, 0, description_limit=1_800)
        return enforce_match_score_policy(proposal, (candidate, job))["results"][0]

    assert scores(missing_candidate, required_clause)["skill_match_score"] <= 40
    assert scores(present_candidate, required_clause)["skill_match_score"] == 100
    assert scores(missing_candidate, preferred_clause)["skill_match_score"] <= 55
    assert scores(missing_candidate, optional_clause)["skill_match_score"] == 50
    assert scores(present_candidate, optional_clause)["skill_match_score"] == 50
    assert scores(present_candidate, excluded_clause)["skill_match_score"] <= 40


@pytest.mark.parametrize(
    ("candidate_text", "job_text"),
    [
        (
            "Python. Two years of experience. English B1. Bachelor degree.",
            "Python is required. At least five years of experience are required. "
            "English C1 is required. A Master degree is required.",
        ),
        (
            "Python. Zwei Jahre Berufserfahrung. Deutsch B1. Bachelorabschluss.",
            "Python ist erforderlich. Mindestens fünf Jahre Berufserfahrung sind "
            "erforderlich. Deutsch C1 ist erforderlich. Masterabschluss ist erforderlich.",
        ),
        (
            "Python. Deux ans d’expérience. Français B1. Licence.",
            "Python est requis. Au moins cinq ans d’expérience sont requis. "
            "Français C1 est requis. Un master est requis.",
        ),
        (
            "Python. Due anni di esperienza. Italiano B1. Laurea triennale.",
            "Python è richiesto. Almeno cinque anni di esperienza sono richiesti. "
            "Italiano C1 è richiesto. Una laurea magistrale è richiesta.",
        ),
    ],
    ids=("english", "german", "french", "italian"),
)
def test_multilingual_typed_mismatches_cap_and_risk_the_outcome(
    candidate_text: str,
    job_text: str,
) -> None:
    candidate = candidate_evidence_document(
        {
            "cv_content": candidate_text,
            "role_description": "Backend Engineer",
            "location_filter": "Zurich",
        }
    )
    job = job_evidence_document(
        {
            "title": "Backend Engineer",
            "description": job_text,
            "location": "Zurich",
        },
        0,
        description_limit=1_800,
    )
    proposal = _payload({dimension: 100 for dimension in DIMENSIONS}).model_dump(mode="json")

    row = enforce_match_score_policy(proposal, (candidate, job))["results"][0]
    scores = {dimension: row[field] for dimension, field in SCORE_FIELDS.items()}
    citations = _materialize_match_citations(
        candidate=candidate,
        job=job,
        dimension_scores=scores,
    )
    affinity, recommendation, worth = derive_match_outcome(scores, citations)
    risk_types = {citation["type"] for citation in citations if citation["assessment"] == "risk"}

    assert row["experience_match_score"] == 40
    assert row["language_match_score"] == 30
    assert row["qualification_gap_score"] == 40
    assert {"language", "qualification"} <= risk_types
    assert affinity <= 30
    assert recommendation == "weak_fit"
    assert worth is False


@pytest.mark.parametrize(
    "candidate_text",
    [
        "I don't know Python.",
        "I haven't used Python.",
        "I lack Python experience.",
        "Ich kenne Python nicht.",
        "Je ne connais pas Python.",
        "Non conosco Python.",
    ],
    ids=(
        "english-contraction",
        "english-havent",
        "english-lack",
        "german",
        "french",
        "italian",
    ),
)
def test_multilingual_candidate_negation_is_never_observed_positive(
    candidate_text: str,
) -> None:
    candidate = candidate_evidence_document({"cv_content": candidate_text})
    job = job_evidence_document({"description": "Python is required."}, 0, description_limit=1_800)
    proposal = _payload({"skill": 100}).model_dump(mode="json")

    row = enforce_match_score_policy(proposal, (candidate, job))["results"][0]
    summary = candidate.validation_metadata["requirement_summary"]

    assert "python" not in summary["observed_skill_terms"]
    assert "python" in summary["negated_skill_terms"]
    assert row["skill_match_score"] <= 40


@pytest.mark.parametrize(
    ("candidate_text", "job_text"),
    [
        ("Two years of experience.", "Five years of experience required."),
        ("Zwei Jahre Berufserfahrung.", "Fünf Jahre Berufserfahrung erforderlich."),
        ("Deux ans d’expérience.", "Cinq ans d’expérience requis."),
        ("Due anni di esperienza.", "Cinque anni di esperienza richiesti."),
    ],
    ids=("english", "german", "french", "italian"),
)
def test_multilingual_tenure_prose_does_not_become_skill_evidence(
    candidate_text: str,
    job_text: str,
) -> None:
    candidate = candidate_evidence_document({"cv_content": candidate_text})
    job = job_evidence_document({"description": job_text}, 0, description_limit=1_800)
    proposal = _payload({"skill": 100, "transferability": 100}).model_dump(mode="json")

    row = enforce_match_score_policy(proposal, (candidate, job))["results"][0]

    assert candidate.validation_metadata["requirement_summary"]["observed_skill_terms"] == []
    assert job.validation_metadata["requirement_summary"]["required_skill_terms"] == []
    assert row["skill_match_score"] == 50
    assert row["transferability_score"] == 50


@pytest.mark.parametrize(
    ("job_text", "required", "preferred"),
    [
        ("Python required and Java optional.", {"python"}, set()),
        ("Python required and Java preferred.", {"python"}, {"java"}),
        ("Python erforderlich und Java optional.", {"python"}, set()),
        ("Python requis et Java facultatif.", {"python"}, set()),
        ("Python richiesto e Java opzionale.", {"python"}, set()),
    ],
)
def test_mixed_polarity_conjunctions_remain_independent(
    job_text: str,
    required: set[str],
    preferred: set[str],
) -> None:
    summary = job_evidence_document(
        {"description": job_text}, 0, description_limit=1_800
    ).validation_metadata["requirement_summary"]

    assert set(summary["required_skill_terms"]) == required
    assert set(summary["preferred_skill_terms"]) == preferred


@pytest.mark.parametrize(
    "job_text",
    [
        "Python or Java is required.",
        "Python oder Java ist erforderlich.",
        "Python ou Java est requis.",
        "Python o Java è richiesto.",
    ],
    ids=("english", "german", "french", "italian"),
)
def test_multilingual_required_alternatives_accept_any_member(job_text: str) -> None:
    job = job_evidence_document({"description": job_text}, 0, description_limit=1_800)
    proposal = _payload({"skill": 100, "transferability": 100}).model_dump(mode="json")
    summary = job.validation_metadata["requirement_summary"]

    assert summary["required_skill_groups"] == [["java", "python"]]
    for candidate_text in ("Python.", "Java."):
        candidate = candidate_evidence_document({"cv_content": candidate_text})
        row = enforce_match_score_policy(proposal, (candidate, job))["results"][0]
        assert row["skill_match_score"] == 100


@pytest.mark.parametrize(
    "job_text",
    [
        "Python isn't required.",
        "Candidates do not have to know Python.",
        "No Python experience needed.",
    ],
)
def test_natural_not_required_phrases_remain_neutral(job_text: str) -> None:
    job = job_evidence_document({"description": job_text}, 0, description_limit=1_800)
    proposal = _payload({"skill": 100}).model_dump(mode="json")

    for candidate_text in ("Python.", "Java."):
        candidate = candidate_evidence_document({"cv_content": candidate_text})
        row = enforce_match_score_policy(proposal, (candidate, job))["results"][0]
        assert row["skill_match_score"] == 50


def test_unrelated_without_does_not_negate_candidate_skill() -> None:
    candidate = candidate_evidence_document(
        {"cv_content": "Built Python services without direct supervision."}
    )
    job = job_evidence_document({"description": "Python is required."}, 0, description_limit=1_800)
    proposal = _payload({"skill": 100}).model_dump(mode="json")

    row = enforce_match_score_policy(proposal, (candidate, job))["results"][0]
    summary = candidate.validation_metadata["requirement_summary"]

    assert "python" in summary["observed_skill_terms"]
    assert "python" not in summary["negated_skill_terms"]
    assert row["skill_match_score"] == 100


def test_comma_exclusion_marker_applies_to_every_list_member() -> None:
    job = job_evidence_document(
        {"description": "Python, Java are prohibited."}, 0, description_limit=1_800
    )
    summary = job.validation_metadata["requirement_summary"]

    assert set(summary["excluded_skill_terms"]) == {"java", "python"}


@pytest.mark.parametrize(
    "job_text",
    [
        "Python is mandatory.",
        "Python is a must.",
        "Strong proficiency in Python is required.",
        "Requirements: Python.",
    ],
)
def test_requirement_scaffolding_never_becomes_a_mandatory_skill(job_text: str) -> None:
    job = job_evidence_document({"description": job_text}, 0, description_limit=1_800)
    summary = job.validation_metadata["requirement_summary"]

    assert summary["required_skill_terms"] == ["python"]
    assert summary["required_skill_groups"] == [["python"]]


@pytest.mark.parametrize(
    ("candidate_text", "language", "rank"),
    [
        ("English native.", "english", 7),
        ("Deutsch muttersprachlich.", "german", 7),
        ("Français langue maternelle.", "french", 7),
        ("Italiano madrelingua.", "italian", 7),
        ("Deutsch fließend.", "german", 5),
        ("Français courant.", "french", 5),
        ("Italiano fluente.", "italian", 5),
    ],
)
def test_localized_fluent_and_native_language_levels(
    candidate_text: str,
    language: str,
    rank: int,
) -> None:
    summary = candidate_evidence_document({"cv_content": candidate_text}).validation_metadata[
        "requirement_summary"
    ]

    assert summary["observed_languages"][language] == rank


def test_comma_no_clause_excludes_only_its_own_skill() -> None:
    job = job_evidence_document(
        {"description": "Python is required, no Java."}, 0, description_limit=1_800
    )
    summary = job.validation_metadata["requirement_summary"]

    assert summary["required_skill_terms"] == ["python"]
    assert summary["excluded_skill_terms"] == ["java"]


def test_descriptive_positive_attributes_can_support_match_scores() -> None:
    candidate = candidate_evidence_document(
        {
            "cv_content": "Python FastAPI Docker. Based in Zurich.",
            "role_description": "Backend Engineer",
        }
    )
    job = job_evidence_document(
        {
            "title": "Backend Engineer",
            "description": "Python FastAPI Docker",
            "location": "Zurich",
        },
        0,
        description_limit=1_800,
    )
    proposed = _payload({"skill": 80, "intent": 80, "location": 80}).model_dump(mode="json")

    enforced = enforce_match_score_policy(proposed, (candidate, job))
    row = enforced["results"][0]

    assert row["skill_match_score"] == 80
    assert row["intent_match_score"] == 80
    assert row["location_match_score"] == 80


def test_natural_strong_profile_is_not_capped_by_typed_requirement_words() -> None:
    candidate = candidate_evidence_document(
        {
            "cv_content": (
                "Python FastAPI Docker. Six years of backend experience. "
                "German C1. Bachelor degree."
            ),
            "role_description": "Backend Engineer",
            "search_strategy": "Backend roles",
            "location_filter": "Zurich",
        }
    )
    job = job_evidence_document(
        {
            "title": "Backend Engineer",
            "description": (
                "Python, FastAPI and Docker are required. At least 5 years experience "
                "required. German B2 and a bachelor degree are required."
            ),
            "location": "Zurich",
        },
        0,
        description_limit=1_800,
    )
    proposal = _payload({dimension: 90 for dimension in DIMENSIONS}).model_dump(mode="json")

    enforced = enforce_match_score_policy(proposal, (candidate, job))
    row = enforced["results"][0]
    summary = job.validation_metadata["requirement_summary"]
    citations = _materialize_match_citations(
        candidate=candidate,
        job=job,
        dimension_scores={dimension: row[field] for dimension, field in SCORE_FIELDS.items()},
    )
    affinity, recommendation, worth = derive_match_outcome(
        {dimension: row[field] for dimension, field in SCORE_FIELDS.items()},
        citations,
    )

    assert summary["required_skill_terms"] == ["docker", "fastapi", "python"]
    assert row == {field: 90 for field in SCORE_FIELDS.values()}
    assert any(
        citation["type"] == "location"
        and citation["candidate_evidence"] == "Preferred Location: Zurich."
        for citation in citations
    )
    assert not any(
        citation["type"] in {"skill", "intent", "transferability"}
        and any(
            typed in citation["job_evidence"].casefold()
            for typed in ("german", "bachelor", "5 years")
        )
        for citation in citations
    )
    assert (affinity, recommendation, worth) == (90, "strong_fit", True)


def test_long_unsplittable_requirement_is_checked_outside_prompt_projection() -> None:
    long_requirement = "Python " + "very-specialized-platform-context " * 9 + "is required."
    assert len(long_requirement) > 240
    candidate = candidate_evidence_document({"cv_content": "Python platform delivery."})
    job = job_evidence_document(
        {"description": long_requirement},
        0,
        description_limit=1_800,
    )

    assert job.validation_metadata["coverage_complete"]["skill"] is True
    issues = validate_grounding(
        _payload({"skill": 100}, [_citation("skill")]),
        (candidate, job),
    )

    assert ValidationCode.SEMANTIC_INVALID in {issue.code for issue in issues}


def test_more_than_four_explicit_requirements_cannot_be_cherry_picked() -> None:
    requirements = [f"Technology{i} is required." for i in range(5)]
    candidate = candidate_evidence_document({"cv_content": "Technology0 delivery."})
    job = job_evidence_document(
        {"description": " ".join(requirements)},
        0,
        description_limit=1_800,
    )

    assert job.validation_metadata["coverage_complete"]["skill"] is True
    assert len(job.validation_metadata["requirement_summary"]["required_skill_terms"]) >= 5
    issues = validate_grounding(
        _payload({"skill": 100}, [_citation("skill")]),
        (candidate, job),
    )

    assert ValidationCode.SEMANTIC_INVALID in {issue.code for issue in issues}


def test_same_source_pair_cannot_count_as_two_independent_strengths() -> None:
    def document(document_id: str, kind: str) -> EvidenceDocument:
        quotes = {
            f"{document_id}:{dimension}:0": {
                "dimension": dimension,
                "has_positive_evidence": True,
                "requirement_status": "present",
                "text": "Python delivery evidence",
                "text_hash": "a" * 64,
            }
            for dimension in DIMENSIONS
        }
        return EvidenceDocument(
            id=document_id,
            kind=kind,
            text="\n".join(quotes),
            validation_metadata={"quotes": quotes},
        )

    output = _payload(
        {dimension: 100 for dimension in DIMENSIONS},
        [_citation(dimension) for dimension in DIMENSIONS],
    )
    issues = validate_grounding(
        output,
        (document("candidate:profile", "candidate"), document("job:0", "job")),
    )

    assert ValidationCode.SEMANTIC_INVALID in {issue.code for issue in issues}


def test_catalog_version_is_bound_into_the_input_fingerprint(monkeypatch) -> None:
    profile = {"cv_content": "Python services."}
    listing = {"description": "Python services are required."}
    candidate_v2 = candidate_evidence_document(profile)
    job_v2 = job_evidence_document(listing, 0, description_limit=400)
    fingerprint_v2 = match_input_fingerprint(candidate_v2, job_v2)

    monkeypatch.setattr(match_evidence, "MATCH_EVIDENCE_CATALOG_VERSION", "6")
    candidate_v3 = candidate_evidence_document(profile)
    job_v3 = job_evidence_document(listing, 0, description_limit=400)

    assert match_input_fingerprint(candidate_v3, job_v3) != fingerprint_v2


def test_server_materializes_risk_caps_from_missing_required_evidence() -> None:
    candidate = candidate_evidence_document({})
    job = job_evidence_document(
        {
            "title": "German-speaking Analyst",
            "description": "German C1 and a bachelor degree are required.",
        },
        0,
        description_limit=1_800,
    )
    scores = {dimension: 50 for dimension in DIMENSIONS}
    scores.update({"intent": 20, "language": 30, "qualification": 40})
    materialized = _materialize_match_citations(
        candidate=candidate,
        job=job,
        dimension_scores=scores,
    )
    affinity, recommendation, worth_applying = derive_match_outcome(scores, materialized)
    summary, flags = derive_match_presentation(recommendation, materialized)

    risk_citations = [
        citation
        for citation in materialized
        if citation["type"] in {"intent", "language", "qualification"}
    ]
    assert [citation["assessment"] for citation in risk_citations] == ["risk"] * 3
    assert affinity == 20
    assert recommendation == "weak_fit"
    assert worth_applying is False
    assert "3 risk signal(s)" in summary
    assert flags == [
        "evidence_risk:intent",
        "evidence_risk:language",
        "evidence_risk:qualification",
    ]


def test_attestation_rejects_tampered_materialized_quote_text() -> None:
    candidate = candidate_evidence_document({"cv_content": "Python delivery."})
    job = job_evidence_document(
        {"description": "Python delivery is required."},
        0,
        description_limit=1_800,
    )
    scores = {dimension: 50 for dimension in DIMENSIONS}
    scores["skill"] = 70
    citations = _materialize_match_citations(
        candidate=candidate,
        job=job,
        dimension_scores=scores,
    )
    raw_row = {field: scores[dimension] for dimension, field in SCORE_FIELDS.items()}
    row_fingerprint = fingerprint_output(raw_row)
    affinity, recommendation, worth = derive_match_outcome(scores, citations)
    summary, flags = derive_match_presentation(recommendation, citations)
    execution_id = str(uuid4())
    input_fingerprint = match_input_fingerprint(candidate, job)
    output_fingerprint = "b" * 64
    analysis = {
        **raw_row,
        "affinity_score": affinity,
        "affinity_analysis": summary,
        "worth_applying": worth,
        "analysis_structured": {
            "recommendation": recommendation,
            "evidence_citations": citations,
        },
        "red_flags": flags,
        "analysis_provenance": "local_model_validated",
        "analysis_model_id": "ollama/test-model",
        "analysis_contract_version": "1.1.0",
        "analysis_validated_at": "2026-07-22T20:00:00Z",
        "analysis_execution_id": execution_id,
        "analysis_output_fingerprint": output_fingerprint,
        "analysis_execution_row_index": 0,
        "analysis_row_fingerprint": row_fingerprint,
        "analysis_input_fingerprint": input_fingerprint,
    }
    execution = SimpleNamespace(
        id=execution_id,
        user_id=7,
        task="job_match",
        accepted=True,
        model_id="ollama/test-model",
        contract_version="1.1.0",
        output_fingerprint=output_fingerprint,
        row_fingerprints=[row_fingerprint],
        row_input_fingerprints=[input_fingerprint],
    )
    bindings = match_quote_bindings(candidate, job)

    validate_match_attestation(
        analysis,
        execution,
        expected_user_id=7,
        expected_input_fingerprint=input_fingerprint,
        expected_quote_bindings=bindings,
        expected_citations=citations,
    )
    tampered = deepcopy(analysis)
    tampered["analysis_structured"]["evidence_citations"][0]["job_evidence"] = "Invented evidence"

    with pytest.raises(MatchAttestationError, match="server-materialized"):
        validate_match_attestation(
            tampered,
            execution,
            expected_user_id=7,
            expected_input_fingerprint=input_fingerprint,
            expected_quote_bindings=bindings,
            expected_citations=citations,
        )


def test_attestation_rejects_tampered_materialized_assessment_and_display() -> None:
    candidate = candidate_evidence_document({"cv_content": "Python delivery."})
    job = job_evidence_document(
        {"description": "Python delivery is required."},
        0,
        description_limit=1_800,
    )
    scores = {dimension: 50 for dimension in DIMENSIONS}
    scores["skill"] = 70
    citations = _materialize_match_citations(
        candidate=candidate,
        job=job,
        dimension_scores=scores,
    )
    assert citations[0]["assessment"] == "strength"
    raw_row = {field: scores[dimension] for dimension, field in SCORE_FIELDS.items()}
    row_fingerprint = fingerprint_output(raw_row)
    affinity, recommendation, worth = derive_match_outcome(scores, citations)
    summary, flags = derive_match_presentation(recommendation, citations)
    execution_id = str(uuid4())
    input_fingerprint = match_input_fingerprint(candidate, job)
    output_fingerprint = "b" * 64
    analysis = {
        **raw_row,
        "affinity_score": affinity,
        "affinity_analysis": summary,
        "worth_applying": worth,
        "analysis_structured": {
            "recommendation": recommendation,
            "evidence_citations": citations,
        },
        "red_flags": flags,
        "analysis_provenance": "local_model_validated",
        "analysis_model_id": "ollama/test-model",
        "analysis_contract_version": "1.1.0",
        "analysis_validated_at": "2026-07-22T20:00:00Z",
        "analysis_execution_id": execution_id,
        "analysis_output_fingerprint": output_fingerprint,
        "analysis_execution_row_index": 0,
        "analysis_row_fingerprint": row_fingerprint,
        "analysis_input_fingerprint": input_fingerprint,
    }
    execution = SimpleNamespace(
        id=execution_id,
        user_id=7,
        task="job_match",
        accepted=True,
        model_id="ollama/test-model",
        contract_version="1.1.0",
        output_fingerprint=output_fingerprint,
        row_fingerprints=[row_fingerprint],
        row_input_fingerprints=[input_fingerprint],
    )
    bindings = match_quote_bindings(candidate, job)

    validate_match_attestation(
        analysis,
        execution,
        expected_user_id=7,
        expected_input_fingerprint=input_fingerprint,
        expected_quote_bindings=bindings,
        expected_citations=citations,
    )

    tampered = deepcopy(analysis)
    tampered_citations = tampered["analysis_structured"]["evidence_citations"]
    tampered_citations[0]["assessment"] = "risk"
    tampered_affinity, tampered_recommendation, tampered_worth = derive_match_outcome(
        scores, tampered_citations
    )
    tampered_summary, tampered_flags = derive_match_presentation(
        tampered_recommendation, tampered_citations
    )
    tampered["affinity_score"] = tampered_affinity
    tampered["worth_applying"] = tampered_worth
    tampered["analysis_structured"]["recommendation"] = tampered_recommendation
    tampered["affinity_analysis"] = tampered_summary
    tampered["red_flags"] = tampered_flags

    assert tampered["analysis_row_fingerprint"] == analysis["analysis_row_fingerprint"]
    assert tampered["analysis_output_fingerprint"] == analysis["analysis_output_fingerprint"]
    assert tampered["analysis_input_fingerprint"] == analysis["analysis_input_fingerprint"]
    with pytest.raises(MatchAttestationError, match="server-materialized"):
        validate_match_attestation(
            tampered,
            execution,
            expected_user_id=7,
            expected_input_fingerprint=input_fingerprint,
            expected_quote_bindings=bindings,
            expected_citations=citations,
        )
