from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.services.scheduler as scheduler_mod
from backend.services.scheduler import (
    _run_scheduled_search,
    add_schedule,
    get_all_schedules,
    get_scheduler,
    remove_schedule,
    start_scheduler,
    stop_scheduler,
)


@pytest.fixture(autouse=True)
def reset_scheduler_state():
    scheduler_mod._scheduler = None
    yield
    if scheduler_mod._scheduler and scheduler_mod._scheduler.running:
        scheduler_mod._scheduler.shutdown()
    scheduler_mod._scheduler = None


def test_get_scheduler():
    s1 = get_scheduler()
    s2 = get_scheduler()
    assert s1 is s2
    assert s1 is not None


def test_add_schedule():
    mock_scheduler = MagicMock()
    with patch("backend.services.scheduler.get_scheduler", return_value=mock_scheduler):
        add_schedule(1, 24)
        mock_scheduler.add_job.assert_called_once()
        args, kwargs = mock_scheduler.add_job.call_args
        assert kwargs["id"] == "search_profile_1"
        assert kwargs["args"] == [1]


def test_remove_schedule():
    mock_scheduler = MagicMock()
    mock_job = MagicMock()
    mock_scheduler.get_job.return_value = mock_job

    with patch("backend.services.scheduler.get_scheduler", return_value=mock_scheduler):
        remove_schedule(1)
        mock_scheduler.remove_job.assert_called_with("search_profile_1")


def test_get_all_schedules():
    mock_scheduler = MagicMock()
    mock_job = MagicMock()
    mock_job.id = "search_profile_1"
    mock_job.name = "name1"
    mock_job.next_run_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    mock_job.trigger = "trigger1"
    mock_scheduler.get_jobs.return_value = [mock_job]

    # Provide a mock db session so SessionLocal() is not called (avoids real PG connection)
    mock_db = MagicMock()
    mock_profile = MagicMock()
    mock_profile.id = 1
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_profile]

    with patch("backend.services.scheduler.get_scheduler", return_value=mock_scheduler):
        schedules = get_all_schedules(db=mock_db)
        assert len(schedules) == 1
        assert schedules[0]["id"] == "search_profile_1"


@pytest.mark.asyncio
async def test_run_scheduled_search_success():
    mock_db = MagicMock()
    mock_profile = MagicMock()
    mock_profile.id = 1
    mock_profile.schedule_enabled = True
    mock_db.query.return_value.filter.return_value.first.return_value = mock_profile

    mock_search_service = AsyncMock()

    with (
        patch("backend.services.scheduler.SessionLocal", return_value=mock_db),
        patch("backend.services.scheduler.get_search_service", return_value=mock_search_service),
        patch("backend.services.scheduler.reserve_task", return_value="token-1") as mock_reserve,
        patch("backend.services.scheduler.release_task") as mock_release,
    ):
        await _run_scheduled_search(1)

        mock_reserve.assert_called_once_with(1, return_token=True)
        mock_search_service.run_search.assert_awaited_once_with(1, reservation_token="token-1")
        mock_db.commit.assert_called_once()
        assert mock_profile.last_scheduled_run is not None
        # release_task should NOT be called on a successful run (run_search handles task lifecycle)
        mock_release.assert_not_called()


@pytest.mark.asyncio
async def test_run_scheduled_search_skipped_when_already_running():
    """Scheduler must skip the run if reserve_task returns False (another worker owns it)."""
    mock_search_service = AsyncMock()

    with (
        patch("backend.services.scheduler.reserve_task", return_value=False),
        patch("backend.services.scheduler.get_search_service", return_value=mock_search_service),
    ):
        await _run_scheduled_search(1)

    mock_search_service.run_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_scheduled_search_profile_not_found():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with (
        patch("backend.services.scheduler.SessionLocal", return_value=mock_db),
        patch("backend.services.scheduler.reserve_task", return_value="token-2"),
        patch("backend.services.scheduler.release_task") as mock_release,
        patch("backend.services.scheduler.remove_schedule") as mock_remove,
    ):
        await _run_scheduled_search(1)
        mock_remove.assert_called_once_with(1)
        mock_release.assert_called_once_with(1, "token-2")


@pytest.mark.asyncio
async def test_run_scheduled_search_disabled():
    mock_db = MagicMock()
    mock_profile = MagicMock()
    mock_profile.schedule_enabled = False
    mock_db.query.return_value.filter.return_value.first.return_value = mock_profile

    mock_search_service = AsyncMock()

    with (
        patch("backend.services.scheduler.SessionLocal", return_value=mock_db),
        patch("backend.services.scheduler.reserve_task", return_value="token-3"),
        patch("backend.services.scheduler.release_task") as mock_release,
        patch("backend.services.scheduler.get_search_service", return_value=mock_search_service),
    ):
        await _run_scheduled_search(1)
        mock_search_service.run_search.assert_not_awaited()
        mock_release.assert_called_once_with(1, "token-3")


