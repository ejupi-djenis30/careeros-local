import json
from datetime import datetime, timedelta, timezone

from backend.models import SearchProfile
from backend.repositories.profile_repository import ProfileRepository
from backend.search.receipt import (
    SEARCH_RECEIPT_MAX_COUNTER,
    SEARCH_RECEIPT_MAX_SERIALIZED_BYTES,
    build_search_completion_summary,
    normalize_search_completion_summary,
)


def _create_profile(db_session, test_user) -> SearchProfile:
    profile = SearchProfile(
        user_id=test_user.id,
        name="Durable receipt",
        role_description="Backend Engineer",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


def _terminal_payload(
    state: str,
    *,
    started_at: datetime,
    finished_at: datetime,
    jobs_found: int = 8,
) -> dict:
    return {
        "state": state,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "updated_at": finished_at.isoformat(),
        "total_searches": 3,
        "searches_completed": 3,
        "jobs_found": jobs_found,
        "jobs_new": 2,
        "jobs_unique": 5,
        "jobs_duplicates": 3,
        "jobs_skipped": 1,
        "jobs_analyzed": 4,
        "provider_successes": 2,
        "provider_failures": 1,
        "queries_without_provider": 1,
        "current_query": "private salary query",
        "searches_generated": [{"query": "private target employer"}],
        "analysis_targets": [{"description": "private listing text"}],
        "log": ["private CV-derived detail"],
        "error": "private provider response",
    }


def test_done_receipt_is_transactional_and_idempotent_for_the_same_run(db_session, test_user):
    profile = _create_profile(db_session, test_user)
    repo = ProfileRepository(db_session)
    started_at = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
    finished_at = started_at + timedelta(minutes=4)
    payload = _terminal_payload(
        "done",
        started_at=started_at,
        finished_at=finished_at,
    )

    assert repo.update_search_status(profile.id, payload) is True
    assert repo.update_search_status(profile.id, payload) is True

    db_session.expire_all()
    refreshed = db_session.get(SearchProfile, profile.id)
    assert refreshed.search_status_state == "done"
    assert refreshed.last_search_state == "done"
    assert refreshed.last_search_started_at == started_at
    assert refreshed.last_search_completed_at == finished_at
    assert refreshed.search_run_count == 1
    assert refreshed.last_search_summary["counts"]["jobs_found"] == 8
    assert refreshed.last_search_summary["providers"]["status"] == "partial"


def test_out_of_order_completion_cannot_regress_latest_receipt(db_session, test_user):
    profile = _create_profile(db_session, test_user)
    repo = ProfileRepository(db_session)
    older_start = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
    newer_start = older_start + timedelta(hours=1)

    assert repo.update_search_status(
        profile.id,
        _terminal_payload(
            "done",
            started_at=newer_start,
            finished_at=newer_start + timedelta(minutes=3),
            jobs_found=13,
        ),
    )
    assert repo.update_search_status(
        profile.id,
        _terminal_payload(
            "done",
            started_at=older_start,
            finished_at=newer_start + timedelta(minutes=5),
            jobs_found=2,
        ),
    )

    db_session.expire_all()
    refreshed = db_session.get(SearchProfile, profile.id)
    assert refreshed.search_run_count == 1
    assert refreshed.last_search_started_at == newer_start
    assert refreshed.last_search_completed_at == newer_start + timedelta(minutes=3)
    assert refreshed.last_search_summary["counts"]["jobs_found"] == 13


def test_failed_and_cancelled_runs_preserve_success_then_retry_increments(db_session, test_user):
    profile = _create_profile(db_session, test_user)
    repo = ProfileRepository(db_session)
    first_start = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)
    first_finish = first_start + timedelta(minutes=3)
    assert repo.update_search_status(
        profile.id,
        _terminal_payload("done", started_at=first_start, finished_at=first_finish),
    )
    db_session.expire_all()
    first_summary = dict(db_session.get(SearchProfile, profile.id).last_search_summary)

    failed_start = first_finish + timedelta(hours=1)
    failed_finish = failed_start + timedelta(minutes=2)
    assert repo.update_search_status(
        profile.id,
        _terminal_payload("error", started_at=failed_start, finished_at=failed_finish),
    )
    assert repo.update_search_status(
        profile.id,
        _terminal_payload(
            "cancelled",
            started_at=failed_finish + timedelta(hours=1),
            finished_at=failed_finish + timedelta(hours=1, minutes=1),
        ),
    )

    db_session.expire_all()
    after_failures = db_session.get(SearchProfile, profile.id)
    assert after_failures.search_run_count == 1
    assert after_failures.last_search_completed_at == first_finish
    assert after_failures.last_search_summary == first_summary

    retry_start = failed_finish + timedelta(hours=2)
    retry_finish = retry_start + timedelta(minutes=5)
    assert repo.update_search_status(
        profile.id,
        _terminal_payload(
            "done",
            started_at=retry_start,
            finished_at=retry_finish,
            jobs_found=13,
        ),
    )

    db_session.expire_all()
    after_retry = db_session.get(SearchProfile, profile.id)
    assert after_retry.search_run_count == 2
    assert after_retry.last_search_started_at == retry_start
    assert after_retry.last_search_completed_at == retry_finish
    assert after_retry.last_search_summary["counts"]["jobs_found"] == 13


