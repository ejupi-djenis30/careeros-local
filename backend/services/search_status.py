"""DB-backed search status tracker.

Search ownership already lives on SearchProfile via lock columns. This module
persists progress/status snapshots to the same shared database so polling works
across workers without relying on a shared JSON file.
"""

import asyncio
import copy
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, overload

from sqlalchemy.exc import OperationalError, ProgrammingError

from backend.core.config import settings
from backend.core.diagnostics import (
    FailureCode,
    FailureDiagnostic,
    diagnose_failure,
    is_public_activity_message,
    is_public_diagnostic_message,
    is_public_progress_label,
    log_failure,
    public_progress_targets,
    public_status_message,
    restore_public_activity_message,
    restore_public_diagnostic_message,
    restore_public_progress_label,
    sanitize_persisted_message,
    unclassified_status_error,
)
from backend.db.base import SessionLocal
from backend.repositories.profile_repository import ProfileRepository

logger = logging.getLogger(__name__)

_lock = threading.Lock()

_VALID_STATUS_KEYS = {
    "diagnostic_schema",
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
    "jobs_stale_before_save",
    "jobs_skipped",
    "errors",
    "analysis_targets",
    "analysis_current_index",
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
    "planner_mode",
    "plan_provenance",
    "queries_without_provider",
    "provider_failures",
    "provider_successes",
    "avam_fallback_count",
}
_PERSISTED_STATUS_KEYS = _VALID_STATUS_KEYS | {"log", "reservation_token"}
_TERMINAL_STATES = {"done", "error", "stopped", "cancelled"}
_DIAGNOSTIC_SCHEMA = 2
_TERMINAL_FAILURE_CODES = {
    "job_persistence_failed": FailureCode.NO_PERSISTED_JOBS,
    "local_analysis_failed": FailureCode.LOCAL_ANALYSIS_FAILED,
    "local_model_required": FailureCode.LOCAL_MODEL_REQUIRED,
    "pipeline_processing_failed": FailureCode.PIPELINE_PROCESSING_FAILED,
    "pipeline_timeout": FailureCode.PIPELINE_TIMEOUT,
    "search_execution_failed": FailureCode.PROVIDER_ALL_FAILED,
    "search_unexpected": FailureCode.SEARCH_UNEXPECTED,
    "server_shutdown": FailureCode.SERVER_SHUTDOWN,
}
_RESERVED_STATE = "reserved"
_STATUS_RETENTION_SECONDS = 86400.0
_RESERVATION_TTL_SECONDS = 30.0


def _entry_timestamp(entry: Dict[str, Any] | None) -> str:
    if not entry:
        return ""
    return str(entry.get("updated_at") or entry.get("finished_at") or entry.get("started_at") or "")


def _parse_timestamp(value: Any) -> float:
    if not value:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _entry_timestamp_value(entry: Dict[str, Any] | None) -> float:
    return _parse_timestamp(_entry_timestamp(entry))


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
            if new_entry is not None:
                merged[profile_id] = copy.deepcopy(new_entry)
            continue
        if new_entry is None:
            merged[profile_id] = copy.deepcopy(current)
            continue
        merged[profile_id] = copy.deepcopy(
            new_entry
            if _entry_timestamp_value(new_entry) >= _entry_timestamp_value(current)
            else current
        )

    return merged


def _normalize_status_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    payload = {k: copy.deepcopy(v) for k, v in entry.items() if k in _PERSISTED_STATUS_KEYS}
    payload["diagnostic_schema"] = _DIAGNOSTIC_SCHEMA
    if "updated_at" not in payload:
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    return payload


