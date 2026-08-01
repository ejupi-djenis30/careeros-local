from __future__ import annotations

import os
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from backend.db.sqlite import sqlite_url_for_path
from backend.migrations.resources import current_migration_head, migration_resource_directory
from backend.migrations.runtime import MigrationLockTimeout, migration_lock

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _config(database_path: Path) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def _current_heads(database_path: Path) -> set[str]:
    engine = create_engine(sqlite_url_for_path(database_path))
    try:
        with engine.connect() as connection:
            return set(MigrationContext.configure(connection).get_current_heads())
    finally:
        engine.dispose()


@pytest.mark.skipif(os.name == "nt", reason="POSIX owner and mode contract")
def test_direct_alembic_reserves_a_private_database_under_public_umask(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source-data" / "careeros.db"
    previous_umask = os.umask(0o022)
    try:
        command.upgrade(_config(database), "head")
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600


def test_migration_resources_have_one_complete_converged_history() -> None:
    root = migration_resource_directory()
    head = current_migration_head(root)

    assert head
    assert (root / "versions" / "__init__.py").is_file()
    assert len(list((root / "versions").glob("*.py"))) > 1


def test_explicit_alembic_target_wins_over_process_database_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intended = tmp_path / "intended.db"
    process_default = tmp_path / "must-not-be-created.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{process_default.as_posix()}")

    command.upgrade(_config(intended), "head")

    assert _current_heads(intended) == {current_migration_head()}
    assert not process_default.exists()


def test_direct_alembic_rejects_an_outside_target_before_creating_its_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "private-data"
    outside_root = tmp_path / "outside" / "nested"
    database = outside_root / "careeros.db"
    monkeypatch.setenv("DATA_DIR", str(data_root))

    with pytest.raises(ValueError, match="configured data root"):
        command.upgrade(_config(database), "head")

    assert not data_root.exists()
    assert not (tmp_path / "outside").exists()


def test_programmatic_migration_preserves_configparser_path_punctuation(tmp_path: Path) -> None:
    database = tmp_path / "percent%23-vault" / "careeros.db"
    database.parent.mkdir()
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend" / "migrations"))
    config.attributes["database_url"] = sqlite_url_for_path(database)

    command.upgrade(config, "head")

    assert _current_heads(database) == {current_migration_head()}


def test_production_vault_refuses_downgrade_and_stamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "production.db"
    config = _config(database)
    command.upgrade(config, "head")
    expected = _current_heads(database)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="downgrades/stamps are disabled"):
        command.downgrade(config, "-1")
    assert _current_heads(database) == expected

    with pytest.raises(RuntimeError, match="downgrades/stamps are disabled"):
        command.stamp(config, "base")
    assert _current_heads(database) == expected


def test_two_processes_can_upgrade_one_new_vault_without_ddl_races(tmp_path: Path) -> None:
    database = tmp_path / "concurrent.db"
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{database.as_posix()}",
            "ENVIRONMENT": "development",
            "PYTHONPATH": str(PROJECT_ROOT),
            "SQLITE_BUSY_TIMEOUT_MS": "30000",
        }
    )
    command_line = [sys.executable, "-m", "alembic", "upgrade", "head"]
    processes = [
        subprocess.Popen(
            command_line,
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda process: process.communicate(timeout=60), processes))

    for process, (stdout, stderr) in zip(processes, results, strict=True):
        assert process.returncode == 0, f"{stdout}\n{stderr}"
    assert _current_heads(database) == {current_migration_head()}
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migration_lock_is_bounded_and_recovers_after_holder_release(tmp_path: Path) -> None:
    database = tmp_path / "bounded.db"
    entered = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with migration_lock(database):
            entered.set()
            assert release.wait(timeout=5)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert entered.wait(timeout=2)
    try:
        with pytest.raises(MigrationLockTimeout, match="still running"):
            with migration_lock(database, timeout_seconds=0.05):
                pytest.fail("contender acquired an already-held migration lock")
    finally:
        release.set()
        holder.join(timeout=2)
    assert not holder.is_alive()
    with migration_lock(database, timeout_seconds=0.5):
        pass


def test_stale_lock_file_and_crashed_holder_do_not_wedge_startup(tmp_path: Path) -> None:
    database = tmp_path / "crash-recovery.db"
    lock_file = tmp_path / ".crash-recovery.db.migration.lock"
    lock_file.write_bytes(b"stale-owner-metadata")
    with migration_lock(database, timeout_seconds=0.5):
        pass

    sentinel = tmp_path / "holder-ready"
    code = (
        "import sys,time; from pathlib import Path; "
        "from backend.migrations.runtime import migration_lock; "
        "db=Path(sys.argv[1]); ready=Path(sys.argv[2]); "
        "ctx=migration_lock(db); ctx.__enter__(); "
        "ready.write_text('ready', encoding='utf-8'); time.sleep(300)"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT)
    holder = subprocess.Popen(
        [sys.executable, "-c", code, str(database), str(sentinel)],
        cwd=PROJECT_ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5
        while not sentinel.exists() and holder.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert sentinel.is_file() and holder.poll() is None
        with pytest.raises(MigrationLockTimeout):
            with migration_lock(database, timeout_seconds=0.05):
                pytest.fail("parent acquired the child-held lock")
    finally:
        holder.kill()
        holder.wait(timeout=5)

    with migration_lock(database, timeout_seconds=1):
        pass


def test_migration_refuses_a_hardlinked_lock_without_touching_target_or_vault(
    tmp_path: Path,
) -> None:
    database = tmp_path / "hardlink-target.db"
    lock_path = tmp_path / ".hardlink-target.db.migration.lock"
    unrelated = tmp_path / "unrelated-private-file"
    sentinel = b"must-remain-byte-for-byte-identical"
    unrelated.write_bytes(sentinel)
    os.link(unrelated, lock_path)

    with pytest.raises(RuntimeError, match="ordinary local file"):
        command.upgrade(_config(database), "head")

    assert unrelated.read_bytes() == sentinel
    assert lock_path.read_bytes() == sentinel
    assert not database.exists()


def test_migration_refuses_a_symlinked_lock_without_touching_target_or_vault(
    tmp_path: Path,
) -> None:
    database = tmp_path / "symlink-target.db"
    lock_path = tmp_path / ".symlink-target.db.migration.lock"
    unrelated = tmp_path / "unrelated-private-file"
    sentinel = b"must-remain-byte-for-byte-identical"
    unrelated.write_bytes(sentinel)
    try:
        lock_path.symlink_to(unrelated)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable on this filesystem: {exc}")

    with pytest.raises(RuntimeError, match="ordinary local file"):
        command.upgrade(_config(database), "head")

    assert unrelated.read_bytes() == sentinel
    assert lock_path.is_symlink()
    assert not database.exists()


def test_head_schema_matches_registered_model_metadata(tmp_path: Path) -> None:
    database = tmp_path / "schema-drift.db"
    config = _config(database)
    command.upgrade(config, "head")

    command.check(config)
