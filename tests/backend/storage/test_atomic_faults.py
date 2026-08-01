import errno
import hashlib
import os
import stat
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.core.config import settings
from backend.storage import atomic
from backend.storage.atomic import (
    StorageWriteError,
    atomic_write,
    cleanup_stale_atomic_writes,
    durable_replace,
    read_stable_bounded_file,
    read_verified,
    resolve_data_path,
)


def test_disk_full_removes_partial_file_and_leaves_no_destination(monkeypatch):
    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        monkeypatch.setattr(settings, "DATA_DIR", directory)

        def disk_full(_descriptor):
            raise OSError(errno.ENOSPC, "No space left on device")

        monkeypatch.setattr(atomic.os, "fsync", disk_full)

        with pytest.raises(StorageWriteError, match="free disk space"):
            atomic_write("exports/resume.pdf", b"partial resume")

        assert not resolve_data_path("exports/resume.pdf").exists()
        assert list(data_dir.rglob(".write-*")) == []


def test_interrupted_atomic_publish_cleans_temporary_file(monkeypatch):
    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        monkeypatch.setattr(settings, "DATA_DIR", directory)

        def interrupted(_source, _destination):
            raise OSError(errno.EINTR, "Interrupted system call")

        monkeypatch.setattr(atomic.os, "link", interrupted)

        with pytest.raises(StorageWriteError, match="folder access"):
            atomic_write("backups/career.zip", b"complete archive")

        assert not resolve_data_path("backups/career.zip").exists()
        assert list(data_dir.rglob(".write-*")) == []


def test_concurrent_identical_writes_publish_once_without_replacement(monkeypatch):
    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        monkeypatch.setattr(settings, "DATA_DIR", directory)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda _index: atomic_write("assets/aa/shared.bin", b"same bytes"),
                    range(32),
                )
            )

        assert sum(created for _path, created in results) == 1
        assert resolve_data_path("assets/aa/shared.bin").read_bytes() == b"same bytes"
        assert list(data_dir.rglob(".write-*")) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX hard-link ctime contract")
def test_winner_validation_allows_private_hard_link_cleanup_during_read(
    monkeypatch,
    tmp_path,
):
    payload = b"immutable content-addressed bytes"
    destination = tmp_path / "published.bin"
    private_alias = tmp_path / ".write-published-private"
    destination.write_bytes(payload)
    os.link(destination, private_alias)
    initial = destination.stat()
    assert initial.st_nlink == 2

    original_read = atomic.os.read
    cleaned = False

    def read_after_cleanup(descriptor, maximum_size):
        nonlocal cleaned
        if not cleaned:
            private_alias.unlink()
            cleaned = True
        return original_read(descriptor, maximum_size)

    monkeypatch.setattr(atomic.os, "read", read_after_cleanup)

    assert atomic._read_regular_file_exact(destination, len(payload)) == payload
    final = destination.stat()
    assert cleaned is True
    assert final.st_nlink == 1
    assert final.st_mtime_ns == initial.st_mtime_ns
    assert final.st_ctime_ns != initial.st_ctime_ns


@pytest.mark.skipif(os.name == "nt", reason="POSIX ctime contract")
def test_recovery_read_rejects_ctime_change_during_read(monkeypatch, tmp_path):
    payload = b"single-link recovery metadata"
    destination = tmp_path / "journal.json"
    destination.write_bytes(payload)
    initial = destination.stat()
    changed_mode = initial.st_mode ^ stat.S_IXUSR

    original_read = atomic.os.read
    changed = False

    def read_after_metadata_change(descriptor, maximum_size):
        nonlocal changed
        if not changed:
            destination.chmod(changed_mode)
            changed = True
        return original_read(descriptor, maximum_size)

    monkeypatch.setattr(atomic.os, "read", read_after_metadata_change)

    with pytest.raises(ValueError, match="changed while it was being read"):
        read_stable_bounded_file(
            destination,
            maximum_size=len(payload),
            expected_size=len(payload),
        )
    final = destination.stat()
    assert changed is True
    assert final.st_mtime_ns == initial.st_mtime_ns
    assert final.st_ctime_ns != initial.st_ctime_ns


