from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from desktop import backend_main


def _case_directory(name: str) -> Path:
    root = (Path.cwd() / ".artifacts" / "desktop-entry" / f"{name}-{uuid4().hex}").resolve()
    root.mkdir(parents=True)
    return root


def test_parse_args_accepts_only_explicit_desktop_values() -> None:
    data_dir = _case_directory("parse")
    try:
        parsed = backend_main.parse_args(
            [
                "--host",
                "127.0.0.1",
                "--port",
                "43127",
                "--data-dir",
                str(data_dir),
                "--parent-pid",
                str(os.getpid() + 1),
            ]
        )
        assert parsed.host == "127.0.0.1"
        assert parsed.port == 43127
        assert parsed.data_dir == data_dir
        assert parsed.parent_pid == os.getpid() + 1
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)


def test_configure_environment_creates_private_vault_and_stable_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = _case_directory("environment")
    monkeypatch.setenv("CAREEROS_DESKTOP_SESSION_TOKEN", "launch-token-" + "x" * 40)
    try:
        arguments = backend_main.DesktopArguments("127.0.0.1", 43127, data_dir, os.getpid() + 1)
        first = backend_main.configure_environment(arguments)
        secret_value = first.installation_secret_path.read_text(encoding="utf-8")
        second = backend_main.configure_environment(arguments)

        assert len(secret_value.strip()) >= 43
        assert second.installation_secret_path.read_text(encoding="utf-8") == secret_value
        assert os.environ["DATABASE_URL"].endswith("/vault/careeros.db")
        assert os.environ["CAREEROS_DESKTOP_MODE"] == "1"
        assert first.database_path.parent.is_dir()
        assert {"assets", "backups", "logs", "models", "staging", "vault"} <= {
            item.name for item in data_dir.iterdir() if item.is_dir()
        }
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)


def test_migration_failure_restores_consistent_backup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = _case_directory("rollback")
    database_path = data_dir / "vault" / "careeros.db"
    database_path.parent.mkdir(parents=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE career_fact (value TEXT NOT NULL)")
        connection.execute("INSERT INTO career_fact VALUES ('preserve-me')")

    monkeypatch.setattr(backend_main, "database_revision_state", lambda *_: ({"old"}, {"new"}))

    def corrupt_then_fail(*_args, **_kwargs) -> None:
        with sqlite3.connect(database_path) as connection:
            connection.execute("DELETE FROM career_fact")
        raise RuntimeError("simulated interrupted migration")

    monkeypatch.setattr(backend_main, "run_alembic_upgrade", corrupt_then_fail)
    try:
        with pytest.raises(backend_main.DesktopMigrationError, match="restored"):
            backend_main.migrate_database(database_path, data_dir / "backups")

        with sqlite3.connect(database_path) as connection:
            assert connection.execute("SELECT value FROM career_fact").fetchone() == (
                "preserve-me",
            )
        assert list((data_dir / "backups").glob("careeros-*.db"))
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)


def test_current_database_skips_backup_and_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = _case_directory("current")
    database_path = data_dir / "vault" / "careeros.db"
    database_path.parent.mkdir(parents=True)
    database_path.touch()
    monkeypatch.setattr(backend_main, "database_revision_state", lambda *_: ({"head"}, {"head"}))
    called = False

    def unexpected_upgrade(*_args, **_kwargs) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(backend_main, "run_alembic_upgrade", unexpected_upgrade)
    try:
        assert backend_main.migrate_database(database_path, data_dir / "backups") is None
        assert called is False
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)


def test_parent_liveness_probe_recognizes_the_test_process() -> None:
    assert backend_main.parent_process_is_alive(os.getpid()) is True
    assert backend_main.parent_process_is_alive(0) is False
