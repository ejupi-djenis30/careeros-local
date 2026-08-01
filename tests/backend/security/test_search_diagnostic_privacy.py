import ast
import io
import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

import backend.services.search_status as search_status
from backend.core.diagnostics import (
    ActivityCode,
    FailureCode,
    FailureDiagnostic,
    PublicActivityMessage,
    PublicDiagnosticMessage,
    PublicProgressLabel,
    diagnose_failure,
    log_failure,
    public_activity_message,
)
from backend.core.logging import PrivacyFormatter, PrivacyRedactionFilter


class CandidatePrivatePayloadError(Exception):
    pass


@pytest.fixture(autouse=True)
def isolated_search_status():
    with search_status._lock:
        search_status._statuses.clear()
        search_status._active_tasks.clear()
        search_status._reserved_tasks.clear()
    with patch("backend.services.search_status._persist_current_status"):
        yield
    with search_status._lock:
        search_status._statuses.clear()


def test_public_markers_and_failure_diagnostics_reject_direct_construction():
    with pytest.raises(TypeError):
        PublicDiagnosticMessage("PRIVATE-DIAGNOSTIC-SENTINEL")
    with pytest.raises(TypeError):
        PublicProgressLabel("PRIVATE-PROGRESS-SENTINEL")
    with pytest.raises(TypeError):
        PublicActivityMessage("PRIVATE-ACTIVITY-SENTINEL")
    with pytest.raises(TypeError):
        FailureDiagnostic(
            FailureCode.SEARCH_UNEXPECTED,
            "CandidatePrivatePayloadError",
            "0123456789abcdef",
        )


def test_add_log_rejects_raw_and_forged_activity_messages():
    search_status.init_status(900)
    with pytest.raises(TypeError):
        search_status.add_log(900, "PRIVATE-ACTIVITY-SENTINEL")
    forged = str.__new__(PublicActivityMessage, "PRIVATE-FORGED-ACTIVITY-SENTINEL")
    with pytest.raises(TypeError):
        search_status.add_log(900, forged)

    assert search_status.get_status(900)["log"] == []
    safe = public_activity_message(ActivityCode.PROGRESS_HEARTBEAT, sequence=1)
    search_status.add_log(900, safe)
    assert search_status.get_status(900)["log"][-1]["message"] == safe


def test_forged_failure_diagnostic_is_not_reused_or_logged():
    forged = object.__new__(FailureDiagnostic)
    object.__setattr__(forged, "code", FailureCode.PROVIDER_SEARCH_FAILED)
    object.__setattr__(forged, "exception_type", "ValueError")
    object.__setattr__(forged, "correlation_id", "0123456789abcdef")
    object.__setattr__(forged, "_diagnostic_seal", object())
    carrier = RuntimeError("PRIVATE-FAILURE-SENTINEL")
    carrier.diagnostic = forged

    regenerated = diagnose_failure(carrier, FailureCode.SEARCH_UNEXPECTED)

    assert regenerated is not forged
    assert regenerated.code is FailureCode.SEARCH_UNEXPECTED
    with pytest.raises(TypeError):
        log_failure(logging.getLogger("tests.forged-diagnostic"), forged)
    with pytest.raises(TypeError):
        _ = forged.public_message


