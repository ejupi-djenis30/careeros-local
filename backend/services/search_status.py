"""
In-memory search status tracker.
Stores real-time progress of search workflows for frontend polling.
"""

import copy
import glob
import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

# Platform-safe fcntl accessor: mypy on Windows doesn't have fcntl, so expose
# a typed-any module variable that the lock code can use without static
# attribute errors.
try:
    import fcntl  # type: ignore

    _fcntl: Any = fcntl
except Exception:
    _fcntl: Any = None  # type: ignore

_lock = threading.Lock()
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
os.makedirs(_DATA_DIR, exist_ok=True)
_STATUS_FILE = os.path.join(_DATA_DIR, "job_hunter_statuses.json")
_STATUS_LOCK_FILE = os.path.join(_DATA_DIR, "job_hunter_statuses.lock")

_VALID_STATUS_KEYS = {
    "user_id",
    "state",
    "total_searches",
    "current_search_index",
    "searches_completed",
    "active_search_indices",
    "completed_search_indices",
    "current_query",
    "searches_generated",
    "jobs_found",
    "jobs_new",
    "jobs_unique",
    "jobs_duplicates",
    "jobs_duplicates_total",
    "jobs_duplicates_runtime",
    "jobs_duplicates_history",
    "jobs_duplicates_catalog_conflicts",
    "jobs_skipped",
    "errors",
    "log",
    "started_at",
    "finished_at",
    "updated_at",
    "error",
    "jobs_analyzed",
    "jobs_analyze_total",
    "terminal_reason",
    "degraded_mode",
    "plan_cache_hit",
    "plan_cache_miss",
    "plan_raw_count",
    "plan_unique_count",
    "queries_without_provider",
    "provider_failures",
    "provider_successes",
    "avam_fallback_count",
}
_TERMINAL_STATES = {"done", "error", "stopped", "cancelled"}
_RESERVED_STATE = "reserved"


def _load_statuses() -> Dict[int, Dict[str, Any]]:
    candidates = []
    if os.path.exists(_STATUS_FILE):
        candidates.append(_STATUS_FILE)

    temp_candidates = sorted(glob.glob(f"{_STATUS_FILE}.*.tmp"), key=os.path.getmtime, reverse=True)
    candidates.extend(path for path in temp_candidates if path not in candidates)

    for candidate in candidates:
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except Exception as exc:
            logger.warning("Failed to load search statuses from %s: %s", candidate, exc)
    return {}