def _sanitize_loaded_status(entry: Dict[str, Any]) -> Dict[str, Any]:
    payload = copy.deepcopy(entry)
    legacy_schema = payload.get("diagnostic_schema") != _DIAGNOSTIC_SCHEMA
    raw_targets = payload.get("searches_generated")
    target_count = len(raw_targets) if isinstance(raw_targets, list) else 0
    payload["searches_generated"] = public_progress_targets(min(target_count, 100))
    raw_analysis_targets = payload.get("analysis_targets")
    analysis_target_count = (
        len(raw_analysis_targets) if isinstance(raw_analysis_targets, list) else 0
    )
    payload["analysis_targets"] = public_progress_targets(min(analysis_target_count, 100))
    current_query = payload.get("current_query")
    if current_query:
        try:
            payload["current_query"] = restore_public_progress_label(current_query)
        except (TypeError, ValueError):
            payload["current_query"] = ""
    else:
        payload["current_query"] = ""
    if legacy_schema:
        payload["analysis_targets"] = []
        payload["log"] = []
        terminal_reason = str(payload.get("terminal_reason") or "")
        failure_code = _TERMINAL_FAILURE_CODES.get(terminal_reason)
        if payload.get("error"):
            payload["error"] = public_status_message(
                failure_code or FailureCode.UNCLASSIFIED_STATUS_ERROR
            )
        payload["diagnostic_schema"] = _DIAGNOSTIC_SCHEMA
    elif payload.get("error"):
        try:
            payload["error"] = restore_public_diagnostic_message(payload["error"])
        except (TypeError, ValueError):
            payload["error"] = public_status_message(FailureCode.UNCLASSIFIED_STATUS_ERROR)
    if not legacy_schema:
        public_log: list[dict[str, str]] = []
        raw_log = payload.get("log")
        if isinstance(raw_log, list):
            for item in raw_log[-100:]:
                if not isinstance(item, dict) or set(item) != {"time", "message"}:
                    continue
                timestamp = item.get("time")
                if not isinstance(timestamp, str) or len(timestamp) > 64:
                    continue
                if _parse_timestamp(timestamp) <= 0:
                    continue
                try:
                    message: str = restore_public_activity_message(item.get("message"))
                except (TypeError, ValueError):
                    try:
                        message = restore_public_diagnostic_message(item.get("message"))
                    except (TypeError, ValueError):
                        continue
                public_log.append({"time": timestamp, "message": str(message)})
        payload["log"] = public_log
    return payload


def _touch_status_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    return entry


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

    entry_ts = _parse_timestamp(reference_ts)
    if entry_ts <= 0.0:
        return True

    current_ts = now if now is not None else time.time()
    return (current_ts - entry_ts) > _RESERVATION_TTL_SECONDS