def test_runtime_pruning_after_24_hours_keeps_durable_receipt(db_session, test_user):
    profile = _create_profile(db_session, test_user)
    repo = ProfileRepository(db_session)
    started_at = datetime.now(timezone.utc) - timedelta(days=2, minutes=5)
    finished_at = started_at + timedelta(minutes=5)
    assert repo.update_search_status(
        profile.id,
        _terminal_payload("done", started_at=started_at, finished_at=finished_at),
    )

    assert (
        repo.clear_stale_search_statuses(
            max_age_seconds=24 * 60 * 60,
            terminal_states=["done", "error", "stopped", "cancelled"],
        )
        == 1
    )

    db_session.expire_all()
    refreshed = db_session.get(SearchProfile, profile.id)
    assert refreshed.search_status_state is None
    assert refreshed.search_status_payload is None
    assert refreshed.search_status_started_at is None
    assert refreshed.search_status_finished_at is None
    assert refreshed.last_search_state == "done"
    assert refreshed.last_search_completed_at == finished_at
    assert refreshed.search_run_count == 1
    assert refreshed.last_search_summary["counts"]["jobs_found"] == 8


def test_completion_summary_is_fixed_size_bounded_and_contains_no_pii():
    started_at = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
    payload = _terminal_payload(
        "done",
        started_at=started_at,
        finished_at=started_at + timedelta(minutes=1),
        jobs_found=10**100,
    )
    payload["cv_content"] = "SECRET-CV"
    payload["description"] = "SECRET-LISTING"
    payload["provider_response"] = {"body": "SECRET-RESPONSE"}

    summary = build_search_completion_summary(payload)

    assert summary is not None
    encoded = json.dumps(summary, sort_keys=True).encode("utf-8")
    assert len(encoded) <= SEARCH_RECEIPT_MAX_SERIALIZED_BYTES
    assert summary["counts"]["jobs_found"] == SEARCH_RECEIPT_MAX_COUNTER
    assert summary["providers"]["status"] == "partial"
    serialized = encoded.decode("utf-8")
    assert "SECRET" not in serialized
    assert '"query"' not in serialized
    assert '"description"' not in serialized
    assert '"log"' not in serialized


def test_imported_summary_drops_unknown_nested_private_fields():
    started_at = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
    summary = build_search_completion_summary(
        _terminal_payload(
            "done",
            started_at=started_at,
            finished_at=started_at + timedelta(minutes=1),
        )
    )
    assert summary is not None
    summary["private_query"] = "SECRET-QUERY"
    summary["counts"]["listing_text"] = "SECRET-LISTING"
    summary["providers"]["response_body"] = "SECRET-RESPONSE"

    normalized = normalize_search_completion_summary(summary)

    assert normalized is not None
    serialized = json.dumps(normalized, sort_keys=True)
    assert "SECRET" not in serialized
    assert "private_query" not in normalized
    assert "listing_text" not in normalized["counts"]
    assert "response_body" not in normalized["providers"]


def test_non_success_terminal_status_cannot_build_a_receipt():
    started_at = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
    assert (
        build_search_completion_summary(
            _terminal_payload(
                "error",
                started_at=started_at,
                finished_at=started_at + timedelta(minutes=1),
            )
        )
        is None
    )
