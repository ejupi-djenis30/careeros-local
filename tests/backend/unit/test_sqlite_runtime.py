import os
import sqlite3
import stat
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from backend.core.config import settings
from backend.db import sqlite as sqlite_runtime
from backend.db.base import configure_sqlite_connection, ensure_sqlite_parent


def _pragma(connection: sqlite3.Connection, name: str) -> object:
    row = connection.execute(f"PRAGMA {name}").fetchone()
    assert row is not None
    return row[0]


def test_file_sqlite_connections_enforce_local_durability_pragmas(tmp_path: Path) -> None:
    database = tmp_path / "runtime.db"
    ensure_sqlite_parent(f"sqlite:///{database.as_posix()}")
    with closing(sqlite3.connect(database)) as connection:
        configure_sqlite_connection(connection, None)

        assert _pragma(connection, "busy_timeout") == settings.SQLITE_BUSY_TIMEOUT_MS
        assert _pragma(connection, "foreign_keys") == 1
        assert _pragma(connection, "secure_delete") == 1
        assert _pragma(connection, "journal_mode") == "wal"
        assert _pragma(connection, "synchronous") == 2
        assert _pragma(connection, "trusted_schema") == 0


def test_in_memory_sqlite_connection_keeps_memory_journal_mode() -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        configure_sqlite_connection(connection, None)

        assert _pragma(connection, "journal_mode") == "memory"
        assert _pragma(connection, "foreign_keys") == 1
        assert _pragma(connection, "synchronous") == 2


@pytest.mark.skipif(os.name == "nt", reason="POSIX owner and mode contract")
def test_source_runtime_creates_private_vault_and_wal_under_public_umask(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source-data" / "careeros.db"
    previous_umask = os.umask(0o022)
    try:
        ensure_sqlite_parent(f"sqlite:///{database.as_posix()}")
        with closing(sqlite3.connect(database)) as connection:
            configure_sqlite_connection(connection, None)
            connection.execute("CREATE TABLE facts (value TEXT NOT NULL)")
            connection.execute("INSERT INTO facts VALUES ('private')")
            connection.commit()

            wal = Path(f"{database}-wal")
            shared_memory = Path(f"{database}-shm")
            assert wal.is_file()
            assert shared_memory.is_file()
            assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
            assert stat.S_IMODE(database.stat().st_mode) == 0o600
            assert stat.S_IMODE(wal.stat().st_mode) == 0o600
            assert stat.S_IMODE(shared_memory.stat().st_mode) == 0o600
    finally:
        os.umask(previous_umask)


@pytest.mark.skipif(os.name == "nt", reason="POSIX fcntl lock contract")
def test_connection_validation_never_opens_a_lock_disrupting_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "runtime.db"
    ensure_sqlite_parent(f"sqlite:///{database.as_posix()}")

    def unexpected_open(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("connection validation must remain lstat-only")

    monkeypatch.setattr(sqlite_runtime.os, "open", unexpected_open)
    with closing(sqlite3.connect(database)) as connection:
        configure_sqlite_connection(connection, None)


@pytest.mark.skipif(os.name == "nt", reason="POSIX fcntl lock contract")
def test_second_connection_validation_preserves_an_active_writer_lock(tmp_path: Path) -> None:
    database = tmp_path / "runtime.db"
    ensure_sqlite_parent(f"sqlite:///{database.as_posix()}")
    first = sqlite3.connect(database, timeout=0.1)
    second: sqlite3.Connection | None = None
    try:
        configure_sqlite_connection(first, None)
        first.execute("CREATE TABLE facts (value TEXT NOT NULL)")
        first.commit()
        first.execute("BEGIN IMMEDIATE")
        first.execute("INSERT INTO facts VALUES ('uncommitted')")

        second = sqlite3.connect(database, timeout=0.1)
        configure_sqlite_connection(second, None)
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sqlite3,sys; c=sqlite3.connect(sys.argv[1],timeout=0); "
                    "\ntry: c.execute('BEGIN IMMEDIATE')"
                    "\nexcept sqlite3.OperationalError as e: "
                    "print('locked' if 'locked' in str(e).lower() else 'error')"
                    "\nelse: print('acquired'); c.rollback()"
                    "\nfinally: c.close()"
                ),
                str(database),
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=10,
        )

        assert probe.stdout.strip() == "locked", probe.stderr
    finally:
        first.rollback()
        if second is not None:
            second.close()
        first.close()
