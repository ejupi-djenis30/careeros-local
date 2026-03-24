import pytest
from unittest.mock import MagicMock
from backend.services.search_status import (
    init_status, add_log, update_status, get_status, 
    get_all_statuses, clear_status, register_task, 
    unregister_task, cancel_task
)
import backend.services.search_status as ss

@pytest.fixture(autouse=True)
def reset_status_registry():
    """Reset the global in-memory dictionaries before each test."""
    with ss._lock:
        ss._statuses.clear()
        ss._active_tasks.clear()
    yield

def test_init_status():
    init_status(1, total_searches=5, searches=[{"q": "test"}])
    status = get_status(1)
    assert status["state"] == "generating"
    assert status["total_searches"] == 5
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
    update_status(1, state="scraping", jobs_found=10)
    status = get_status(1)
    assert status["state"] == "scraping"
    assert status["jobs_found"] == 10

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
