from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

import pytest


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.mark.acceptance
def test_packaged_backend_starts_ready_and_stops_without_orphan() -> None:
    configured_binary = os.getenv("CAREEROS_SIDECAR_BINARY", "").strip()
    if not configured_binary:
        pytest.skip("CAREEROS_SIDECAR_BINARY is set by the desktop artifact smoke job")
    binary = Path(configured_binary).resolve()
    if not binary.is_file():
        pytest.fail(f"Packaged sidecar does not exist: {binary}")

    data_dir = (Path.cwd() / ".artifacts" / "packaged" / uuid4().hex).resolve()
    data_dir.mkdir(parents=True)
    port = _free_port()
    token = "acceptance-" + "x" * 48
    environment = os.environ.copy()
    environment["CAREEROS_DESKTOP_SESSION_TOKEN"] = token
    native_parent = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    stdout_path = data_dir / "sidecar.stdout.log"
    stderr_path = data_dir / "sidecar.stderr.log"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
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
                str(native_parent.pid),
            ],
            stdout=stdout,
            stderr=stderr,
            env=environment,
        )
    try:
        deadline = time.monotonic() + 90
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/v1/health/ready",
                headers={"X-CareerOS-Session": token},
            )
            try:
                with urllib.request.urlopen(request, timeout=1) as response:
                    payload = json.load(response)
                if payload.get("status") == "ready":
                    break
            except Exception as exc:  # the sidecar may still be migrating
                last_error = exc
                time.sleep(0.2)
        else:
            process.terminate()
            process.wait(timeout=15)
            safe_tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            pytest.fail(f"Packaged sidecar never became ready: {last_error}\n{safe_tail}")

        native_parent.terminate()
        native_parent.wait(timeout=10)
        process.wait(timeout=10)
    finally:
        if native_parent.poll() is None:
            native_parent.kill()
            native_parent.wait(timeout=5)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        shutil.rmtree(data_dir, ignore_errors=True)

    assert process.poll() is not None