@pytest.mark.skipif(atomic.os.name != "nt", reason="Win32 extended path alias")
def test_windows_extended_paths_compare_as_the_same_containment_root():
    assert atomic._path_for_containment(r"\\?\C:\Private\CareerOS") == (
        atomic._path_for_containment(r"C:\Private\CareerOS")
    )
    assert atomic._path_for_containment(r"\\?\UNC\server\share\CareerOS") == (
        atomic._path_for_containment(r"\\server\share\CareerOS")
    )


def test_concurrent_conflicting_write_never_replaces_winner(monkeypatch):
    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        monkeypatch.setattr(settings, "DATA_DIR", directory)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(atomic_write, "assets/aa/shared.bin", payload)
                for payload in (b"first value", b"second value")
            ]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except ValueError:
                outcomes.append(None)

        assert sum(outcome is not None for outcome in outcomes) == 1
        assert resolve_data_path("assets/aa/shared.bin").read_bytes() in {
            b"first value",
            b"second value",
        }
        assert list(data_dir.rglob(".write-*")) == []


def test_startup_cleanup_removes_only_stale_asset_and_resume_temporaries(monkeypatch):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        monkeypatch.setattr(settings, "DATA_DIR", directory)
        stale = [
            root / "assets" / "aa" / ".write-source-private",
            root / "resumes" / "profile" / ".write-resume-private",
        ]
        unrelated = root / "models" / ".write-runtime-keep"
        for path in [*stale, unrelated]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"private")

        assert cleanup_stale_atomic_writes() == 2
        assert all(not path.exists() for path in stale)
        assert unrelated.read_bytes() == b"private"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction contract")
def test_startup_cleanup_never_traverses_a_nested_windows_junction(monkeypatch):
    with TemporaryDirectory() as data_directory, TemporaryDirectory() as outside_directory:
        root = Path(data_directory)
        outside = Path(outside_directory)
        assets = root / "assets" / "inside"
        assets.mkdir(parents=True)
        external = outside / ".write-external-private"
        external.write_bytes(b"must survive")
        junction = assets / "junction"
        monkeypatch.setattr(settings, "DATA_DIR", data_directory)

        creation = subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
            capture_output=True,
            check=False,
            text=True,
        )
        if creation.returncode != 0:
            pytest.skip(f"Directory junctions are unavailable: {creation.stderr.strip()}")
        try:
            assert cleanup_stale_atomic_writes() == 0
            assert external.read_bytes() == b"must survive"
        finally:
            # Remove only the junction entry so TemporaryDirectory never needs
            # to reason about the external target.
            os.rmdir(junction)


def test_startup_cleanup_revalidates_a_namespace_swapped_to_a_symlink(
    monkeypatch,
    tmp_path,
):
    root = tmp_path / "data"
    assets = root / "assets"
    original_assets = root / "assets-original"
    outside = tmp_path / "outside"
    assets.mkdir(parents=True)
    outside.mkdir()
    external = outside / ".write-external-private"
    external.write_bytes(b"must survive")
    probe = root / "symlink-probe"
    monkeypatch.setattr(settings, "DATA_DIR", str(root))
    try:
        probe.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Directory symlinks are unavailable: {exc}")
    probe.unlink()

    def swap_namespace(_root: Path, _remaining: list[int] | None = None) -> list[Path]:
        assets.rename(original_assets)
        assets.symlink_to(outside, target_is_directory=True)
        return [assets / external.name]

    monkeypatch.setattr(atomic, "_stale_atomic_write_candidates", swap_namespace)
    try:
        assert cleanup_stale_atomic_writes() == 0
        assert external.read_bytes() == b"must survive"
    finally:
        assets.unlink(missing_ok=True)
        original_assets.rename(assets)


