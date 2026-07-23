import errno
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.core.config import settings
from backend.storage import atomic
from backend.storage.atomic import StorageWriteError, atomic_write, resolve_data_path


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


def test_interrupted_atomic_replace_cleans_temporary_file(monkeypatch):
    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        monkeypatch.setattr(settings, "DATA_DIR", directory)

        def interrupted(_source, _destination):
            raise OSError(errno.EINTR, "Interrupted system call")

        monkeypatch.setattr(atomic.os, "replace", interrupted)

        with pytest.raises(StorageWriteError, match="folder access"):
            atomic_write("backups/career.zip", b"complete archive")

        assert not resolve_data_path("backups/career.zip").exists()
        assert list(data_dir.rglob(".write-*")) == []


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
