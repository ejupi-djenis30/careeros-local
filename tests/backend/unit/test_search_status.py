from unittest.mock import MagicMock, patch

import pytest

import backend.services.search_status as ss
from backend.services.search_status import (
    add_log,
    cancel_task,
    clear_status,
    get_all_statuses,
    get_status,
    init_status,
    register_task,
    release_task,
    reserve_task,
    unregister_task,
    update_status,
)


@pytest.fixture(autouse=True)
def reset_status_registry():
    """Reset the global in-memory dictionaries before each test."""
    with (
        patch("backend.services.search_status._acquire_profile_search_lock", return_value=True),
        patch("backend.services.search_status._activate_profile_search_lock", return_value=True),
        patch("backend.services.search_status._release_profile_search_lock", return_value=True),
    ):
        with ss._lock:
            ss._statuses.clear()
            ss._active_tasks.clear()
            ss._reserved_tasks.clear()
        yield


def test_init_status():
    init_status(1, total_searches=5, searches=[{"q": "test"}])
    status = get_status(1)
    assert status["state"] == "generating"
    assert status["terminal_reason"] is None
    assert status["total_searches"] == 5
    assert status["searches_completed"] == 0
    assert status["active_search_indices"] == []
    assert status["completed_search_indices"] == []
    assert len(status["searches_generated"]) == 1
    assert status["jobs_duplicates_total"] == 0
    assert status["jobs_duplicates_runtime"] == 0
    assert status["jobs_duplicates_history"] == 0
    assert status["jobs_duplicates_catalog_conflicts"] == 0
    assert "started_at" in status


def test_add_log():
    init_status(1)
    add_log(1, "First log")
    add_log(1, "Second log")
    status = get_status(1)
    assert len(status["log"]) == 2
    assert status["log"][0]["message"] == "First log"
    assert status["log"][1]["message"] == "Second log"


def test_add_log_overflow():
    init_status(1)
    for i in range(110):
        add_log(1, f"Log {i}")
    status = get_status(1)
    assert len(status["log"]) == 100
    assert status["log"][-1]["message"] == "Log 109"


def test_update_status():
    init_status(1)
    update_status(
        1,
        state="scraping",
        jobs_found=10,
        terminal_reason="no_results",
        searches_completed=2,
        active_search_indices=[3],
        completed_search_indices=[1, 2],
    )
    status = get_status(1)
    assert status["state"] == "scraping"
    assert status["jobs_found"] == 10
    assert status["terminal_reason"] == "no_results"
    assert status["searches_completed"] == 2
    assert status["active_search_indices"] == [3]
    assert status["completed_search_indices"] == [1, 2]


def test_get_status_unknown():
    status = get_status(999)
    assert status == {"state": "unknown"}


def test_get_all_statuses():
    init_status(1)
    init_status(2)
    all_s = get_all_statuses()
    assert len(all_s) == 2
    assert 1 in all_s
    assert 2 in all_s


def test_clear_status():
    init_status(1)
    clear_status(1)
    assert get_status(1) == {"state": "unknown"}


def test_task_lifecycle():
    mock_task = MagicMock()
    register_task(1, mock_task)

    # cancel_task
    assert cancel_task(1) is True
    mock_task.cancel.assert_called_once()

    # unregister_task
    unregister_task(1)
    assert cancel_task(1) is False


def test_cancel_task_non_existent():
    assert cancel_task(999) is False


def test_task_reservation_lifecycle():
    assert reserve_task(123) is True
    assert reserve_task(123) is False

    release_task(123)
    assert reserve_task(123) is True


def test_tokenized_reservation_requires_matching_token_for_registration_and_release():
    token = reserve_task(321, return_token=True)
    mock_task = MagicMock()

    assert isinstance(token, str)
    assert register_task(321, mock_task, reservation_token="wrong-token") is False
    assert release_task(321, reservation_token="wrong-token") is False
    assert register_task(321, mock_task, reservation_token=token) is True


def test_persist_status_logs_warning_on_repository_failure(caplog):
    caplog.set_level("WARNING")
    with (
        patch("backend.services.search_status.SessionLocal") as mock_session_local,
        patch.object(
            ss.ProfileRepository, "update_search_status", side_effect=RuntimeError("boom")
        ),
    ):
        mock_session_local.return_value = MagicMock()
        init_status(1)
    assert "Failed to persist search status for profile 1" in caplog.text


def test_get_status_loads_persisted_status_when_missing_in_memory():
    persisted = {
        "state": "searching",
        "started_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:10+00:00",
    }

    with patch("backend.services.search_status._load_persisted_status", return_value=persisted):
        status = get_status(2)

    assert status["state"] == "searching"


def test_merge_with_persisted_statuses_prefers_newer_persisted_entry():
    init_status(1)
    with ss._lock:
        snapshot = dict(ss._statuses)

    persisted_entry = {
        1: {**snapshot[1], "state": "searching", "updated_at": "9999-01-01T00:00:00+00:00"},
        2: {
            "state": "done",
            "started_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:01+00:00",
        },
    }

    with patch("backend.services.search_status._load_statuses", return_value=persisted_entry):
        merged = ss._merge_with_persisted_statuses(snapshot)

    assert merged[1]["state"] == "searching"
    assert merged[2]["state"] == "done"


