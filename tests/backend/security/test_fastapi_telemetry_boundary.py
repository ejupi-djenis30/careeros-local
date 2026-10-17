"""Keep native FastAPI telemetry inert despite hostile ambient configuration."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROBE = r"""
import json
import ipaddress
import socket
import sys
from pathlib import Path
from unittest.mock import Mock

events = []
connections = []

original_connect = socket.socket.connect
original_create_connection = socket.create_connection
original_getaddrinfo = socket.getaddrinfo

def loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False

def deny_network(*args, **kwargs):
    connections.append("blocked")
    raise AssertionError("Privacy probe attempted network access")

def connect(sock, address):
    if isinstance(address, tuple) and loopback(address[0]):
        return original_connect(sock, address)
    return deny_network()

def create_connection(address, *args, **kwargs):
    if loopback(address[0]):
        return original_create_connection(address, *args, **kwargs)
    return deny_network()

def getaddrinfo(host, *args, **kwargs):
    if loopback(host):
        return original_getaddrinfo("127.0.0.1" if host == "localhost" else host, *args, **kwargs)
    return deny_network()

# Windows event-loop control sockets require loopback; public egress stays blocked.
socket.socket.connect = connect
socket.create_connection = create_connection
socket.getaddrinfo = getaddrinfo

from fastapi import FastAPI
from fastapi.telemetry import _runtime
from fastapi.testclient import TestClient
from opentelemetry import _logs, metrics, trace
from pydantic import BaseModel

tracer_provider = Mock()
tracer_provider.get_tracer.return_value = trace.NoOpTracer()
meter_provider = Mock()
logger_provider = Mock()

def provider(kind, value):
    def get():
        events.append(kind)
        return value
    return get

trace.get_tracer_provider = provider("tracing", tracer_provider)
metrics.get_meter_provider = provider("metrics", meter_provider)
_logs.get_logger_provider = provider("logs", logger_provider)

def export_endpoint(signal):
    events.append("export-configuration")
    return None

_runtime._export_endpoint = export_endpoint

# Prove these ambient providers observe the unguarded upstream defaults.
control = FastAPI()
control.get("/")(lambda: {"ok": True})
with TestClient(control) as client:
    assert client.get("/").status_code == 200
required_control = {"tracing", "metrics", "logs", "export-configuration"}
assert required_control <= set(events), "Positive control did not activate every telemetry channel"
assert not connections, "Positive control attempted network access"
control_events = len(events)
events.clear()

from backend.core.config import settings
settings.DATA_DIR = sys.argv[1]
Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)
from backend.db.base import Base, engine
from backend.main import app
Base.metadata.create_all(engine)

class ValidationBody(BaseModel):
    value: int

@app.post("/_telemetry_boundary/validation")
def validation(body: ValidationBody):
    return {"ok": True}

@app.get("/_telemetry_boundary/failure")
def failure():
    raise RuntimeError("synthetic-private-exception")

with TestClient(app, raise_server_exceptions=False) as client:
    healthy = client.get(
        f"{settings.API_V1_STR}/health/live",
        params={"profile": "synthetic-private-query"},
        headers={"Authorization": "Bearer synthetic-private-header"},
    )
    invalid = client.post(
        "/_telemetry_boundary/validation",
        json={"value": "synthetic-private-body"},
    )
    failed = client.get("/_telemetry_boundary/failure")
    assert healthy.status_code == 200, "Health request failed"
    assert invalid.status_code == 422, "Validation request failed"
    assert failed.status_code == 500, "Exception request failed"

engine.dispose()
print(json.dumps({
    "requests": 3,
    "control_events": control_events,
    "provider_events": len(events),
    "egress_events": len(connections),
}), flush=True)
assert not events, "CareerOS consulted ambient telemetry or export configuration"
assert not connections, "CareerOS attempted network access"
"""


def test_app_does_not_observe_or_export_through_ambient_telemetry(tmp_path: Path) -> None:
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
    environment.update(
        TESTING="1",
        ENVIRONMENT="development",
        SECRET_KEY="synthetic-telemetry-boundary-test-key-at-least-32-bytes",
        OFFLINE_MODE="true",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1",
        FASTAPI_OTEL_AUTO_CONFIGURE="true",
        OTEL_SDK_DISABLED="false",
        OTEL_EXPORTER_OTLP_ENDPOINT="https://telemetry.example.invalid:4318",
        OTEL_TRACES_EXPORTER="otlp",
        OTEL_METRICS_EXPORTER="otlp",
        OTEL_LOGS_EXPORTER="otlp",
    )
    completed = subprocess.run(
        [sys.executable, "-c", PROBE, str(tmp_path / "data")],
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
        raise AssertionError("Privacy probe did not return its event counts") from None
    return_code = completed.returncode
    provider_events = result.get("provider_events")
    assert return_code == 0, (
        f"Isolated telemetry privacy probe failed ({provider_events} provider events)"
    )
    assert result["requests"] == 3
    assert result["control_events"] > 0
    assert result["provider_events"] == 0
    assert result["egress_events"] == 0
    private_output_absent = "synthetic-private-" not in completed.stderr
    assert private_output_absent, "Application diagnostics exposed a synthetic private field"


def test_locked_dependencies_do_not_install_telemetry_sdk_or_exporters() -> None:
    for name in ("requirements.lock", "requirements-dev.lock", "requirements-tooling.lock"):
        packages = {
            re.sub(r"[-_.]+", "-", match.group(1).lower())
            for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
            if (match := re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==", line))
        }
        telemetry_packages = {
            package for package in packages if package.startswith("opentelemetry-")
        }
        assert telemetry_packages <= {"opentelemetry-api"}, (
            "Telemetry implementation entered a lock"
        )
        if name == "requirements.lock":
            assert "opentelemetry-api" in telemetry_packages
