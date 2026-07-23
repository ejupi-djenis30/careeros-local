from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.db.base import ensure_sqlite_parent


def test_file_backed_sqlite_bootstrap_creates_missing_parent() -> None:
    with TemporaryDirectory(prefix="careeros-db-bootstrap-") as directory:
        database = Path(directory) / "nested" / "vault" / "careeros.db"

        ensure_sqlite_parent(f"sqlite:///{database.as_posix()}")

        assert database.parent.is_dir()


def test_in_memory_sqlite_bootstrap_does_not_create_a_directory() -> None:
    with patch("backend.db.base.Path.mkdir") as mkdir:
        ensure_sqlite_parent("sqlite:///:memory:")

    mkdir.assert_not_called()