def test_forged_marker_instances_fail_closed_at_status_boundary():
    search_status.init_status(
        901,
        searches=[
            {
                "query": "PRIVATE-QUERY-SENTINEL",
                "domain": "PRIVATE-DOMAIN-SENTINEL",
            }
        ],
    )
    forged_message = str.__new__(
        PublicDiagnosticMessage,
        "PRIVATE-DIAGNOSTIC-SENTINEL",
    )
    forged_progress = str.__new__(
        PublicProgressLabel,
        "PRIVATE-PROGRESS-SENTINEL",
    )

    search_status.update_status(
        901,
        current_query=forged_progress,
        searches_generated=[
            {
                "query": "PRIVATE-QUERY-SENTINEL",
                "domain": "PRIVATE-DOMAIN-SENTINEL",
            }
        ],
        analysis_targets=[{"title": "PRIVATE-TITLE-SENTINEL"}],
        error=forged_message,
        log=[{"message": "PRIVATE-LOG-SENTINEL"}],
    )

    status = search_status.get_status(901)
    serialized = json.dumps(status)
    assert status["current_query"] == ""
    assert status["searches_generated"] == [{"index": 1}]
    assert status["analysis_targets"] == [{"index": 1}]
    assert status["error"].startswith("An unclassified internal error detail was suppressed.")
    for sentinel in (
        "PRIVATE-DIAGNOSTIC-SENTINEL",
        "PRIVATE-PROGRESS-SENTINEL",
        "PRIVATE-QUERY-SENTINEL",
        "PRIVATE-DOMAIN-SENTINEL",
        "PRIVATE-TITLE-SENTINEL",
        "PRIVATE-LOG-SENTINEL",
    ):
        assert sentinel not in serialized


def test_persisted_current_schema_drops_unsealed_activity_and_invalid_entries():
    safe_activity = public_activity_message(ActivityCode.PROGRESS_HEARTBEAT, sequence=7)
    safe_failure = diagnose_failure(
        RuntimeError("PRIVATE-FAILURE-SENTINEL"),
        FailureCode.SEARCH_UNEXPECTED,
    ).public_message
    sanitized = search_status._sanitize_loaded_status(
        {
            "diagnostic_schema": search_status._DIAGNOSTIC_SCHEMA,
            "state": "searching",
            "current_query": "PRIVATE-QUERY-SENTINEL",
            "searches_generated": [{"query": "PRIVATE-PLAN-SENTINEL"}],
            "analysis_targets": [{"title": "PRIVATE-TITLE-SENTINEL"}],
            "log": [
                {
                    "time": "2026-07-31T01:00:00+00:00",
                    "message": str(safe_activity),
                },
                {
                    "time": "2026-07-31T01:00:01+00:00",
                    "message": str(safe_failure),
                },
                {
                    "time": "2026-07-31T01:00:02+00:00",
                    "message": "PRIVATE-ACTIVITY-SENTINEL",
                },
                {
                    "time": "not-a-time",
                    "message": str(safe_activity),
                },
                {
                    "time": "2026-07-31T01:00:03+00:00",
                    "message": str(safe_activity),
                    "private": "PRIVATE-EXTRA-KEY-SENTINEL",
                },
            ],
        }
    )

    serialized = json.dumps(sanitized)
    assert sanitized["current_query"] == ""
    assert sanitized["searches_generated"] == [{"index": 1}]
    assert sanitized["analysis_targets"] == [{"index": 1}]
    assert [entry["message"] for entry in sanitized["log"]] == [
        str(safe_activity),
        str(safe_failure),
    ]
    assert "PRIVATE-" not in serialized


def test_schema_one_activity_is_cleared_during_schema_upgrade():
    sanitized = search_status._sanitize_loaded_status(
        {
            "diagnostic_schema": 1,
            "state": "searching",
            "log": [
                {
                    "time": "2026-07-31T01:00:00+00:00",
                    "message": "PRIVATE-SCHEMA-ONE-SENTINEL",
                }
            ],
        }
    )

    assert sanitized["diagnostic_schema"] == search_status._DIAGNOSTIC_SCHEMA
    assert sanitized["log"] == []


def test_failure_log_uses_registry_code_allowlisted_type_and_generated_reference():
    sentinel = "candidate@example.test PRIVATE-QUERY-SENTINEL"
    diagnostic = diagnose_failure(
        CandidatePrivatePayloadError(sentinel),
        FailureCode.PROVIDER_SEARCH_FAILED,
    )
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(PrivacyRedactionFilter())
    handler.setFormatter(PrivacyFormatter("%(message)s"))
    logger = logging.getLogger("tests.search-diagnostic-privacy")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    log_failure(logger, diagnostic)

    rendered = stream.getvalue()
    assert "code=provider_search_failed" in rendered
    assert "exception_type=Exception" in rendered
    assert "correlation_id=" in rendered
    assert len(diagnostic.correlation_id) == 16
    assert sentinel not in rendered
    assert "CandidatePrivatePayloadError" not in rendered


