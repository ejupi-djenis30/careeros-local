from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.desktop.connection_descriptor import (
    MAX_BYTES,
    DescriptorError,
    invalidate_connection_descriptor,
    publish_connection_descriptor,
    read_connection_descriptor,
)
from desktop.connection_publication import connection_publication
from desktop.connection_security import secure_private
from desktop.process_identity import process_identity


@pytest.fixture
def descriptor(tmp_path):
    identity = str(uuid4())
    path = publish_connection_descriptor(tmp_path, "http://127.0.0.1:43127/api/v1", identity)
    return path, identity


def test_private_atomic_roundtrip_and_instance_conditional_cleanup(descriptor):
    path, identity = descriptor
    current = read_connection_descriptor(path)
    assert current.pid == os.getpid() and current.process_start == process_identity(os.getpid())
    assert current.expires_at - current.issued_at == 30
    assert path.stat().st_size <= MAX_BYTES
    assert set(json.loads(path.read_bytes())) == {
        "schema_version",
        "api_base_url",
        "instance_id",
        "pid",
        "process_start",
        "issued_at",
        "expires_at",
    }
    second = str(uuid4())
    publish_connection_descriptor(path.parent.parent, "http://127.0.0.1:43128/api/v1", second)
    invalidate_connection_descriptor(path, identity)
    assert read_connection_descriptor(path).instance_id == second
    invalidate_connection_descriptor(path, second)
    assert not path.exists()
    assert list(path.parent.iterdir()) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"token": "never-authority"},
        {"api_base_url": "http://localhost:43127/api/v1"},
        {"api_base_url": "http://127.0.0.1:04312/api/v1"},
        {"api_base_url": "http://owner@127.0.0.1:43127/api/v1"},
        {"api_base_url": "http://127.0.0.1:43127/api/v1#"},
        {"pid": True},
        {"pid": 0},
        {"process_start": "different-process"},
        {"instance_id": "not-an-instance"},
        {"issued_at": 0, "expires_at": 30},
        {"issued_at": 1, "expires_at": 9999999999},
    ],
)
def test_rejects_wrong_schema_addresses_authority_and_stale_process(descriptor, changes):
    path, _ = descriptor
    data = json.loads(path.read_bytes())
    data.update(changes)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DescriptorError):
        read_connection_descriptor(path)


@pytest.mark.parametrize(
    "payload", [b"x" * (MAX_BYTES + 1), b'{"schema_version":1,"schema_version":1}', b"[]", b"\xff"]
)
def test_rejects_oversize_duplicate_and_non_json(descriptor, payload):
    path, _ = descriptor
    path.write_bytes(payload)
    with pytest.raises(DescriptorError):
        read_connection_descriptor(path)


def test_rejects_hardlinks_and_noncanonical_paths(descriptor):
    path, _ = descriptor
    with pytest.raises(DescriptorError):
        read_connection_descriptor(
            str(path.parent) + os.sep + ".." + os.sep + path.parent.name + os.sep + path.name
        )
    alias = path.parent / "alias.json"
    os.link(path, alias)
    try:
        with pytest.raises(DescriptorError):
            read_connection_descriptor(path)
    finally:
        alias.unlink()


@pytest.mark.skipif(os.name != "nt", reason="Windows path normalization boundary")
@pytest.mark.parametrize("suffix", [".", " ", ":metadata"])
def test_rejects_windows_implicit_aliases_and_alternate_streams(descriptor, suffix):
    path, _ = descriptor
    with pytest.raises(DescriptorError):
        read_connection_descriptor(str(path) + suffix)


def test_rejects_linked_descriptor(descriptor):
    path, _ = descriptor
    link = path.parent / "linked.json"
    try:
        link.symlink_to(path)
    except OSError:
        pytest.skip("This Windows account cannot create symlinks")
    try:
        with pytest.raises(DescriptorError):
            read_connection_descriptor(link)
    finally:
        link.unlink(missing_ok=True)


@pytest.mark.parametrize("target", ["file", "directory"])
def test_rejects_insecure_permissions_including_windows_dacl(descriptor, target):
    path, _ = descriptor
    changed = path if target == "file" else path.parent
    try:
        if os.name == "nt":
            subprocess.run(
                ["icacls", str(changed), "/grant", "*S-1-1-0:(F)"], capture_output=True, check=True
            )
        else:
            changed.chmod(0o777)
        with pytest.raises(DescriptorError):
            read_connection_descriptor(path)
    finally:
        secure_private(changed)


