"""
In-memory search status tracker.
Stores real-time progress of search workflows for frontend polling.
"""
from datetime import datetime, timezone
from typing import Dict, List, Any
import threading
import json
import os

_lock = threading.Lock()
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
os.makedirs(_DATA_DIR, exist_ok=True)
_STATUS_FILE = os.path.join(_DATA_DIR, "job_hunter_statuses.json")

_VALID_STATUS_KEYS = {
    "user_id", "state", "total_searches", "current_search_index",
    "current_query", "searches_generated", "jobs_found", "jobs_new",
    "jobs_duplicates", "jobs_skipped", "errors", "log",
    "started_at", "finished_at", "error",
}
_TERMINAL_STATES = {"done", "error", "stopped", "cancelled"}

def _load_statuses() -> Dict[int, Dict[str, Any]]:
    if os.path.exists(_STATUS_FILE):
        try:
            with open(_STATUS_FILE, "r") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except Exception:
            pass
    return {}

def _save_statuses():
    try:
        with open(_STATUS_FILE, "w") as f:
            json.dump(_statuses, f)
    except Exception:
        pass

_statuses: Dict[int, Dict[str, Any]] = _load_statuses()
_active_tasks: Dict[int, Any] = {} # profile_id -> asyncio.Task


def init_status(profile_id: int, total_searches: int = 0, searches: List[Dict] = None, user_id: int = None):
    """Initialize or reset status when search begins."""
    with _lock:
        _statuses[profile_id] = {
            "user_id": user_id,
            "state": "generating",
            "total_searches": total_searches,
            "current_search_index": 0,
            "current_query": "",
            "searches_generated": searches or [],
            "jobs_found": 0,
            "jobs_new": 0,
            "jobs_duplicates": 0,
            "jobs_skipped": 0,
            "errors": 0,
            "log": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
        }
        _save_statuses()


def add_log(profile_id: int, message: str):
    """Append a log entry."""
    with _lock:
        s = _statuses.get(profile_id)
        if s:
            s["log"].append({
                "time": datetime.now(timezone.utc).isoformat(),
                "message": message,
            })
            # Keep last 100 entries
            if len(s["log"]) > 100:
                s["log"] = s["log"][-100:]
            _save_statuses()


def update_status(profile_id: int, **kwargs):
    """Update any status fields."""
    invalid = set(kwargs.keys()) - _VALID_STATUS_KEYS
    if invalid:
        import logging
        logging.getLogger(__name__).warning(f"update_status called with unknown keys: {invalid}")
    with _lock:
        s = _statuses.get(profile_id)
        if s:
            s.update({k: v for k, v in kwargs.items() if k in _VALID_STATUS_KEYS})
            # Auto-set finished_at on terminal states
            if s.get("state") in _TERMINAL_STATES and not s.get("finished_at"):
                s["finished_at"] = datetime.now(timezone.utc).isoformat()
            _save_statuses()


def get_status(profile_id: int) -> Dict[str, Any]:
    """Get current status for a profile."""
    with _lock:
        return dict(_statuses.get(profile_id, {"state": "unknown"}))


def get_all_statuses(user_id: int = None) -> Dict[int, Dict[str, Any]]:
    """Get all current statuses (filtered by user_id if provided)."""
    with _lock:
        import copy
        if user_id is None:
            return copy.deepcopy(_statuses)
        return {k: copy.deepcopy(v) for k, v in _statuses.items() if v.get("user_id") == user_id}


def clear_status(profile_id: int):
    """Remove status (optional cleanup)."""
    with _lock:
        if profile_id in _statuses:
            _statuses.pop(profile_id, None)
            _save_statuses()

def register_task(profile_id: int, task: Any):
    """Register an active search task."""
    with _lock:
        _active_tasks[profile_id] = task


def unregister_task(profile_id: int):
    """Remove a finished or cancelled task from registry."""
    with _lock:
        _active_tasks.pop(profile_id, None)


def cancel_task(profile_id: int):
    """Explicitly cancel the background search task for a profile."""
    with _lock:
        task = _active_tasks.get(profile_id)
        if task:
            task.cancel()
            return True
    return False