def test_start_scheduler():
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    mock_db = MagicMock()
    mock_profile = MagicMock()
    mock_profile.id = 1
    mock_profile.schedule_interval_hours = 12
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_profile]

    with (
        patch("backend.services.scheduler.get_scheduler", return_value=mock_scheduler),
        patch("backend.services.scheduler.SessionLocal", return_value=mock_db),
        patch("backend.services.scheduler.add_schedule") as mock_add,
    ):
        start_scheduler()
        mock_scheduler.start.assert_called_once()
        mock_add.assert_called_once_with(1, 12)


def test_stop_scheduler():
    mock_scheduler = MagicMock()
    mock_scheduler.running = True
    scheduler_mod._scheduler = mock_scheduler

    stop_scheduler()
    mock_scheduler.shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_run_scheduled_search_exception():
    mock_db = MagicMock()
    mock_profile = MagicMock()
    mock_profile.id = 1
    mock_profile.schedule_enabled = True
    mock_db.query.return_value.filter.return_value.first.return_value = mock_profile

    with (
        patch("backend.services.scheduler.SessionLocal", return_value=mock_db),
        patch("backend.services.scheduler.reserve_task", return_value="token-4"),
        patch("backend.services.scheduler.release_task") as mock_release,
        patch("backend.services.scheduler.get_search_service", side_effect=Exception("DB Failure")),
    ):
        await _run_scheduled_search(1)
        mock_db.close.assert_called_once()
        # Safety net: release_task must be called when run_search never registered the task
        mock_release.assert_called_once_with(1, "token-4")


@pytest.mark.asyncio
async def test_run_scheduled_search_releases_reservation_when_session_creation_fails():
    with (
        patch("backend.services.scheduler.SessionLocal", side_effect=RuntimeError("db offline")),
        patch("backend.services.scheduler.reserve_task", return_value="token-5"),
        patch("backend.services.scheduler.release_task") as mock_release,
    ):
        await _run_scheduled_search(1)

    mock_release.assert_called_once_with(1, "token-5")


def test_get_all_schedules_no_db_and_specific_user():
    mock_scheduler = MagicMock()
    mock_job = MagicMock()
    mock_job.id = "search_profile_1"
    mock_job.name = "name1"
    mock_job.next_run_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    mock_job.trigger = "trigger1"
    mock_scheduler.get_jobs.return_value = [mock_job]

    mock_db = MagicMock()
    mock_profile = MagicMock()
    mock_profile.id = 1
    # Needs two .filter() calls for schedule_enabled and user_id
    mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = [
        mock_profile
    ]

    with (
        patch("backend.services.scheduler.get_scheduler", return_value=mock_scheduler),
        patch("backend.services.scheduler.SessionLocal", return_value=mock_db),
    ):
        schedules = get_all_schedules(user_id=99)
        assert len(schedules) == 1
        mock_db.close.assert_called_once()


def test_get_all_schedules_value_error():
    mock_scheduler = MagicMock()
    mock_job = MagicMock()
    mock_job.id = "search_profile_invalid"
    mock_scheduler.get_jobs.return_value = [mock_job]

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []

    # We must mock get_scheduler to return a scheduler with these jobs
    with (
        patch("backend.services.scheduler.get_scheduler", return_value=mock_scheduler),
        patch("backend.services.scheduler.SessionLocal", return_value=mock_db),
    ):
        schedules = get_all_schedules()
        assert len(schedules) == 0


def test_start_scheduler_already_running():
    mock_scheduler = MagicMock()
    mock_scheduler.running = True
    with patch("backend.services.scheduler.get_scheduler", return_value=mock_scheduler):
        start_scheduler()
        mock_scheduler.start.assert_not_called()


def test_start_scheduler_exception():
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    mock_db = MagicMock()
    mock_db.query.side_effect = Exception("DB Query Error")

    with (
        patch("backend.services.scheduler.get_scheduler", return_value=mock_scheduler),
        patch("backend.services.scheduler.SessionLocal", return_value=mock_db),
    ):
        start_scheduler()


def test_get_all_schedules_pid_not_in_valid():
    # hits line 117
    mock_scheduler = MagicMock()
    mock_job = MagicMock()
    mock_job.id = "search_profile_2"
    mock_scheduler.get_jobs.return_value = [mock_job]

    mock_db = MagicMock()
    mock_profile = MagicMock()
    mock_profile.id = 1
    mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = [
        mock_profile
    ]

    with (
        patch("backend.services.scheduler.get_scheduler", return_value=mock_scheduler),
        patch("backend.services.scheduler.SessionLocal", return_value=mock_db),
    ):
        schedules = get_all_schedules(user_id=1)
        assert len(schedules) == 0