def _prune_stale_reserved_entries(statuses: Dict[int, Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    now = time.time()
    return {
        pid: entry for pid, entry in statuses.items() if not _is_stale_reserved_entry(entry, now)
    }


def _prune_old_terminal_statuses(
    statuses: Dict[int, Dict[str, Any]], max_age_seconds: float = _STATUS_RETENTION_SECONDS
) -> Dict[int, Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
    pruned: Dict[int, Dict[str, Any]] = {}
    for pid, entry in statuses.items():
        if entry.get("state") not in _TERMINAL_STATES:
            pruned[pid] = copy.deepcopy(entry)
            continue
        finished_at = entry.get("finished_at")
        if not finished_at:
            pruned[pid] = copy.deepcopy(entry)
            continue
        finished_ts = _parse_timestamp(finished_at)
        if finished_ts <= 0.0 or finished_ts >= cutoff:
            pruned[pid] = copy.deepcopy(entry)
    return pruned


def _status_is_expired(entry: Dict[str, Any]) -> bool:
    if _is_stale_reserved_entry(entry):
        return True
    if entry.get("state") not in _TERMINAL_STATES:
        return False
    finished_ts = _parse_timestamp(entry.get("finished_at"))
    if finished_ts <= 0.0:
        return False
    return finished_ts < (datetime.now(timezone.utc).timestamp() - _STATUS_RETENTION_SECONDS)


def _snapshot_statuses() -> Dict[int, Dict[str, Any]]:
    return copy.deepcopy(_statuses)


def _with_profile_repo(operation_name: str, callback):
    del operation_name
    db = SessionLocal()
    try:
        repo = ProfileRepository(db)
        return callback(repo)
    except (OperationalError, ProgrammingError) as exc:
        diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_OPERATION_FAILED)
        log_failure(logger, diagnostic, level=logging.DEBUG)
        return None
    except Exception as exc:
        diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_OPERATION_FAILED)
        log_failure(logger, diagnostic, level=logging.WARNING)
        return None
    finally:
        db.close()


def _persist_status_entry(profile_id: int, entry: Dict[str, Any]) -> None:
    payload = _normalize_status_entry(entry)
    _with_profile_repo(
        f"persist search status for profile {profile_id}",
        lambda repo: repo.update_search_status(profile_id, payload),
    )


def _clear_persisted_status(profile_id: int) -> None:
    _with_profile_repo(
        f"clear search status for profile {profile_id}",
        lambda repo: repo.clear_search_status(profile_id),
    )


def _load_persisted_status(profile_id: int) -> Dict[str, Any] | None:
    result = _with_profile_repo(
        f"load search status for profile {profile_id}",
        lambda repo: repo.get_search_status(profile_id),
    )
    return _sanitize_loaded_status(result) if isinstance(result, dict) else None


def _load_statuses(user_id: Optional[int] = None) -> Dict[int, Dict[str, Any]]:
    result = _with_profile_repo(
        "load persisted search statuses",
        lambda repo: repo.get_search_statuses(user_id=user_id),
    )
    if not isinstance(result, dict):
        return {}
    return {
        profile_id: _sanitize_loaded_status(entry)
        for profile_id, entry in result.items()
        if isinstance(entry, dict)
    }


def _clear_stale_persisted_statuses() -> None:
    _with_profile_repo(
        "clear stale persisted search statuses",
        lambda repo: repo.clear_stale_search_statuses(
            max_age_seconds=_STATUS_RETENTION_SECONDS,
            terminal_states=sorted(_TERMINAL_STATES),
        ),
    )


def _active_lock_ttl_seconds() -> int:
    """Return a safe stale-lock TTL for active searches."""
    try:
        configured_timeout = int(getattr(settings, "SEARCH_PIPELINE_TIMEOUT_SECONDS", 1800))
    except (TypeError, ValueError, OverflowError):
        configured_timeout = 1800

    normalized_timeout = max(configured_timeout, int(_RESERVATION_TTL_SECONDS))
    capped_timeout = min(normalized_timeout, 24 * 60 * 60)
    return capped_timeout + 60


def _acquire_profile_search_lock(profile_id: int, reservation_token: str) -> bool:
    db = SessionLocal()
    try:
        repo = ProfileRepository(db)
        return repo.acquire_search_lock(
            profile_id,
            reservation_token,
            reservation_ttl_seconds=int(_RESERVATION_TTL_SECONDS),
            active_ttl_seconds=_active_lock_ttl_seconds(),
        )
    finally:
        db.close()


def _activate_profile_search_lock(profile_id: int, reservation_token: str) -> bool:
    db = SessionLocal()
    try:
        repo = ProfileRepository(db)
        return repo.activate_search_lock(profile_id, reservation_token)
    finally:
        db.close()


def _release_profile_search_lock(profile_id: int, reservation_token: str | None = None) -> bool:
    db = SessionLocal()
    try:
        repo = ProfileRepository(db)
        return repo.release_search_lock(profile_id, reservation_token)
    finally:
        db.close()


_statuses: Dict[int, Dict[str, Any]] = {}
_active_tasks: Dict[int, Any] = {}
_reserved_tasks: Dict[int, Dict[str, Any]] = {}


def _cleanup_stale_reservations(now: float | None = None) -> None:
    ts = now if now is not None else time.time()
    stale = [
        profile_id
        for profile_id, reservation in _reserved_tasks.items()
        if (ts - float(reservation.get("reserved_at", 0.0))) > _RESERVATION_TTL_SECONDS
    ]
    for profile_id in stale:
        _reserved_tasks.pop(profile_id, None)
        status_entry = _statuses.get(profile_id)
        if status_entry and status_entry.get("state") == _RESERVED_STATE:
            _statuses.pop(profile_id, None)

    done_tasks = [
        profile_id
        for profile_id, task in _active_tasks.items()
        if hasattr(task, "done") and task.done()
    ]
    for profile_id in done_tasks:
        _active_tasks.pop(profile_id, None)


def _task_slot_is_available(task: Any | None) -> bool:
    if task is None:
        return True
    try:
        return bool(task.done())
    except Exception:
        return True


def _get_local_status(profile_id: int) -> Dict[str, Any] | None:
    with _lock:
        status = _statuses.get(profile_id)
        return copy.deepcopy(status) if status else None


def _load_status_into_memory(profile_id: int) -> Dict[str, Any] | None:
    persisted = _load_persisted_status(profile_id)
    if not persisted:
        return None
    if _status_is_expired(persisted):
        _clear_persisted_status(profile_id)
        return None

    with _lock:
        existing = _statuses.get(profile_id)
        if existing is None or _entry_timestamp_value(persisted) >= _entry_timestamp_value(
            existing
        ):
            _statuses[profile_id] = copy.deepcopy(persisted)
            return copy.deepcopy(_statuses[profile_id])
        return copy.deepcopy(existing)


def _persist_current_status(profile_id: int) -> None:
    with _lock:
        status = _statuses.get(profile_id)
        snapshot = copy.deepcopy(status) if status else None
    if snapshot is not None:
        _persist_status_entry(profile_id, snapshot)


def init_status(
    profile_id: int,
    total_searches: int = 0,
    searches: Optional[List[Dict]] = None,
    user_id: Optional[int] = None,
) -> None:
    """Initialize or reset status when search begins."""
    with _lock:
        _statuses[profile_id] = {
            "diagnostic_schema": _DIAGNOSTIC_SCHEMA,
            "user_id": user_id,
            "state": "generating",
            "terminal_reason": None,
            "total_searches": total_searches,
            "current_search_index": 0,
            "searches_completed": 0,
            "active_search_indices": [],
            "completed_search_indices": [],
            "current_query": "",
            "searches_generated": public_progress_targets(len(searches or [])),
            "jobs_found": 0,
            "jobs_new": 0,
            "jobs_unique": 0,
            "jobs_duplicates": 0,
            "jobs_duplicates_total": 0,
            "jobs_duplicates_runtime": 0,
            "jobs_duplicates_history": 0,
            "jobs_duplicates_catalog_conflicts": 0,
            "jobs_stale_before_save": 0,
            "jobs_skipped": 0,
            "jobs_analyzed": 0,
            "jobs_analyze_total": 0,
            "analysis_targets": [],
            "analysis_current_index": 0,
            "plan_cache_hit": 0,
            "plan_cache_miss": 0,
            "plan_raw_count": 0,
            "plan_unique_count": 0,
            "planner_mode": None,
            "plan_provenance": None,
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
    _persist_current_status(profile_id)


def add_log(profile_id: int, message: object) -> None:
    """Append a registry-sealed, content-free activity or failure message."""
    if not (is_public_activity_message(message) or is_public_diagnostic_message(message)):
        raise TypeError("Persisted search activity must come from the public registry")
    message = sanitize_persisted_message(message)
    status = _get_local_status(profile_id)
    if status is None:
        status = _load_status_into_memory(profile_id)
    if status is None:
        return

    with _lock:
        live_status = _statuses.get(profile_id)
        if live_status is None:
            _statuses[profile_id] = copy.deepcopy(status)
            live_status = _statuses[profile_id]

        live_status.setdefault("log", [])
        live_status["log"].append(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "message": message,
            }
        )
        if len(live_status["log"]) > 100:
            live_status["log"] = live_status["log"][-100:]
        _touch_status_entry(live_status)
    _persist_current_status(profile_id)


def add_failure_log(profile_id: int, diagnostic: FailureDiagnostic) -> None:
    """Persist only the registry-owned public representation of a failure."""
    add_log(profile_id, diagnostic.public_message)


def update_status(profile_id: int, **kwargs) -> None:
    """Update any status fields."""
    invalid = set(kwargs.keys()) - _VALID_STATUS_KEYS
    if invalid:
        logger.warning("update_status called with unknown keys: %s", invalid)
    if "current_query" in kwargs:
        current_query = kwargs["current_query"]
        if current_query and not is_public_progress_label(current_query):
            kwargs["current_query"] = ""
        else:
            kwargs["current_query"] = str(current_query or "")
    if "searches_generated" in kwargs:
        searches = kwargs["searches_generated"]
        kwargs["searches_generated"] = public_progress_targets(
            min(len(searches), 100) if isinstance(searches, list) else 0
        )
    if "analysis_targets" in kwargs:
        targets = kwargs["analysis_targets"]
        kwargs["analysis_targets"] = public_progress_targets(
            min(len(targets), 100) if isinstance(targets, list) else 0
        )
    if kwargs.get("error") is not None:
        error = kwargs["error"]
        if not is_public_diagnostic_message(error):
            diagnostic = unclassified_status_error()
            log_failure(logger, diagnostic)
            kwargs["error"] = diagnostic.public_message
        else:
            kwargs["error"] = sanitize_persisted_message(error)

    status = _get_local_status(profile_id)
    if status is None:
        status = _load_status_into_memory(profile_id)
    if status is None:
        return

    with _lock:
        live_status = _statuses.get(profile_id)
        if live_status is None:
            _statuses[profile_id] = copy.deepcopy(status)
            live_status = _statuses[profile_id]

        live_status.update({k: v for k, v in kwargs.items() if k in _VALID_STATUS_KEYS})
        is_terminal = live_status.get("state") in _TERMINAL_STATES
        if is_terminal and not live_status.get("finished_at"):
            live_status["finished_at"] = datetime.now(timezone.utc).isoformat()
        _touch_status_entry(live_status)
    _persist_current_status(profile_id)


def _merge_with_persisted_statuses(memory: Dict[int, Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    persisted = _prune_stale_reserved_entries(_load_statuses())
    persisted = _prune_old_terminal_statuses(persisted)
    return _merge_status_maps(persisted, memory)


def get_status(profile_id: int) -> Dict[str, Any]:
    """Get current status for a profile."""
    _cleanup_stale_reservations()
    local_status = _get_local_status(profile_id)
    persisted_status = _load_persisted_status(profile_id)

    if persisted_status and _status_is_expired(persisted_status):
        _clear_persisted_status(profile_id)
        persisted_status = None

    merged = _merge_status_maps(
        {profile_id: persisted_status} if persisted_status else {},
        {profile_id: local_status} if local_status else {},
    )
    status = merged.get(profile_id)
    return status if status is not None else {"state": "unknown"}


def get_all_statuses(user_id: Optional[int] = None) -> Dict[int, Dict[str, Any]]:
    """Get all current statuses (filtered by user_id if provided)."""
    _cleanup_stale_reservations()
    _clear_stale_persisted_statuses()

    with _lock:
        memory_snapshot = dict(_statuses)

    merged = _merge_with_persisted_statuses(memory_snapshot)

    merged = _prune_old_terminal_statuses(_prune_stale_reserved_entries(merged))
    if user_id is None:
        return merged
    return {k: v for k, v in merged.items() if v.get("user_id") == user_id}


def clear_status(profile_id: int) -> None:
    """Remove persisted/in-memory status for a profile."""
    with _lock:
        _statuses.pop(profile_id, None)
    _clear_persisted_status(profile_id)


def register_task(profile_id: int, task: Any, reservation_token: str | None = None):
    """Register an active search task."""
    needs_db_activation = reservation_token is not None

    with _lock:
        reservation = _reserved_tasks.get(profile_id)
        if needs_db_activation:
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
        if not _task_slot_is_available(existing):
            logger.warning(
                "register_task: profile %d already has an active task — ignoring duplicate registration",
                profile_id,
            )
            return False

    if needs_db_activation:
        activation_token = reservation_token
        if activation_token is None:
            return False
        try:
            if not _activate_profile_search_lock(profile_id, activation_token):
                logger.warning(
                    "register_task: profile %d DB-backed lock activation failed",
                    profile_id,
                )
                return False
        except Exception as exc:
            diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_OPERATION_FAILED)
            log_failure(logger, diagnostic, level=logging.WARNING)
            return False

    rollback_db_activation = False
    with _lock:
        existing = _active_tasks.get(profile_id)
        if not _task_slot_is_available(existing):
            rollback_db_activation = needs_db_activation
        elif needs_db_activation:
            reservation = _reserved_tasks.get(profile_id)
            if reservation is None or reservation.get("token") != reservation_token:
                rollback_db_activation = True
            else:
                _reserved_tasks.pop(profile_id, None)
                _active_tasks[profile_id] = task
                return True
        else:
            _active_tasks[profile_id] = task
            return True

    if rollback_db_activation:
        try:
            _release_profile_search_lock(profile_id, activation_token)
        except Exception as exc:
            diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_OPERATION_FAILED)
            log_failure(logger, diagnostic, level=logging.WARNING)

    logger.warning(
        "register_task: profile %d activation could not be finalized in memory",
        profile_id,
    )
    return False


def unregister_task(profile_id: int) -> None:
    """Remove a finished or cancelled task from registry."""
    with _lock:
        _reserved_tasks.pop(profile_id, None)
        _active_tasks.pop(profile_id, None)


def get_all_active_tasks() -> dict:
    """Return a snapshot of {profile_id: task} for graceful shutdown."""
    with _lock:
        return dict(_active_tasks)


@overload
def reserve_task(
    profile_id: int,
    *,
    return_token: Literal[True],
    reservation_token: str | None = None,
    user_id: int | None = None,
) -> str | Literal[False]: ...


@overload
def reserve_task(
    profile_id: int,
    *,
    return_token: Literal[False] = False,
    reservation_token: str | None = None,
    user_id: int | None = None,
) -> bool: ...


def reserve_task(
    profile_id: int,
    *,
    return_token: bool = False,
    reservation_token: str | None = None,
    user_id: int | None = None,
) -> bool | str:
    """Reserve a profile before the background task is registered."""
    token = reservation_token or uuid.uuid4().hex

    with _lock:
        _cleanup_stale_reservations()
        if profile_id in _active_tasks or profile_id in _reserved_tasks:
            return False

    try:
        if not _acquire_profile_search_lock(profile_id, token):
            return False
    except Exception as exc:
        diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_OPERATION_FAILED)
        log_failure(logger, diagnostic, level=logging.WARNING)
        return False

    with _lock:
        _reserved_tasks[profile_id] = {
            "reserved_at": time.time(),
            "token": token,
        }
        _statuses[profile_id] = _build_reserved_status_entry(token, user_id=user_id)
    _persist_current_status(profile_id)

    return token if return_token else True


