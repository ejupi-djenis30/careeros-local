"""Exercise resume and backup exports through an installed frozen backend."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _request(
    base_url: str,
    path: str,
    *,
    session_token: str,
    method: str = "GET",
    payload: dict | None = None,
    access_token: str | None = None,
) -> tuple[bytes, dict[str, str]]:
    headers = {"X-CareerOS-Session": session_token}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    request = urllib.request.Request(
        f"{base_url}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read(), {
                name.lower(): value for name, value in response.headers.items()
            }
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}") from exc


def _json_request(*args, **kwargs) -> dict:
    body, _headers = _request(*args, **kwargs)
    value = json.loads(body)
    if not isinstance(value, dict):
        raise RuntimeError("Packaged backend returned a non-object JSON response")
    return value


def _wait_ready(base_url: str, session_token: str) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            ready = _json_request(
                base_url, "/health/ready", session_token=session_token
            )
            if ready.get("status") == "ready":
                return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("Packaged backend did not become ready")


def _exercise_exports(base_url: str, session_token: str, data_dir: Path) -> dict:
    token = _json_request(
        base_url,
        "/auth/register",
        session_token=session_token,
        method="POST",
        payload={"username": "package_smoke", "password": "PackageSmoke123"},
    )["access_token"]
    profile = _json_request(
        base_url,
        "/career-profile",
        session_token=session_token,
        access_token=token,
        method="PUT",
        payload={
            "expected_revision": 0,
            "display_name": "Package Smoke",
            "headline": "Local Career Agent Tester",
            "summary": "Verifies local packaged exports.",
            "preferences": {},
            "facts": [
                {
                    "fact_type": "skill",
                    "position": 0,
                    "verification_status": "confirmed",
                    "payload": {"name": "Local verification", "level": "advanced"},
                }
            ],
            "goals": [],
        },
    )
    fact_id = profile["facts"][0]["id"]
    draft = _json_request(
        base_url,
        "/resumes",
        session_token=session_token,
        access_token=token,
        method="POST",
        payload={
            "title": "Packaged ATS Resume",
            "template_kind": "ats",
            "selected_fact_ids": [fact_id],
            "content_overrides": {},
        },
    )
    version = _json_request(
        base_url,
        f"/resumes/{draft['id']}/publish",
        session_token=session_token,
        access_token=token,
        method="POST",
        payload={"name": "Package acceptance"},
    )
    formats: list[str] = []
    for artifact in version["artifacts"]:
        content, headers = _request(
            base_url,
            f"/resume-artifacts/{artifact['id']}",
            session_token=session_token,
            access_token=token,
        )
        digest = hashlib.sha256(content).hexdigest()
        expected = artifact["sha256"]
        if digest != expected or headers.get("x-content-sha256") != expected:
            raise RuntimeError("Packaged resume artifact failed its hash check")
        formats.append(artifact["format"])
    if sorted(formats) != ["docx", "pdf"]:
        raise RuntimeError("Packaged resume publish did not produce PDF and DOCX")

    backup, headers = _request(
        base_url,
        "/portability/export",
        session_token=session_token,
        access_token=token,
    )
    if headers.get("x-content-sha256") != hashlib.sha256(backup).hexdigest():
        raise RuntimeError("Packaged backup failed its response hash check")
    with zipfile.ZipFile(BytesIO(backup)) as archive:
        names = set(archive.namelist())
        if not {"manifest.json", "payload.json"} <= names:
            raise RuntimeError("Packaged backup is missing its manifest or payload")
        if not any(name.startswith("files/resume-artifacts/") for name in names):
            raise RuntimeError("Packaged backup omitted published resume artifacts")
    export_path = data_dir / "vault" / "package-smoke-export.zip"
    export_path.write_bytes(backup)
    return {
        "formats": sorted(formats),
        "backupBytes": len(backup),
        "backupSha256": hashlib.sha256(backup).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    arguments = parser.parse_args()
    binary = arguments.binary.resolve()
    data_dir = arguments.data_dir.resolve()
    if not binary.is_file() or not data_dir.is_absolute():
        raise RuntimeError("Packaged backend binary and absolute smoke data path are required")
    data_dir.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    token = "package-smoke-" + "x" * 48
    environment = os.environ.copy()
    environment["CAREEROS_DESKTOP_SESSION_TOKEN"] = token
    parent = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(180)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    process = subprocess.Popen(
        [
            str(binary),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--data-dir",
            str(data_dir),
            "--parent-pid",
            str(parent.pid),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
    )
    try:
        base_url = f"http://127.0.0.1:{port}/api/v1"
        _wait_ready(base_url, token)
        result = _exercise_exports(base_url, token, data_dir)
        print(json.dumps({"result": "pass", **result}, separators=(",", ":")))
    finally:
        if parent.poll() is None:
            parent.terminate()
            parent.wait(timeout=10)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)
    if process.returncode is None:
        raise RuntimeError("Packaged backend did not terminate with its parent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
