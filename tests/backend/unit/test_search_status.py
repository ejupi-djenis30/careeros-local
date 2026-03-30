from contextlib import nullcontext
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


def test_save_statuses_logs_warning_on_write_failure(caplog):
    caplog.set_level("WARNING")
    with patch("backend.services.search_status.open", side_effect=OSError("disk full")):
        init_status(1)
    assert "Failed to persist search statuses" in caplog.text


def test_save_statuses_merges_with_newer_file_entry():
    init_status(1)
    with ss._lock:
        snapshot = dict(ss._statuses)

    file_entry = {
        1: {**snapshot[1], "state": "searching", "updated_at": "9999-01-01T00:00:00+00:00"},
        2: {
            "state": "done",
            "started_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:01+00:00",
        },
    }

    with (
        patch("backend.services.search_status._load_statuses", return_value=file_entry),
        patch("backend.services.search_status._write_status_payload") as mock_write,
    ):
        ss._save_statuses(force=True, statuses_snapshot=snapshot)

    written_payload = mock_write.call_args.args[0]
    assert written_payload[1]["state"] == "searching"
    assert written_payload[2]["state"] == "done"


def test_add_log_persists_every_update_without_debounce_skip():
    init_status(1)

    with (
        patch("backend.services.search_status._load_statuses", return_value={}),
        patch("backend.services.search_status._write_status_payload") as mock_write,
    ):
        add_log(1, "First persisted log")
        add_log(1, "Second persisted log")

    assert mock_write.call_count == 2
    final_payload = mock_write.call_args.args[0]
    assert final_payload[1]["log"][-1]["message"] == "Second persisted log"


def test_reserve_task_persists_shared_reserved_entry():
    with (
        patch("backend.services.search_status._status_file_lock", return_value=nullcontext()),
        patch("backend.services.search_status._load_statuses", return_value={}),
        patch("backend.services.search_status._write_status_payload") as mock_write,
    ):
        token = reserve_task(808, return_token=True)

    payload = mock_write.call_args.args[0]
    assert isinstance(token, str)
    assert payload[808]["state"] == "reserved"
    assert payload[808]["reservation_token"] == token


def test_release_task_removes_shared_reserved_entry():
    token = reserve_task(909, return_token=True)
    file_data = {
        909: {
            "state": "reserved",
            "started_at": "9999-01-01T00:00:00+00:00",
            "updated_at": "9999-01-01T00:00:00+00:00",
            "reservation_token": token,
        }
    }

    with (
        patch("backend.services.search_status._status_file_lock", return_value=nullcontext()),
        patch("backend.services.search_status._load_statuses", return_value=file_data),
        patch("backend.services.search_status._write_status_payload") as mock_write,
    ):
        assert release_task(909, reservation_token=token) is True

    written_payload = mock_write.call_args.args[0]
    assert 909 not in written_payload


def test_reserve_task_allows_when_file_shows_stale_reserved_state():
    file_data = {
        1001: {
            "state": "reserved",
            "started_at": "2000-01-01T00:00:00+00:00",
            "updated_at": "2000-01-01T00:00:00+00:00",
            "reservation_token": "old-token",
        }
    }
    with (
        patch("backend.services.search_status._status_file_lock", return_value=nullcontext()),
        patch("backend.services.search_status._load_statuses", return_value=file_data),
        patch("backend.services.search_status._write_status_payload"),
    ):
        result = reserve_task(1001)
    assert result is True
    release_task(1001)


# ── Cross-worker reserve_task tests ─────────────────────────────────────


def test_reserve_task_blocked_by_file_active_state():
    """reserve_task must reject when the shared JSON file shows a non-terminal
    state with a started_at AFTER the current worker's boot time."""
    from datetime import datetime, timezone

    # Simulate a file entry started *after* the worker booted (cross-worker case)
    future_started = datetime.now(timezone.utc).isoformat()  # strictly after _WORKER_BOOT_TIME
    file_data = {
        456: {
            "state": "searching",
            "started_at": future_started,
            "terminal_reason": None,
        }
    }
    with patch("backend.services.search_status._load_statuses", return_value=file_data):
        result = reserve_task(456)
    assert result is False, "reserve_task should reject when another worker owns the search"


def test_reserve_task_blocked_by_recent_file_update_without_started_at():
    file_data = {
        654: {
            "state": "searching",
            "updated_at": "9999-01-01T00:00:00+00:00",
            "terminal_reason": None,
        }
    }
    with patch("backend.services.search_status._load_statuses", return_value=file_data):
        result = reserve_task(654)
    assert result is False, "recent updated_at should block duplicate reservations"


def test_reserve_task_allowed_when_file_shows_terminal_state():
    """reserve_task must allow when the file shows a terminal (done/error) state."""
    file_data = {
        789: {
            "state": "done",
            "started_at": "2000-01-01T00:00:00+00:00",
            "terminal_reason": "completed",
        }
    }
    with patch("backend.services.search_status._load_statuses", return_value=file_data):
        result = reserve_task(789)
    assert result is True, "Completed searches should not block a new reservation"
    release_task(789)


def test_reserve_task_allowed_when_file_shows_stale_state():
    """reserve_task must allow when the file entry pre-dates the current worker boot."""
    # Use a started_at that is definitely before _WORKER_BOOT_TIME
    old_started = "2000-01-01T00:00:00+00:00"
    file_data = {
        101: {
            "state": "searching",  # non-terminal but stale
            "started_at": old_started,
        }
    }
    with patch("backend.services.search_status._load_statuses", return_value=file_data):
        result = reserve_task(101)
    assert result is True, "Stale pre-boot entries should not block a fresh reservation"
    release_task(101)


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


def test_merge_with_file_prefers_newer_updated_entry_over_older_started_entry():
    memory = {
        77: {
            "state": "done",
            "started_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:05:00+00:00",
            "finished_at": "2024-01-01T00:05:00+00:00",
        }
    }
    file_data = {
        77: {
            "state": "searching",
            "started_at": "2024-01-01T00:01:00+00:00",
            "updated_at": "2024-01-01T00:02:00+00:00",
        }
    }

    with patch("backend.services.search_status._load_statuses", return_value=file_data):
        merged = ss._merge_with_file(memory)

    assert merged[77]["state"] == "done"
