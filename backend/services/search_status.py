"""
In-memory search status tracker.
Stores real-time progress of search workflows for frontend polling.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
os.makedirs(_DATA_DIR, exist_ok=True)
_STATUS_FILE = os.path.join(_DATA_DIR, "job_hunter_statuses.json")

_VALID_STATUS_KEYS = {
    "user_id", "state", "total_searches", "current_search_index",
    "current_query", "searches_generated", "jobs_found", "jobs_new",
    "jobs_duplicates", "jobs_skipped", "errors", "log",
    "started_at", "finished_at", "error",
    "jobs_analyzed", "jobs_analyze_total", "terminal_reason", "degraded_mode",
    "plan_cache_hit", "plan_cache_miss", "plan_raw_count", "plan_unique_count",
    "queries_without_provider", "provider_failures", "provider_successes", "avam_fallback_count",
}
_TERMINAL_STATES = {"done", "error", "stopped", "cancelled"}

def _load_statuses() -> Dict[int, Dict[str, Any]]:
    if os.path.exists(_STATUS_FILE):
        try:
            with open(_STATUS_FILE, "r") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except Exception as exc:
            logger.warning("Failed to load search statuses from %s: %s", _STATUS_FILE, exc)
    return {}

_last_save_time = 0.0
_SAVE_DEBOUNCE_INTERVAL = 1.5
_RESERVATION_TTL_SECONDS = 30.0

def _save_statuses(force: bool = False, statuses_snapshot: Dict[int, Dict[str, Any]] | None = None):
    global _last_save_time
    now = time.time()
    if not force and (now - _last_save_time) < _SAVE_DEBOUNCE_INTERVAL:
        return

    payload = statuses_snapshot if statuses_snapshot is not None else _statuses

    try:
        temp_file = f"{_STATUS_FILE}.tmp"
        with open(temp_file, "w") as f:
            json.dump(payload, f)
        os.replace(temp_file, _STATUS_FILE)
        _last_save_time = now
    except Exception as exc:
        logger.warning("Failed to persist search statuses to %s: %s", _STATUS_FILE, exc)

_statuses: Dict[int, Dict[str, Any]] = _load_statuses()
_active_tasks: Dict[int, Any] = {} # profile_id -> asyncio.Task
_reserved_tasks: Dict[int, float] = {}
# ISO-8601 timestamp captured once when this worker process starts.
# Used in _merge_with_file to distinguish live cross-worker search entries
# (started after this boot) from stale entries left in the file by a prior
# server run that crashed mid-search.
_WORKER_BOOT_TIME: str = datetime.now(timezone.utc).isoformat()


def _cleanup_stale_reservations(now: float | None = None):
    ts = now if now is not None else time.time()
    stale = [
        profile_id
        for profile_id, reserved_at in _reserved_tasks.items()
        if (ts - reserved_at) > _RESERVATION_TTL_SECONDS
    ]
    for profile_id in stale:
        _reserved_tasks.pop(profile_id, None)
    # Also evict active_tasks slots where the asyncio Task has already finished.
    done_tasks = [
        profile_id
        for profile_id, task in _active_tasks.items()
        if hasattr(task, "done") and task.done()
    ]
    for profile_id in done_tasks:
        _active_tasks.pop(profile_id, None)


def init_status(profile_id: int, total_searches: int = 0, searches: Optional[List[Dict]] = None, user_id: Optional[int] = None):
    """Initialize or reset status when search begins."""
    with _lock:
        _statuses[profile_id] = {
            "user_id": user_id,
            "state": "generating",
            "terminal_reason": None,
            "total_searches": total_searches,
            "current_search_index": 0,
            "current_query": "",
            "searches_generated": searches or [],
            "jobs_found": 0,
            "jobs_new": 0,
            "jobs_duplicates": 0,
            "jobs_skipped": 0,
            "jobs_analyzed": 0,
            "jobs_analyze_total": 0,
            "plan_cache_hit": 0,
            "plan_cache_miss": 0,
            "plan_raw_count": 0,
            "plan_unique_count": 0,
            "queries_without_provider": 0,
            "provider_failures": 0,
            "provider_successes": 0,
            "avam_fallback_count": 0,
            "errors": 0,
            "log": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
        }
        snapshot = dict(_statuses)
    _save_statuses(force=True, statuses_snapshot=snapshot)


def add_log(profile_id: int, message: str):
    """Append a log entry."""
    with _lock:
        s = _statuses.get(profile_id)
        snapshot = None
        if s:
            s["log"].append({
                "time": datetime.now(timezone.utc).isoformat(),
                "message": message,
            })
            # Keep last 100 entries
            if len(s["log"]) > 100:
                s["log"] = s["log"][-100:]
            snapshot = dict(_statuses)
    if snapshot is not None:
        _save_statuses(statuses_snapshot=snapshot)


def update_status(profile_id: int, **kwargs):
    """Update any status fields."""
    invalid = set(kwargs.keys()) - _VALID_STATUS_KEYS
    if invalid:
        import logging
        logging.getLogger(__name__).warning(f"update_status called with unknown keys: {invalid}")
    with _lock:
        s = _statuses.get(profile_id)
        snapshot = None
        should_force = False
        if s:
            s.update({k: v for k, v in kwargs.items() if k in _VALID_STATUS_KEYS})
            # Auto-set finished_at on terminal states
            is_terminal = s.get("state") in _TERMINAL_STATES
            if is_terminal and not s.get("finished_at"):
                s["finished_at"] = datetime.now(timezone.utc).isoformat()
            snapshot = dict(_statuses)
            should_force = is_terminal
    if snapshot is not None:
        _save_statuses(force=should_force, statuses_snapshot=snapshot)


def _merge_with_file(memory: Dict[int, Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Merge in-memory statuses with file-persisted ones.

    Needed when running with multiple Gunicorn workers: a background search
    task runs entirely inside one worker process and writes its status to
    that process's in-memory dict.  Polling requests from other workers
    would otherwise always return an empty result.  The JSON file is the
    shared source of truth across processes — it is force-written on every
    init_status() call and on every terminal-state transition.

    Merge rule: for a given profile_id present in both sources, whichever
    has the *newer* ``started_at`` ISO string wins.  In practice this means
    the owning worker's live in-memory state wins for the current run, and
    a fresher file entry wins for a run that was started by a different
    worker (cross-process case).
    """
    import copy
    merged: Dict[int, Dict[str, Any]] = {}
    try:
        file_data = _load_statuses()
    except Exception:
        file_data = {}

    all_ids = set(memory.keys()) | set(file_data.keys())
    for pid in all_ids:
        mem_entry = memory.get(pid)
        file_entry = file_data.get(pid)
        if mem_entry is None:
            # This worker has no in-memory record — might be a sibling-worker
            # entry or a stale entry left by a prior server run.
            file_state = (file_entry or {}).get("state", "unknown")
            if file_state in _TERMINAL_STATES:
                # Terminal states are always safe to surface.
                merged[pid] = file_entry  # type: ignore[assignment]
            else:
                # Non-terminal: only include if the search was started AFTER
                # this worker booted.  Lexicographic ISO-8601 comparison is
                # valid for UTC timestamps of the same format.
                file_started = (file_entry or {}).get("started_at") or ""
                if file_started >= _WORKER_BOOT_TIME:
                    merged[pid] = copy.deepcopy(file_entry)  # type: ignore[assignment]
                # else: stale non-terminal entry from a crashed prior run — skip.
        elif file_entry is None:
            merged[pid] = copy.deepcopy(mem_entry)
        else:
            mem_started = mem_entry.get("started_at") or ""
            file_started = file_entry.get("started_at") or ""
            merged[pid] = copy.deepcopy(mem_entry if mem_started >= file_started else file_entry)
    return merged