def test_arbitrary_string_arguments_cannot_bypass_privacy_formatter():
    sentinel = "PRIVATE-SENTINEL"
    record = logging.LogRecord(
        name="tests.search-diagnostic-privacy",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="operation_failed code=%s exception_type=%s correlation_id=%s",
        args=(sentinel, sentinel, sentinel),
        exc_info=None,
    )

    assert PrivacyRedactionFilter().filter(record)
    rendered = PrivacyFormatter("%(message)s").format(record)
    assert sentinel not in rendered
    assert rendered.count("[redacted]") == 3


def test_failure_paths_cannot_log_exception_objects_or_raw_status_errors():
    root = Path(__file__).resolve().parents[3]
    source_roots = (root / "backend",)
    violations: list[str] = []

    for source_root in source_roots:
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for handler in (
                node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler) and node.name
            ):
                exception_name = handler.name
                for node in ast.walk(handler):
                    if not isinstance(node, ast.Call):
                        continue
                    function_name = (
                        node.func.attr
                        if isinstance(node.func, ast.Attribute)
                        else node.func.id
                        if isinstance(node.func, ast.Name)
                        else ""
                    )
                    is_logger_call = (
                        isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "logger"
                        and function_name
                        in {"critical", "debug", "error", "exception", "info", "warning"}
                    )
                    if function_name != "add_log" and not is_logger_call:
                        continue
                    if any(
                        isinstance(descendant, ast.Name) and descendant.id == exception_name
                        for argument in (*node.args, *[kw.value for kw in node.keywords])
                        for descendant in ast.walk(argument)
                    ):
                        violations.append(
                            f"{path.relative_to(root)}:{node.lineno} logs exception variable "
                            f"{exception_name}"
                        )

            for node in (item for item in ast.walk(tree) if isinstance(item, ast.Call)):
                function_name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                is_logger_call = (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "logger"
                )
                if is_logger_call and function_name == "exception":
                    violations.append(
                        f"{path.relative_to(root)}:{node.lineno} uses traceback logging"
                    )
                if (
                    "providers" in path.parts
                    and is_logger_call
                    and function_name
                    in {
                        "critical",
                        "debug",
                        "error",
                        "info",
                        "warning",
                    }
                ):
                    if any(isinstance(argument, ast.JoinedStr) for argument in node.args):
                        violations.append(
                            f"{path.relative_to(root)}:{node.lineno} uses provider f-string logging"
                        )
                if function_name == "update_status":
                    for keyword in node.keywords:
                        if keyword.arg != "error":
                            continue
                        allowed = (
                            isinstance(keyword.value, ast.Call)
                            and isinstance(keyword.value.func, ast.Name)
                            and keyword.value.func.id == "public_status_message"
                        ) or (
                            isinstance(keyword.value, ast.Attribute)
                            and keyword.value.attr == "public_message"
                        )
                        if not allowed:
                            violations.append(
                                f"{path.relative_to(root)}:{node.lineno} writes a raw status error"
                            )
                if function_name == "add_log":
                    message_argument = node.args[1] if len(node.args) > 1 else None
                    allowed = (
                        isinstance(message_argument, ast.Call)
                        and isinstance(message_argument.func, ast.Name)
                        and message_argument.func.id == "public_activity_message"
                    ) or (
                        isinstance(message_argument, ast.Attribute)
                        and message_argument.attr == "public_message"
                    )
                    if not allowed:
                        violations.append(
                            f"{path.relative_to(root)}:{node.lineno} writes raw search activity"
                        )

    assert violations == []