@contextmanager
def _status_file_lock(timeout_seconds: float = 5.0) -> Iterator[None]:
    lock_handle = None
    acquired = False
    start = time.time()
    try:
        lock_handle = open(_STATUS_LOCK_FILE, "a+b")
        while not acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    lock_handle.seek(0)
                    msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
                else:
                    _fcntl.flock(lock_handle.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                acquired = True
            except OSError:
                if (time.time() - start) >= timeout_seconds:
                    raise TimeoutError("Timed out waiting for search status file lock")
                time.sleep(0.05)

        yield
    finally:
        if acquired and lock_handle is not None:
            try:
                if os.name == "nt":
                    import msvcrt

                    lock_handle.seek(0)
                    msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
                else:
                    _fcntl.flock(lock_handle.fileno(), _fcntl.LOCK_UN)
            except OSError:
                pass
        if lock_handle is not None:
            lock_handle.close()


def _entry_timestamp(entry: Dict[str, Any] | None) -> str:
    if not entry:
        return ""
    return str(entry.get("updated_at") or entry.get("finished_at") or entry.get("started_at") or "")


def _merge_status_maps(
    existing: Dict[int, Dict[str, Any]],
    incoming: Dict[int, Dict[str, Any]],
    removed_ids: set[int] | None = None,
) -> Dict[int, Dict[str, Any]]:
    removed = removed_ids or set()
    merged: Dict[int, Dict[str, Any]] = {}
    all_ids = (set(existing.keys()) | set(incoming.keys())) - removed

    for profile_id in all_ids:
        current = existing.get(profile_id)
        new_entry = incoming.get(profile_id)
        if current is None:
            merged[profile_id] = new_entry  # type: ignore[assignment]
            continue
        if new_entry is None:
            merged[profile_id] = current
            continue
        merged[profile_id] = (
            new_entry if _entry_timestamp(new_entry) >= _entry_timestamp(current) else current
        )

    return merged


def _write_status_payload(payload: Dict[int, Dict[str, Any]]):
    temp_file = f"{_STATUS_FILE}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(payload, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_file, _STATUS_FILE)


def _touch_status_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    return entry


_RESERVATION_TTL_SECONDS = 30.0


def _snapshot_statuses() -> Dict[int, Dict[str, Any]]:
    return copy.deepcopy(_statuses)


def _build_reserved_status_entry(
    reservation_token: str, user_id: int | None = None
) -> Dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    entry: Dict[str, Any] = {
        "state": _RESERVED_STATE,
        "terminal_reason": None,
        "started_at": timestamp,
        "updated_at": timestamp,
        "finished_at": None,
        "reservation_token": reservation_token,
    }
    if user_id is not None:
        entry["user_id"] = user_id
    return entry


def _is_stale_reserved_entry(entry: Dict[str, Any], now: float | None = None) -> bool:
    if entry.get("state") != _RESERVED_STATE:
        return False

    reference_ts = _entry_timestamp(entry)
    if not reference_ts:
        return True

    try:
        entry_ts = datetime.fromisoformat(reference_ts).timestamp()
    except (TypeError, ValueError):
        return True

    current_ts = now if now is not None else time.time()
    return (current_ts - entry_ts) > _RESERVATION_TTL_SECONDS


def _prune_stale_reserved_entries(statuses: Dict[int, Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    now = time.time()
    return {
        pid: entry for pid, entry in statuses.items() if not _is_stale_reserved_entry(entry, now)
    }


def _entry_is_current_worker_visible(entry: Dict[str, Any] | None) -> bool:
    reference_ts = _entry_timestamp(entry)
    return bool(reference_ts and reference_ts >= _WORKER_BOOT_TIME)


def _shared_entry_blocks_reservation(entry: Dict[str, Any]) -> bool:
    state = entry.get("state", "unknown")
    if state in _TERMINAL_STATES or state == "unknown":
        return False
    if state == _RESERVED_STATE:
        return not _is_stale_reserved_entry(entry)

    return _entry_is_current_worker_visible(entry)


def _save_statuses(force: bool = False, statuses_snapshot: Dict[int, Dict[str, Any]] | None = None):
    payload = statuses_snapshot if statuses_snapshot is not None else _statuses

    try:
        with _status_file_lock():
            file_payload = _prune_stale_reserved_entries(_load_statuses())
            merged = _merge_status_maps(file_payload, payload)
            _write_status_payload(merged)
    except Exception as exc:
        logger.warning("Failed to persist search statuses to %s: %s", _STATUS_FILE, exc)


def _save_statuses_with_removals(
    *,
    force: bool = False,
    statuses_snapshot: Dict[int, Dict[str, Any]] | None = None,
    removed_ids: set[int] | None = None,
):
    payload = statuses_snapshot if statuses_snapshot is not None else _statuses

    try:
        with _status_file_lock():
            file_payload = _prune_stale_reserved_entries(_load_statuses())
            merged = _merge_status_maps(file_payload, payload, removed_ids=removed_ids)
            _write_status_payload(merged)
    except Exception as exc:
        logger.warning("Failed to persist search statuses to %s: %s", _STATUS_FILE, exc)


_statuses: Dict[int, Dict[str, Any]] = _load_statuses()
_active_tasks: Dict[int, Any] = {}  # profile_id -> asyncio.Task
_reserved_tasks: Dict[int, Dict[str, Any]] = {}
# ISO-8601 timestamp captured once when this worker process starts.
# Used in _merge_with_file to distinguish live cross-worker search entries
# (started after this boot) from stale entries left in the file by a prior
# server run that crashed mid-search.
_WORKER_BOOT_TIME: str = datetime.now(timezone.utc).isoformat()


def _cleanup_stale_reservations(now: float | None = None):
    ts = now if now is not None else time.time()
    stale = [
        profile_id
        for profile_id, reservation in _reserved_tasks.items()
        if (ts - float(reservation.get("reserved_at", 0.0))) > _RESERVATION_TTL_SECONDS
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


def init_status(
    profile_id: int,
    total_searches: int = 0,
    searches: Optional[List[Dict]] = None,
    user_id: Optional[int] = None,
):
    """Initialize or reset status when search begins."""
    with _lock:
        _statuses[profile_id] = {
            "user_id": user_id,
            "state": "generating",
            "terminal_reason": None,
            "total_searches": total_searches,
            "current_search_index": 0,
            "searches_completed": 0,
            "active_search_indices": [],
            "completed_search_indices": [],
            "current_query": "",
            "searches_generated": searches or [],
            "jobs_found": 0,
            "jobs_new": 0,
            "jobs_unique": 0,
            "jobs_duplicates": 0,
            "jobs_duplicates_total": 0,
            "jobs_duplicates_runtime": 0,
            "jobs_duplicates_history": 0,
            "jobs_duplicates_catalog_conflicts": 0,
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
        _touch_status_entry(_statuses[profile_id])
        snapshot = _snapshot_statuses()
    _save_statuses(force=True, statuses_snapshot=snapshot)


def add_log(profile_id: int, message: str):
    """Append a log entry."""
    with _lock:
        s = _statuses.get(profile_id)
        snapshot = None
        if s:
            s["log"].append(
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "message": message,
                }
            )
            # Keep last 100 entries
            if len(s["log"]) > 100:
                s["log"] = s["log"][-100:]
            _touch_status_entry(s)
            snapshot = _snapshot_statuses()
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
            _touch_status_entry(s)
            snapshot = _snapshot_statuses()
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
    merged: Dict[int, Dict[str, Any]] = {}
    try:
        file_data = _prune_stale_reserved_entries(_load_statuses())
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
            elif _entry_is_current_worker_visible(file_entry):
                merged[pid] = copy.deepcopy(file_entry)  # type: ignore[assignment, arg-type]
            # else: stale non-terminal entry from a crashed prior run — skip.
        elif file_entry is None:
            merged[pid] = copy.deepcopy(mem_entry)
        else:
            merged[pid] = copy.deepcopy(
                mem_entry
                if _entry_timestamp(mem_entry) >= _entry_timestamp(file_entry)
                else file_entry
            )
    return merged


def _prune_old_terminal_statuses(
    statuses: Dict[int, Dict[str, Any]], max_age_seconds: float = 86400.0
) -> Dict[int, Dict[str, Any]]:
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
    file_statuses = _prune_stale_reserved_entries(_load_statuses())
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
            snapshot = _snapshot_statuses()
    if snapshot is not None:
        _save_statuses_with_removals(
            force=True, statuses_snapshot=snapshot, removed_ids={profile_id}
        )


def register_task(profile_id: int, task: Any, reservation_token: str | None = None):
    """Register an active search task.

    Guards against a second worker overwriting an already-active task for the
    same profile_id (cross-worker race).  If the slot is already occupied by a
    live task the call is a no-op and returns False so the caller can abort.
    """
    with _lock:
        reservation = _reserved_tasks.get(profile_id)
        if reservation_token is not None:
            if reservation is None:
                logger.warning(
                    "register_task: profile %d has no matching reservation token; refusing activation",
                    profile_id,
                )
                return False
            if reservation.get("token") != reservation_token:
                logger.warning(
                    "register_task: profile %d reservation token mismatch; refusing activation",
                    profile_id,
                )
                return False
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
                _reserved_tasks.pop(profile_id, None)
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


def reserve_task(
    profile_id: int,
    *,
    return_token: bool = False,
    reservation_token: str | None = None,
    user_id: int | None = None,
) -> bool | str:
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
            with _status_file_lock():
                file_data = _prune_stale_reserved_entries(_load_statuses())
                file_entry = file_data.get(profile_id)
                if file_entry and _shared_entry_blocks_reservation(file_entry):
                    logger.info(
                        "reserve_task: profile %d is already running on another worker (state=%s, started=%s)",
                        profile_id,
                        file_entry.get("state", "unknown"),
                        file_entry.get("started_at") or "",
                    )
                    return False

                token = reservation_token or uuid.uuid4().hex
                _reserved_tasks[profile_id] = {
                    "reserved_at": time.time(),
                    "token": token,
                }
                file_data[profile_id] = _build_reserved_status_entry(token, user_id=user_id)
                _write_status_payload(file_data)
        except Exception as exc:
            logger.warning("reserve_task: failed to persist shared reservation: %s", exc)
            _reserved_tasks.pop(profile_id, None)
            return False

        return token if return_token else True


def release_task(profile_id: int, reservation_token: str | None = None) -> bool:
    """Release a previously reserved profile slot."""
    with _lock:
        reservation = _reserved_tasks.get(profile_id)
        in_memory_released = False
        if reservation is not None:
            if reservation_token is not None and reservation.get("token") != reservation_token:
                return False
            _reserved_tasks.pop(profile_id, None)
            in_memory_released = True

        file_released = False
        try:
            with _status_file_lock():
                file_data = _prune_stale_reserved_entries(_load_statuses())
                file_entry = file_data.get(profile_id)
                if file_entry and file_entry.get("state") == _RESERVED_STATE:
                    file_token = file_entry.get("reservation_token")
                    if reservation_token is None or file_token == reservation_token:
                        file_data.pop(profile_id, None)
                        _write_status_payload(file_data)
                        file_released = True
        except Exception as exc:
            logger.warning("release_task: failed to clear shared reservation: %s", exc)
        return in_memory_released or file_released


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
_statuses = _prune_stale_reserved_entries(_statuses)