def release_task(profile_id: int, reservation_token: str | None = None) -> bool:
    """Release a previously reserved profile slot."""
    with _lock:
        reservation = _reserved_tasks.get(profile_id)
        in_memory_released = False
        clear_local_reserved_status = False
        if reservation is not None:
            if reservation_token is not None and reservation.get("token") != reservation_token:
                return False
            _reserved_tasks.pop(profile_id, None)
            in_memory_released = True

        status_entry = _statuses.get(profile_id)
        if status_entry and status_entry.get("state") == _RESERVED_STATE:
            _statuses.pop(profile_id, None)
            clear_local_reserved_status = True

    try:
        db_released = _release_profile_search_lock(profile_id, reservation_token)
    except Exception as exc:
        diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_OPERATION_FAILED)
        log_failure(logger, diagnostic, level=logging.WARNING)
        db_released = False

    if clear_local_reserved_status:
        _clear_persisted_status(profile_id)
    else:
        persisted_status = _load_persisted_status(profile_id)
        if persisted_status and persisted_status.get("state") == _RESERVED_STATE:
            _clear_persisted_status(profile_id)

    return in_memory_released or db_released


def cancel_task(profile_id: int):
    """Explicitly cancel the background search task for a profile."""
    with _lock:
        task = _active_tasks.get(profile_id)
        _reserved_tasks.pop(profile_id, None)
        if task:
            task.cancel()
            return True
    return False


async def cancel_and_clear_tasks(profile_ids: list[int]) -> None:
    """Cancel, await and remove every runtime trace for owned search profiles."""

    unique_profile_ids = sorted(set(profile_ids))
    tasks: list[Any] = []
    with _lock:
        for profile_id in unique_profile_ids:
            task = _active_tasks.get(profile_id)
            _reserved_tasks.pop(profile_id, None)
            if task is not None and not task.done():
                task.cancel()
                tasks.append(task)
    caller_cancelled = False
    try:
        if tasks:
            joined = asyncio.gather(*tasks, return_exceptions=True)
            while not joined.done():
                try:
                    await asyncio.shield(joined)
                except asyncio.CancelledError:
                    # Destructive maintenance cannot outlive the workers it is
                    # meant to quiesce. Preserve cancellation, but join first.
                    caller_cancelled = True
            await joined
    finally:
        for profile_id in unique_profile_ids:
            try:
                release_task(profile_id)
            finally:
                clear_status(profile_id)
    if caller_cancelled:
        raise asyncio.CancelledError