def _prune_old_terminal_statuses(statuses: Dict[int, Dict[str, Any]], max_age_seconds: float = 86400.0) -> Dict[int, Dict[str, Any]]:
    """Remove terminal status entries whose ``finished_at`` timestamp is older than max_age_seconds."""
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
    pruned: Dict[int, Dict[str, Any]] = {}
    for pid, entry in statuses.items():
        if entry.get("state") not in _TERMINAL_STATES:
            pruned[pid] = entry
            continue
        finished_at = entry.get("finished_at")
        if not finished_at:
            pruned[pid] = entry
            continue
        try:
            finished_ts = datetime.fromisoformat(finished_at).timestamp()
            if finished_ts >= cutoff:
                pruned[pid] = entry
            # else: expired terminal entry — silently drop it
        except (ValueError, TypeError):
            pruned[pid] = entry  # keep entries with unparseable timestamps
    return pruned


def get_status(profile_id: int) -> Dict[str, Any]:
    """Get current status for a profile."""
    with _lock:
        if profile_id in _statuses:
            return dict(_statuses[profile_id])
    # Not present in this worker's memory — check the persisted file.
    file_statuses = _load_statuses()
    return dict(file_statuses.get(profile_id, {"state": "unknown"}))


def get_all_statuses(user_id: Optional[int] = None) -> Dict[int, Dict[str, Any]]:
    """Get all current statuses (filtered by user_id if provided).

    Merges in-memory state with the shared JSON file so that searches
    started on a different Gunicorn worker process are also visible.
    Terminal entries older than 24 hours are pruned on each call.
    """
    with _lock:
        merged = _merge_with_file(dict(_statuses))

    # Prune stale terminal entries (>24h old) to prevent unbounded file growth.
    merged = _prune_old_terminal_statuses(merged)

    if user_id is None:
        return merged
    return {k: v for k, v in merged.items() if v.get("user_id") == user_id}


