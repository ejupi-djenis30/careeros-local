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