def test_add_log_persists_every_update_without_debounce_skip():
    init_status(1)

    with patch("backend.services.search_status._persist_status_entry") as mock_persist:
        add_log(1, "First persisted log")
        add_log(1, "Second persisted log")

    assert mock_persist.call_count == 2
    final_payload = mock_persist.call_args.args[1]
    assert final_payload["log"][-1]["message"] == "Second persisted log"


def test_reserve_task_persists_shared_reserved_entry():
    with patch("backend.services.search_status._persist_status_entry") as mock_persist:
        token = reserve_task(808, return_token=True)

    assert isinstance(token, str)
    persisted_profile_id, payload = mock_persist.call_args.args
    assert persisted_profile_id == 808
    assert payload["state"] == "reserved"
    assert payload["reservation_token"] == token


def test_reserve_task_persists_user_id_for_cross_worker_visibility():
    with patch("backend.services.search_status._persist_status_entry") as mock_persist:
        token = reserve_task(811, return_token=True, user_id=77)

    assert isinstance(token, str)
    _, payload = mock_persist.call_args.args
    assert payload["state"] == "reserved"
    assert payload["user_id"] == 77


def test_release_task_removes_shared_reserved_entry():
    token = reserve_task(909, return_token=True)

    with (
        patch("backend.services.search_status._clear_persisted_status") as mock_clear,
        patch("backend.services.search_status._load_persisted_status", return_value=None),
    ):
        assert release_task(909, reservation_token=token) is True

    mock_clear.assert_called_once_with(909)


def test_release_task_calls_db_release_even_without_in_memory_reservation():
    with patch(
        "backend.services.search_status._release_profile_search_lock", return_value=True
    ) as mock_release:
        assert release_task(990, reservation_token="shared-token") is True

    mock_release.assert_called_once_with(990, "shared-token")


def test_get_all_statuses_merges_local_and_persisted_statuses():
    init_status(1001)
    persisted = {
        1001: {"state": "searching", "updated_at": "2024-01-01T00:00:00+00:00"},
        1002: {"state": "done", "updated_at": "2024-01-01T00:00:01+00:00"},
    }

    with (
        patch("backend.services.search_status._clear_stale_persisted_statuses"),
        patch("backend.services.search_status._load_statuses", return_value=persisted),
    ):
        statuses = get_all_statuses()

    assert 1001 in statuses
    assert 1002 in statuses


# ── DB-backed reserve_task tests ────────────────────────────────────────


def test_reserve_task_blocked_by_db_lock():
    with patch("backend.services.search_status._acquire_profile_search_lock", return_value=False):
        result = reserve_task(456)
    assert result is False, "reserve_task should reject when the DB-backed lock is occupied"


# ── register_task guard tests ────────────────────────────────────────────


def test_register_task_rejects_overwrite_of_live_task():
    """register_task must refuse to overwrite an existing live asyncio task."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:

        async def _dummy():
            await asyncio.sleep(10)

        task1 = loop.create_task(_dummy())
        # Register first task
        result1 = register_task(200, task1)
        assert result1 is True

        # Second registration with a different task should be rejected
        task2 = loop.create_task(_dummy())
        result2 = register_task(200, task2)
        assert result2 is False, "Should not overwrite a live task"

        # Cleanup
        task1.cancel()
        task2.cancel()
        try:
            loop.run_until_complete(asyncio.gather(task1, task2, return_exceptions=True))
        except Exception:
            pass
    finally:
        unregister_task(200)
        loop.close()


def test_register_task_allows_registration_after_task_done():
    """register_task must allow re-registration once the old task is done."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:

        async def _immediate():
            pass

        task1 = loop.create_task(_immediate())
        loop.run_until_complete(task1)  # task is now done

        result1 = register_task(300, task1)
        assert result1 is True

        # task1.done() is True now — should allow overwrite
        task2 = loop.create_task(_immediate())
        loop.run_until_complete(task2)
        result2 = register_task(300, task2)
        assert result2 is True
    finally:
        unregister_task(300)
        loop.close()


def test_register_task_with_reservation_promotes_only_after_db_activation():
    token = reserve_task(404, return_token=True)
    task = MagicMock()

    with patch(
        "backend.services.search_status._activate_profile_search_lock", return_value=True
    ) as mock_activate:
        assert register_task(404, task, reservation_token=token) is True

    mock_activate.assert_called_once_with(404, token)
    with ss._lock:
        assert 404 not in ss._reserved_tasks
        assert ss._active_tasks[404] is task


def test_register_task_with_reservation_rolls_back_when_db_activation_fails():
    token = reserve_task(405, return_token=True)
    task = MagicMock()

    with patch(
        "backend.services.search_status._activate_profile_search_lock", return_value=False
    ) as mock_activate:
        assert register_task(405, task, reservation_token=token) is False

    mock_activate.assert_called_once_with(405, token)
    with ss._lock:
        assert ss._reserved_tasks[405]["token"] == token
        assert 405 not in ss._active_tasks


def test_merge_with_persisted_statuses_prefers_newer_updated_entry_over_older_started_entry():
    memory = {
        77: {
            "state": "done",
            "started_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:05:00+00:00",
            "finished_at": "2024-01-01T00:05:00+00:00",
        }
    }
    persisted_data = {
        77: {
            "state": "searching",
            "started_at": "2024-01-01T00:01:00+00:00",
            "updated_at": "2024-01-01T00:02:00+00:00",
        }
    }

    with patch("backend.services.search_status._load_statuses", return_value=persisted_data):
        merged = ss._merge_with_persisted_statuses(memory)

    assert merged[77]["state"] == "done"