def clear_status(profile_id: int):
    """Remove status (optional cleanup)."""
    with _lock:
        snapshot = None
        if profile_id in _statuses:
            _statuses.pop(profile_id, None)
            snapshot = dict(_statuses)
    if snapshot is not None:
        _save_statuses(force=True, statuses_snapshot=snapshot)

def register_task(profile_id: int, task: Any):
    """Register an active search task.

    Guards against a second worker overwriting an already-active task for the
    same profile_id (cross-worker race).  If the slot is already occupied by a
    live task the call is a no-op and returns False so the caller can abort.
    """
    with _lock:
        _reserved_tasks.pop(profile_id, None)
        existing = _active_tasks.get(profile_id)
        if existing is not None:
            # Check if the existing task is still alive before refusing.
            try:
                if not existing.done():
                    logger.warning(
                        "register_task: profile %d already has an active task — ignoring duplicate registration",
                        profile_id,
                    )
                    return False
            except Exception:
                pass  # Non-asyncio task object — treat as replaced
        _active_tasks[profile_id] = task
        return True


def unregister_task(profile_id: int):
    """Remove a finished or cancelled task from registry."""
    with _lock:
        _reserved_tasks.pop(profile_id, None)
        _active_tasks.pop(profile_id, None)


def get_all_active_tasks() -> dict:
    """Return a snapshot of {profile_id: task} for graceful shutdown."""
    with _lock:
        return dict(_active_tasks)


def reserve_task(profile_id: int) -> bool:
    """Reserve a profile before the background task is registered.

    Cross-worker safe: in addition to checking the in-process task registries
    this also inspects the shared JSON status file so that a reservation made
    by a sibling Gunicorn worker is honoured.  A non-terminal status entry
    whose ``started_at`` was created after this worker booted means another
    worker already owns (or just started) the search.
    """
    with _lock:
        _cleanup_stale_reservations()
        if profile_id in _active_tasks or profile_id in _reserved_tasks:
            return False

        # Cross-worker guard: check the shared status file.
        try:
            file_data = _load_statuses()
            file_entry = file_data.get(profile_id)
            if file_entry:
                file_state = file_entry.get("state", "unknown")
                file_started = file_entry.get("started_at") or ""
                # Non-terminal status that was started AFTER this worker booted
                # means another live worker owns this profile's search.
                if (
                    file_state not in _TERMINAL_STATES
                    and file_state != "unknown"
                    and file_started >= _WORKER_BOOT_TIME
                ):
                    logger.info(
                        "reserve_task: profile %d is already running on another worker (state=%s, started=%s)",
                        profile_id, file_state, file_started,
                    )
                    return False
        except Exception as exc:
            logger.warning("reserve_task: failed to read status file for cross-worker check: %s", exc)

        _reserved_tasks[profile_id] = time.time()
        return True


def release_task(profile_id: int):
    """Release a previously reserved profile slot."""
    with _lock:
        _reserved_tasks.pop(profile_id, None)


def cancel_task(profile_id: int):
    """Explicitly cancel the background search task for a profile."""
    with _lock:
        task = _active_tasks.get(profile_id)
        _reserved_tasks.pop(profile_id, None)
        if task:
            task.cancel()
            return True
    return False


# Prune stale terminal statuses from prior server runs at module load so the
# status file does not grow unboundedly across restarts.
_statuses = _prune_old_terminal_statuses(_statuses)