def test_reader_does_not_import_settings_storage_or_database(descriptor):
    path, _ = descriptor
    script = """
import importlib.abc, sys
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.startswith(('backend.core.config', 'backend.db', 'backend.storage')):
            raise AssertionError('Forbidden bootstrap import')
sys.meta_path.insert(0, Deny())
from backend.desktop.connection_descriptor import read_connection_descriptor
from backend.automation.mcp_server import _parser
assert _parser().parse_args(['--connection-file', sys.argv[1]]).connection_file
read_connection_descriptor(sys.argv[1])
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(path)], capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr


def test_publication_waits_for_readiness_and_invalidates_before_shutdown(tmp_path):
    server = SimpleNamespace(started=False, should_exit=False)
    path = tmp_path / "mcp" / "connection.json"
    with connection_publication(server, tmp_path, "http://127.0.0.1:43127/api/v1"):
        time.sleep(0.1)
        assert not path.exists()
        server.started = True
        deadline = time.monotonic() + 3
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert read_connection_descriptor(path).pid == os.getpid()
    assert not path.exists() and not server.should_exit


def test_atomic_publication_failure_preserves_existing_connection(descriptor, monkeypatch):
    path, identity = descriptor
    previous = path.read_bytes()

    def fail_replace(*_args):
        raise OSError("synthetic atomic write failure")

    monkeypatch.setattr("backend.desktop.connection_descriptor.os.replace", fail_replace)
    with pytest.raises(OSError):
        publish_connection_descriptor(path.parent.parent, "http://127.0.0.1:43129/api/v1", identity)
    assert path.read_bytes() == previous
    assert list(path.parent.iterdir()) == [path]


def test_concurrent_reader_does_not_break_atomic_renewal_on_windows(descriptor, monkeypatch):
    path, identity = descriptor
    replacement = str(uuid4())
    read, replace = os.read, os.replace
    reading, release, attempted = Event(), Event(), Event()
    sharing_failures = []

    def hold_first_read(fd, maximum):
        data = read(fd, maximum)
        if not reading.is_set():
            reading.set()
            assert release.wait(2)
        return data

    def observe_replace(*args):
        try:
            return replace(*args)
        except PermissionError:
            sharing_failures.append(True)
            raise
        finally:
            attempted.set()

    with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=2) as pool:
        patch.setattr("backend.desktop.connection_descriptor.os.read", hold_first_read)
        patch.setattr("backend.desktop.connection_descriptor.os.replace", observe_replace)
        reader = pool.submit(read_connection_descriptor, path)
        try:
            assert reading.wait(1)
            publisher = pool.submit(
                publish_connection_descriptor,
                path.parent.parent,
                "http://127.0.0.1:43128/api/v1",
                replacement,
            )
            assert attempted.wait(1)
        finally:
            release.set()
        try:
            reader.result(timeout=2)
        except DescriptorError:
            pass  # A concurrent replacement invalidates only this old snapshot.
        assert publisher.result(timeout=2) == path
    if os.name == "nt":
        assert sharing_failures
    assert read_connection_descriptor(path).instance_id == replacement
    invalidate_connection_descriptor(path, identity)
    assert path.exists()


def test_persistently_locked_descriptor_fails_with_a_bounded_retry(descriptor, monkeypatch):
    path, identity = descriptor
    previous = path.read_bytes()

    def denied(*_args):
        raise PermissionError("synthetic sharing conflict")

    monkeypatch.setattr("backend.desktop.connection_descriptor.os.replace", denied)
    started = time.monotonic()
    with pytest.raises(PermissionError):
        publish_connection_descriptor(path.parent.parent, "http://127.0.0.1:43128/api/v1", identity)
    assert time.monotonic() - started < 2
    assert path.read_bytes() == previous
    assert list(path.parent.iterdir()) == [path]


def test_reader_rejects_dead_process_before_expiry(descriptor):
    path, _ = descriptor
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(20)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        data = json.loads(path.read_bytes())
        data.update(pid=child.pid, process_start=process_identity(child.pid))
        path.write_text(json.dumps(data), encoding="utf-8")
        assert read_connection_descriptor(path).pid == child.pid
        child.terminate()
        child.wait(timeout=5)
        with pytest.raises(DescriptorError):
            read_connection_descriptor(path)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_rejected_second_desktop_start_preserves_active_descriptor(descriptor):
    from backend.desktop.lifecycle import desktop_instance_lease

    path, identity = descriptor
    script = """
import sys
from pathlib import Path
from backend.desktop.lifecycle import desktop_instance_lease, DesktopInstanceAlreadyRunning
from desktop.connection_publication import connection_publication
from types import SimpleNamespace
try:
    with desktop_instance_lease(root=Path(sys.argv[1])):
        with connection_publication(SimpleNamespace(started=True), Path(sys.argv[1]), 'http://127.0.0.1:43128/api/v1'):
            raise AssertionError('Second writer acquired the lease')
except DesktopInstanceAlreadyRunning:
    pass
"""
    with desktop_instance_lease(root=path.parent.parent):
        result = subprocess.run(
            [sys.executable, "-c", script, str(path.parent.parent)],
            capture_output=True,
            text=True,
            timeout=15,
        )
    assert result.returncode == 0, result.stderr
    assert read_connection_descriptor(path).instance_id == identity
