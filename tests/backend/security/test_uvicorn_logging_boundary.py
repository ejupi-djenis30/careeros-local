"""Exercise the production logging boundary with Uvicorn's real configuration."""

from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.core.logging import PrivacyFormatter, PrivacyRedactionFilter

ROOT = Path(__file__).resolve().parents[3]
PROBE = r"""
import contextlib
import io
import json
import logging
import sys
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

private = "synthetic-private-uvicorn-boundary"
stream = io.StringIO()
original_stdout, original_stdin = sys.stdout, sys.stdin

def report_exception():
    try:
        raise RuntimeError(private)
    except RuntimeError:
        logging.getLogger("uvicorn.error").error("Exception in ASGI application", exc_info=True)

with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
    probe_stdout = sys.stdout
    if sys.argv[1] == "app-first":
        from backend.main import app
    configuration = uvicorn.Config(
        "backend.main:app", access_log=True, log_level="trace",
        server_header=False, proxy_headers=False,
    )
    report_exception()
    positive_control = private in stream.getvalue()
    stream.seek(0)
    stream.truncate(0)
    configuration.load()
    from backend.main import app
    from backend.core.diagnostics import FailureCode, diagnose_failure, log_failure
    from backend.db.base import Base, engine

    Base.metadata.create_all(engine)
    with TestClient(configuration.loaded_app) as client:
        assert client.get("/api/v1/health/live", params={"q": private}).status_code == 200
        assert client.get("/" + private).status_code == 404
        report_exception()
        # Uvicorn lifespan failures can arrive as a preformatted message, not exc_info.
        logging.getLogger("uvicorn.error").error("opaque " + private)
        logging.getLogger("uvicorn.asgi").log(5, "opaque " + private)
        for request_target in ("/?q=" + private, "/" + private):
            logging.getLogger("uvicorn.access").info(
                '%s - "%s %s HTTP/%s" %d',
                "203.0.113.17:49152", "GET", request_target, "1.1", 200,
            )
        logging.getLogger("backend.logging_probe").info("rows=%d success=%s", 7, True)
        log_failure(
            logging.getLogger("uvicorn.error"),
            diagnose_failure(RuntimeError(private), FailureCode.HTTP_REQUEST_FAILED),
        )
    engine.dispose()
    stdio_unchanged = sys.stdout is probe_stdout and sys.stdin is original_stdin

output = stream.getvalue()
print(json.dumps({
    "positive_control": positive_control,
    "private_absent": private not in output,
    "traceback_absent": "Traceback (most recent call last)" not in output,
    "logging_error_absent": "--- Logging error ---" not in output,
    "exception_type_retained": "exception_type=RuntimeError" in output,
    "safe_metrics_retained": "rows=7 success=True" in output,
    "structured_code_retained": "code=http_request_failed" in output,
    "correlation_retained": "correlation_id=" in output,
    "access_status_retained": "http_request method=GET status=200" in output,
    "asgi_trace_observed": "asgi_event" in output,
    "client_ip_absent": "203.0.113.17" not in output,
    "stdio_unchanged": stdio_unchanged and sys.stdout is original_stdout,
}), flush=True)
"""


@pytest.mark.parametrize("ordering", ["config-first", "app-first"])
def test_real_uvicorn_configuration_preserves_private_logs(tmp_path: Path, ordering: str) -> None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("OTEL_", "FASTAPI_", "CAREEROS_DESKTOP_"))
        and key
        not in {
            "DATA_DIR",
            "DATABASE_URL",
            "CAREEROS_SECRET_FILE",
            "CAREEROS_MCP_TOKEN",
            "PYTHONPATH",
            "PYTHONHOME",
        }
    }
    data = tmp_path / "data"
    data.mkdir()
    environment.update(
        TESTING="1",
        ENVIRONMENT="development",
        SECRET_KEY="synthetic-logging-boundary-test-key-at-least-32-bytes",
        OFFLINE_MODE="true",
        DATA_DIR=str(data),
        DATABASE_URL=f"sqlite:///{(data / 'vault.db').as_posix()}",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1",
    )
    completed = subprocess.run(
        [sys.executable, "-c", PROBE, ordering],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise AssertionError("Isolated logging probe did not return its checks") from None
    assert completed.returncode == 0, "Isolated logging probe failed"
    assert result["positive_control"], "Uvicorn positive control did not expose the baseline"
    for check in (
        "private_absent",
        "traceback_absent",
        "logging_error_absent",
        "exception_type_retained",
        "safe_metrics_retained",
        "structured_code_retained",
        "correlation_retained",
        "access_status_retained",
        "asgi_trace_observed",
        "client_ip_absent",
        "stdio_unchanged",
    ):
        assert result[check], f"Logging privacy contract failed: {check}"
    stderr_empty = not completed.stderr
    assert stderr_empty, "Logging probe emitted diagnostics outside its capture"


def test_uvicorn_access_metadata_survives_two_handlers() -> None:
    streams = [io.StringIO(), io.StringIO()]
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("203.0.113.17:49152", "GET", "/synthetic-private-target", "1.1", 200),
        None,
    )
    for stream in streams:
        handler = logging.StreamHandler(stream)
        handler.addFilter(PrivacyRedactionFilter())
        handler.setFormatter(PrivacyFormatter("%(message)s"))
        handler.handle(record)
    expected = "http_request method=GET status=200\n"
    both_match = all(stream.getvalue() == expected for stream in streams)
    assert both_match, "A later privacy handler lost or exposed request metadata"


@pytest.mark.parametrize("exception_info_available", [True, False])
def test_privacy_formatter_rejects_cached_exception_details(exception_info_available: bool) -> None:
    private = "synthetic-private-cached-exception"
    try:
        raise RuntimeError(private)
    except RuntimeError:
        record = logging.LogRecord(
            "tests.logging.cached",
            logging.ERROR,
            __file__,
            1,
            "operation failed",
            (),
            sys.exc_info(),
        )
    logging.Formatter().format(record)
    cached = record.exc_text
    if not exception_info_available:
        record.exc_info = None
    PrivacyRedactionFilter().filter(record)
    output = PrivacyFormatter("%(message)s").format(record)
    private_absent = private not in output
    traceback_absent = "Traceback (most recent call last)" not in output
    assert private_absent, "Cached exception message escaped the privacy formatter"
    assert traceback_absent, "Cached traceback escaped the privacy formatter"
    assert record.exc_text == cached, "Formatting mutated another handler's exception cache"
    if exception_info_available:
        assert "exception_type=RuntimeError" in output