def test_startup_cleanup_scan_limit_fails_before_unlinking_any_candidate(
    monkeypatch,
    tmp_path,
):
    root = tmp_path / "data"
    assets = root / "assets"
    assets.mkdir(parents=True)
    stale = assets / ".write-private"
    stale.write_bytes(b"must survive an incomplete scan")
    (assets / "ordinary-a.bin").write_bytes(b"a")
    (assets / "ordinary-b.bin").write_bytes(b"b")
    monkeypatch.setattr(settings, "DATA_DIR", str(root))
    monkeypatch.setattr(atomic, "_STALE_ATOMIC_WRITE_SCAN_LIMIT", 2)

    with pytest.raises(StorageWriteError, match="scan limit"):
        cleanup_stale_atomic_writes()

    assert stale.read_bytes() == b"must survive an incomplete scan"


def test_startup_cleanup_scans_every_namespace_before_any_unlink(
    monkeypatch,
    tmp_path,
):
    root = tmp_path / "data"
    assets = root / "assets"
    resumes = root / "resumes"
    assets.mkdir(parents=True)
    resumes.mkdir(parents=True)
    asset_stale = assets / ".write-asset-private"
    asset_stale.write_bytes(b"must survive a later namespace failure")
    (resumes / "ordinary-a.bin").write_bytes(b"a")
    (resumes / "ordinary-b.bin").write_bytes(b"b")
    monkeypatch.setattr(settings, "DATA_DIR", str(root))
    monkeypatch.setattr(atomic, "_STALE_ATOMIC_WRITE_SCAN_LIMIT", 2)

    with pytest.raises(StorageWriteError, match="scan limit"):
        cleanup_stale_atomic_writes()

    assert asset_stale.read_bytes() == b"must survive a later namespace failure"


def test_existing_durable_content_is_never_overwritten(monkeypatch):
    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        monkeypatch.setattr(settings, "DATA_DIR", directory)
        destination, created = atomic_write("resumes/version.pdf", b"published version")
        assert created is True

        with pytest.raises(ValueError, match="does not match"):
            atomic_write("resumes/version.pdf", b"corrupted replacement")

        assert destination.read_bytes() == b"published version"
        assert list(data_dir.rglob(".write-*")) == []


def test_verified_reads_are_exactly_bounded_by_recorded_metadata(monkeypatch):
    with TemporaryDirectory() as directory:
        monkeypatch.setattr(settings, "DATA_DIR", directory)
        payload = b"verified private bytes"
        source = Path(directory) / "assets" / "private.bin"
        source.parent.mkdir(parents=True)
        source.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()

        assert (
            read_verified(
                "assets/private.bin",
                digest,
                expected_size=len(payload),
                maximum_size=1024,
            )
            == payload
        )
        with pytest.raises(ValueError, match="bounded regular file"):
            read_verified(
                "assets/private.bin",
                digest,
                expected_size=len(payload) - 1,
                maximum_size=1024,
            )
        with pytest.raises(ValueError, match="metadata"):
            read_verified(
                "assets/private.bin",
                digest,
                expected_size=1025,
                maximum_size=1024,
            )


def test_stable_bounded_file_reads_are_repeatable_under_parallel_windows_load(
    tmp_path,
) -> None:
    payload = b"descriptor stable journal bytes" * 32
    source = tmp_path / "journal.json"
    source.write_bytes(payload)

    def read_once(_index: int) -> bytes:
        return read_stable_bounded_file(
            source,
            expected_size=len(payload),
            maximum_size=len(payload),
        )

    for _round in range(5):
        with ThreadPoolExecutor(max_workers=16) as executor:
            assert all(result == payload for result in executor.map(read_once, range(128)))


@pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "mkfifo"),
    reason="POSIX FIFO no-block contract",
)
def test_special_file_cannot_block_verified_read_or_winner_validation(monkeypatch):
    with TemporaryDirectory() as directory:
        monkeypatch.setattr(settings, "DATA_DIR", directory)
        fifo = Path(directory) / "assets" / "hostile.fifo"
        fifo.parent.mkdir(parents=True)
        os.mkfifo(fifo)
        digest = hashlib.sha256(b"x").hexdigest()

        started = time.monotonic()
        with pytest.raises(ValueError, match="bounded regular file"):
            read_verified(
                "assets/hostile.fifo",
                digest,
                expected_size=1,
                maximum_size=1024,
            )
        with pytest.raises(ValueError, match="does not match"):
            atomic_write("assets/hostile.fifo", b"x")
        assert time.monotonic() - started < 2.0


def test_durable_replace_atomically_replaces_an_existing_destination(tmp_path):
    source = tmp_path / "replacement.tmp"
    destination = tmp_path / "published.bin"
    source.write_bytes(b"new durable bytes")
    destination.write_bytes(b"old bytes")

    durable_replace(source, destination)

    assert not source.exists()
    assert destination.read_bytes() == b"new durable bytes"


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.bin",
        "assets/../../outside.bin",
        "/absolute/path.bin",
        "C:/Windows/system.ini",
        r"C:\Windows\system.ini",
        r"\\server\share\private.bin",
        r"assets\..\outside.bin",
        "assets//outside.bin",
        "assets/./outside.bin",
    ],
)
def test_resolve_data_path_rejects_non_portable_or_escaping_paths(monkeypatch, unsafe_path):
    with TemporaryDirectory() as directory:
        monkeypatch.setattr(settings, "DATA_DIR", directory)

        with pytest.raises(ValueError):
            resolve_data_path(unsafe_path)


def test_resolve_data_path_accepts_canonical_string_and_path_inputs(monkeypatch):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        monkeypatch.setattr(settings, "DATA_DIR", directory)

        assert resolve_data_path("assets/ab/file.bin") == root / "assets" / "ab" / "file.bin"
        assert resolve_data_path(Path("assets") / "ab" / "file.bin") == (
            root / "assets" / "ab" / "file.bin"
        )


def test_resolve_data_path_can_validate_without_creating_the_data_root(monkeypatch):
    with TemporaryDirectory() as directory:
        root = Path(directory) / "not-created"
        monkeypatch.setattr(settings, "DATA_DIR", str(root))

        resolved = resolve_data_path("assets/file.bin", create_root=False)

        assert resolved == root / "assets" / "file.bin"
        assert not root.exists()


def test_resolve_data_path_rejects_symlink_escape(monkeypatch):
    with TemporaryDirectory() as data_directory, TemporaryDirectory() as outside_directory:
        root = Path(data_directory)
        outside = Path(outside_directory)
        monkeypatch.setattr(settings, "DATA_DIR", data_directory)
        link = root / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"Directory symlinks are unavailable: {exc}")

        with pytest.raises(ValueError, match="escapes"):
            resolve_data_path("linked/private.bin")


def test_resolve_data_path_rejects_sibling_prefix_symlink_escape(monkeypatch):
    with TemporaryDirectory() as directory:
        parent = Path(directory)
        root = parent / "vault"
        sibling = parent / "vault-copy"
        root.mkdir()
        sibling.mkdir()
        monkeypatch.setattr(settings, "DATA_DIR", str(root))
        link = root / "linked"
        try:
            link.symlink_to(sibling, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"Directory symlinks are unavailable: {exc}")

        with pytest.raises(ValueError, match="escapes"):
            resolve_data_path("linked/private.bin")


def test_resolve_data_path_rejects_symlink_alias_inside_data_root(monkeypatch):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        target = root / "assets" / "actual.bin"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"private")
        alias = root / "assets" / "alias.bin"
        monkeypatch.setattr(settings, "DATA_DIR", directory)
        try:
            alias.symlink_to(target)
        except OSError as exc:
            pytest.skip(f"File symlinks are unavailable: {exc}")

        with pytest.raises(ValueError, match="symbolic link or reparse point"):
            resolve_data_path("assets/alias.bin")
