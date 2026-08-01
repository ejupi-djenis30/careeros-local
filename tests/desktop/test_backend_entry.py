from __future__ import annotations

import os
import shutil
import sqlite3
import stat
import tempfile
import threading
from collections.abc import Iterator
from contextlib import closing
from multiprocessing import get_context
from pathlib import Path

import pytest

from backend.db.sqlite import ensure_sqlite_database_parent
from desktop import backend_main


def _try_instance_lease(root: str, result_queue) -> None:
    from backend.desktop.lifecycle import DesktopInstanceAlreadyRunning, desktop_instance_lease

    try:
        with desktop_instance_lease(root=Path(root)):
            result_queue.put("acquired")
    except DesktopInstanceAlreadyRunning:
        result_queue.put("blocked")


def _case_directory(name: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=f"careeros-desktop-{name}-")).resolve()


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Avoid pytest's Windows `*current` directory links in x64-on-ARM runs."""
    root = _case_directory("pytest")
    try:
        yield root
    finally:
        shutil.rmtree(root)


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
        shutil.rmtree(data_dir)


def test_parse_args_rejects_a_relative_desktop_data_directory() -> None:
    with pytest.raises(SystemExit):
        backend_main.parse_args(
            [
                "--host",
                "127.0.0.1",
                "--port",
                "43127",
                "--data-dir",
                "relative-vault",
                "--parent-pid",
                str(os.getpid() + 1),
            ]
        )


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
        shutil.rmtree(data_dir)


def test_installation_secret_rejects_links_oversize_and_noncanonical_bytes(
    tmp_path: Path,
) -> None:
    secret = tmp_path / ".installation-secret"
    secret.write_text("x" * 260, encoding="utf-8")
    with pytest.raises(RuntimeError, match="bounded regular file"):
        backend_main._write_installation_secret(secret)

    secret.write_text("x" * 48 + " ", encoding="utf-8")
    with pytest.raises(RuntimeError, match="invalid"):
        backend_main._write_installation_secret(secret)

    secret.unlink()
    target = tmp_path / "target"
    target.write_text("x" * 48, encoding="utf-8")
    os.link(target, secret)
    try:
        with pytest.raises(RuntimeError, match="ambiguous hard-link identity"):
            backend_main._write_installation_secret(secret)
    finally:
        secret.unlink(missing_ok=True)

    try:
        secret.symlink_to(target)
    except OSError:
        pytest.skip("The test account cannot create a file symlink")
    try:
        with pytest.raises(RuntimeError, match="bounded regular file"):
            backend_main._write_installation_secret(secret)
    finally:
        secret.unlink(missing_ok=True)


def test_installation_secret_recovers_a_completed_publish_after_process_kill(
    tmp_path: Path,
) -> None:
    secret = tmp_path / ".installation-secret"
    temporary = tmp_path / f".{secret.name}.{'a' * 32}.tmp"
    value = "x" * 64
    temporary.write_text(f"{value}\n", encoding="utf-8")
    os.link(temporary, secret)
    assert secret.stat().st_nlink == 2

    assert backend_main._write_installation_secret(secret) == value
    assert not temporary.exists()
    assert secret.stat().st_nlink == 1


def test_installation_secret_publish_fault_never_exposes_a_partial_final_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = tmp_path / ".installation-secret"

    def fail_publish(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated publication fault")

    monkeypatch.setattr(backend_main.os, "link", fail_publish)
    with pytest.raises(OSError, match="publication fault"):
        backend_main._write_installation_secret(secret)

    assert not secret.exists()
    assert list(tmp_path.glob(f".{secret.name}.*.tmp")) == []


def test_desktop_data_directories_reject_files_and_links() -> None:
    root = _case_directory("directory-boundary")
    try:
        ordinary_file = root / "file"
        ordinary_file.write_bytes(b"not a directory")
        with pytest.raises(RuntimeError, match="not a regular directory"):
            backend_main._ensure_private_directory(ordinary_file)

        target = root / "target"
        target.mkdir()
        linked = root / "linked"
        try:
            linked.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("The test account cannot create a directory symlink")
        try:
            with pytest.raises(RuntimeError, match="not a regular directory"):
                backend_main._ensure_private_directory(linked)
        finally:
            linked.unlink(missing_ok=True)
    finally:
        shutil.rmtree(root)


@pytest.mark.skipif(os.name == "nt", reason="POSIX ownership and mode contract")
def test_desktop_data_directory_is_repaired_to_private_owner_mode(tmp_path: Path) -> None:
    directory = tmp_path / "private"
    directory.mkdir(mode=0o777)
    directory.chmod(0o777)

    backend_main._ensure_private_directory(directory)

    metadata = directory.stat()
    assert metadata.st_uid == os.geteuid()
    assert stat.S_IMODE(metadata.st_mode) == 0o700


@pytest.mark.skipif(os.name == "nt", reason="POSIX no-follow descriptor contract")
def test_private_directory_chmod_never_follows_a_raced_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "private"
    directory.mkdir()
    target = tmp_path / "target"
    target.mkdir(mode=0o755)
    target.chmod(0o755)
    real_open = os.open

    def race_open(candidate: object, flags: int, *args: object, **kwargs: object) -> int:
        if Path(candidate) == directory:
            directory.rmdir()
            directory.symlink_to(target, target_is_directory=True)
        return real_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(backend_main.os, "open", race_open)
    with pytest.raises(OSError):
        backend_main._ensure_private_directory(directory)
    assert stat.S_IMODE(target.stat().st_mode) == 0o755


@pytest.mark.skipif(os.name == "nt", reason="POSIX no-follow descriptor contract")
def test_secret_permission_repair_never_follows_a_raced_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = tmp_path / ".installation-secret"
    secret.write_text("x" * 64, encoding="utf-8")
    target = tmp_path / "target"
    target.write_text("keep", encoding="utf-8")
    target.chmod(0o644)
    real_open = os.open

    def race_open(candidate: object, flags: int, *args: object, **kwargs: object) -> int:
        if Path(candidate) == secret:
            secret.unlink()
            secret.symlink_to(target)
        return real_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(backend_main.os, "open", race_open)
    with pytest.raises(OSError):
        backend_main._read_installation_secret(secret)
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_migration_failure_restores_consistent_backup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = _case_directory("rollback")
    database_path = data_dir / "vault" / "careeros.db"
    database_path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("CREATE TABLE career_fact (value TEXT NOT NULL)")
        connection.execute("INSERT INTO career_fact VALUES ('preserve-me')")
        connection.commit()

    monkeypatch.setattr(
        backend_main,
        "database_revision_state",
        lambda *_: ({"f8a9b0c1d2e3"}, {"a9b0c1d2e3f4"}),
    )

    def corrupt_then_fail(*_args, **_kwargs) -> None:
        with closing(sqlite3.connect(database_path)) as connection:
            connection.execute("DELETE FROM career_fact")
            connection.commit()
        raise RuntimeError("simulated interrupted migration")

    monkeypatch.setattr(backend_main, "run_alembic_upgrade", corrupt_then_fail)
    try:
        with pytest.raises(backend_main.DesktopMigrationError, match="restored"):
            backend_main.migrate_database(database_path, data_dir / "backups")

        with closing(sqlite3.connect(database_path)) as connection:
            assert connection.execute("SELECT value FROM career_fact").fetchone() == (
                "preserve-me",
            )
        assert list((data_dir / "backups").glob("careeros-*.db"))
    finally:
        shutil.rmtree(data_dir)


def test_backup_captures_committed_wal_frames(tmp_path: Path) -> None:
    database = tmp_path / "vault" / "careeros.db"
    database.parent.mkdir()
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute("CREATE TABLE facts (value TEXT NOT NULL)")
        connection.execute("INSERT INTO facts VALUES ('committed-in-wal')")
        connection.commit()

        backup = backend_main._backup_database(database, tmp_path / "backups")

    with closing(sqlite3.connect(backup)) as restored:
        assert restored.execute("SELECT value FROM facts").fetchone() == ("committed-in-wal",)
        assert restored.execute("PRAGMA quick_check").fetchone() == ("ok",)


def test_restore_rejects_a_corrupt_backup_before_replacing_the_vault(tmp_path: Path) -> None:
    database = tmp_path / "careeros.db"
    backup = tmp_path / "corrupt-backup.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE facts (value TEXT NOT NULL)")
        connection.execute("INSERT INTO facts VALUES ('still-here')")
        connection.commit()
    backup.write_bytes(b"not a sqlite database")

    with pytest.raises(sqlite3.DatabaseError):
        backend_main._restore_database(database, backup)

    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT value FROM facts").fetchone() == ("still-here",)
    assert list(tmp_path.glob(".careeros.db.restore-*.tmp")) == []


def test_sqlite_cleanup_removes_every_journal_mode_sidecar(tmp_path: Path) -> None:
    database = tmp_path / "careeros.db"
    for suffix in ("-journal", "-wal", "-shm"):
        Path(f"{database}{suffix}").write_bytes(b"stale")

    backend_main._remove_sqlite_sidecars(database)

    assert all(not Path(f"{database}{suffix}").exists() for suffix in ("-journal", "-wal", "-shm"))


def test_failed_new_vault_migration_removes_main_database_and_all_sidecars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "vault" / "careeros.db"
    database.parent.mkdir()
    ensure_sqlite_database_parent(f"sqlite:///{database.as_posix()}")

    def fail_with_partial_files(_database_path: Path) -> None:
        database.write_bytes(b"partial")
        for suffix in ("-journal", "-wal", "-shm"):
            Path(f"{database}{suffix}").write_bytes(b"partial")
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(backend_main, "run_alembic_upgrade", fail_with_partial_files)
    with pytest.raises(backend_main.DesktopMigrationError, match="before the vault"):
        backend_main.migrate_database(database, tmp_path / "backups")

    assert not database.exists()
    assert all(not Path(f"{database}{suffix}").exists() for suffix in ("-journal", "-wal", "-shm"))


def test_populated_unversioned_vault_is_refused_without_mutation_or_backup(
    tmp_path: Path,
) -> None:
    database = tmp_path / "vault" / "careeros.db"
    database.parent.mkdir()
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE private_facts (value TEXT NOT NULL)")
        connection.execute("INSERT INTO private_facts VALUES ('preserve')")
        connection.commit()

    with pytest.raises(backend_main.DesktopMigrationError, match="no Alembic revision"):
        backend_main.migrate_database(database, tmp_path / "backups")

    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT value FROM private_facts").fetchone() == ("preserve",)
    assert not (tmp_path / "backups").exists()


def test_desktop_migration_rejects_an_outside_vault_before_creating_its_parent(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "private-data"
    database = tmp_path / "outside" / "nested" / "careeros.db"

    with pytest.raises(ValueError, match="configured data root"):
        backend_main.migrate_database(database, data_root / "backups")

    assert not data_root.exists()
    assert not (tmp_path / "outside").exists()


def test_unknown_vault_revision_is_refused_without_attempting_a_downgrade(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "vault" / "careeros.db"
    database.parent.mkdir()
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('future_release_revision')")
        connection.commit()
    upgrade_called = False

    def unexpected_upgrade(_database_path: Path) -> None:
        nonlocal upgrade_called
        upgrade_called = True

    monkeypatch.setattr(backend_main, "run_alembic_upgrade", unexpected_upgrade)
    with pytest.raises(backend_main.DesktopMigrationError, match="automatic downgrade is refused"):
        backend_main.migrate_database(database, tmp_path / "backups")

    assert upgrade_called is False
    assert not (tmp_path / "backups").exists()


def test_desktop_migration_supports_configparser_punctuation_in_path(tmp_path: Path) -> None:
    database = tmp_path / "vault%23" / "careeros.db"
    database.parent.mkdir()

    backup = backend_main.migrate_database(database, tmp_path / "backups")

    assert backup is None
    current, expected = backend_main.database_revision_state(database, read_only=True)
    assert current == expected


def test_recovery_journal_failure_refuses_schema_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from alembic import command

    database = tmp_path / "vault" / "careeros.db"
    database.parent.mkdir()
    command.upgrade(backend_main._alembic_config(database), "f8a9b0c1d2e3")
    revision_before, expected = backend_main.database_revision_state(database, read_only=True)
    assert revision_before != expected
    upgrade_called = False

    def fail_journal(_database_path: Path, _backup_path: Path | None) -> Path:
        raise OSError("simulated durable journal failure")

    def unexpected_upgrade(_database_path: Path) -> None:
        nonlocal upgrade_called
        upgrade_called = True

    monkeypatch.setattr(backend_main, "_write_migration_recovery_marker", fail_journal)
    monkeypatch.setattr(backend_main, "run_alembic_upgrade", unexpected_upgrade)
    with pytest.raises(backend_main.DesktopMigrationError, match="journal.*untouched"):
        backend_main.migrate_database(database, tmp_path / "backups")

    revision_after, _ = backend_main.database_revision_state(database, read_only=True)
    assert revision_after == revision_before
    assert upgrade_called is False
    assert list((tmp_path / "backups").glob("careeros-*.db"))


def test_existing_vault_recovers_a_hard_crash_before_retrying_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from alembic import command

    database = tmp_path / "vault" / "careeros.db"
    database.parent.mkdir()
    command.upgrade(backend_main._alembic_config(database), "f8a9b0c1d2e3")
    real_upgrade = backend_main.run_alembic_upgrade

    def crash_after_nontransactional_ddl(_database_path: Path) -> None:
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("CREATE TABLE crash_partial_schema (value TEXT)")
            connection.commit()
        raise KeyboardInterrupt("simulated process termination")

    monkeypatch.setattr(
        backend_main,
        "run_alembic_upgrade",
        crash_after_nontransactional_ddl,
    )
    with pytest.raises(KeyboardInterrupt):
        backend_main.migrate_database(database, tmp_path / "backups")
    marker = backend_main._migration_recovery_path(database)
    assert marker.is_file()
    assert list((tmp_path / "backups").glob("careeros-*.db"))

    monkeypatch.setattr(backend_main, "run_alembic_upgrade", real_upgrade)
    backend_main.migrate_database(database, tmp_path / "backups")

    assert not marker.exists()
    current, expected = backend_main.database_revision_state(database, read_only=True)
    assert current == expected
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='crash_partial_schema'"
            ).fetchone()
            is None
        )


def test_new_vault_recovers_a_hard_crash_without_accepting_partial_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "vault" / "careeros.db"
    database.parent.mkdir()
    ensure_sqlite_database_parent(f"sqlite:///{database.as_posix()}")
    real_upgrade = backend_main.run_alembic_upgrade

    def crash_during_initialization(_database_path: Path) -> None:
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("CREATE TABLE partial_initialization (value TEXT)")
            connection.commit()
        raise KeyboardInterrupt("simulated process termination")

    monkeypatch.setattr(backend_main, "run_alembic_upgrade", crash_during_initialization)
    with pytest.raises(KeyboardInterrupt):
        backend_main.migrate_database(database, tmp_path / "backups")
    marker = backend_main._migration_recovery_path(database)
    assert marker.is_file()

    monkeypatch.setattr(backend_main, "run_alembic_upgrade", real_upgrade)
    backend_main.migrate_database(database, tmp_path / "backups")

    assert not marker.exists()
    current, expected = backend_main.database_revision_state(database, read_only=True)
    assert current == expected
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='partial_initialization'"
            ).fetchone()
            is None
        )


@pytest.mark.skipif(os.name == "nt", reason="POSIX owner and mode contract")
def test_new_vault_recovery_recreates_a_private_database_under_public_umask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "vault" / "careeros.db"
    database.parent.mkdir(mode=0o755)
    previous_umask = os.umask(0o022)
    real_upgrade = backend_main.run_alembic_upgrade

    def crash_during_initialization(_database_path: Path) -> None:
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("CREATE TABLE partial_initialization (value TEXT)")
            connection.commit()
        raise KeyboardInterrupt("simulated process termination")

    try:
        ensure_sqlite_database_parent(f"sqlite:///{database.as_posix()}")
        assert stat.S_IMODE(database.stat().st_mode) == 0o600
        monkeypatch.setattr(backend_main, "run_alembic_upgrade", crash_during_initialization)
        with pytest.raises(KeyboardInterrupt):
            backend_main.migrate_database(database, tmp_path / "backups")

        monkeypatch.setattr(backend_main, "run_alembic_upgrade", real_upgrade)
        backend_main.migrate_database(database, tmp_path / "backups")
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    assert not backend_main._migration_recovery_path(database).exists()


def test_invalid_recovery_marker_fails_closed_without_touching_the_vault(
    tmp_path: Path,
) -> None:
    database = tmp_path / "vault" / "careeros.db"
    database.parent.mkdir()
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE facts (value TEXT)")
        connection.execute("INSERT INTO facts VALUES ('preserve')")
        connection.commit()
    marker = backend_main._migration_recovery_path(database)
    marker.write_text('{"mode":"new"}', encoding="utf-8")

    with pytest.raises(backend_main.DesktopMigrationError, match="left untouched"):
        backend_main.migrate_database(database, tmp_path / "backups")

    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT value FROM facts").fetchone() == ("preserve",)
    assert marker.is_file()


def _write_private_recovery_marker(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    if os.name != "nt":
        path.chmod(0o600)


def test_recovery_marker_rejects_oversize_and_hardlink_aliases_without_mutation(
    tmp_path: Path,
) -> None:
    marker = tmp_path / ".careeros.db.migration-recovery.json"
    _write_private_recovery_marker(
        marker,
        b"x" * (backend_main.MIGRATION_RECOVERY_MAX_BYTES + 1),
    )
    with pytest.raises(RuntimeError, match="private bounded"):
        backend_main._read_migration_recovery_marker(marker)

    marker.unlink()
    target = tmp_path / "unrelated-private-file"
    payload = b'{"mode":"new","schema_version":1}'
    _write_private_recovery_marker(target, payload)
    os.link(target, marker)

    with pytest.raises(RuntimeError, match="private bounded"):
        backend_main._read_migration_recovery_marker(marker)

    assert target.read_bytes() == payload
    assert marker.read_bytes() == payload


@pytest.mark.skipif(os.name == "nt", reason="POSIX owner and mode contract")
def test_recovery_marker_requires_private_posix_permissions(tmp_path: Path) -> None:
    marker = tmp_path / ".careeros.db.migration-recovery.json"
    marker.write_bytes(b'{"mode":"new","schema_version":1}')
    marker.chmod(0o644)

    with pytest.raises(RuntimeError, match="private bounded"):
        backend_main._read_migration_recovery_marker(marker)

    assert stat.S_IMODE(marker.stat().st_mode) == 0o644


def test_recovery_marker_never_follows_a_raced_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.storage import atomic

    marker = tmp_path / ".careeros.db.migration-recovery.json"
    target = tmp_path / "unrelated-private-file"
    payload = b'{"mode":"new","schema_version":1}'
    _write_private_recovery_marker(marker, payload)
    _write_private_recovery_marker(target, b"preserve")
    real_open = os.open
    raced = False

    def race_open(candidate: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal raced
        if Path(candidate) == marker and not raced:
            raced = True
            marker.unlink()
            marker.symlink_to(target)
        return real_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(atomic.os, "open", race_open)
    with pytest.raises((OSError, RuntimeError, ValueError)):
        backend_main._read_migration_recovery_marker(marker)

    assert target.read_bytes() == b"preserve"


def test_recovery_marker_rejects_post_read_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.storage import atomic

    marker = tmp_path / ".careeros.db.migration-recovery.json"
    payload = b'{"mode":"new","schema_version":1}'
    _write_private_recovery_marker(marker, payload)
    real_read = atomic.read_stable_bounded_file

    def mutate_after_read(*args, **kwargs) -> bytes:
        encoded = real_read(*args, **kwargs)
        marker.write_bytes(b'{"mode":"new","schema_version":2} ')
        if os.name != "nt":
            marker.chmod(0o600)
        return encoded

    monkeypatch.setattr(atomic, "read_stable_bounded_file", mutate_after_read)
    with pytest.raises(RuntimeError, match="changed while it was read"):
        backend_main._read_migration_recovery_marker(marker)


def test_migration_backup_hash_rejects_hardlink_alias_without_mutating_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "unrelated-private-file"
    backup = tmp_path / "careeros-20260801T000000000000Z-aaaaaaaa.db"
    payload = b"preserve"
    _write_private_recovery_marker(target, payload)
    os.link(target, backup)

    with pytest.raises(RuntimeError, match="private ordinary file"):
        backend_main._sha256_file(backup)

    assert target.read_bytes() == payload
    assert backup.read_bytes() == payload


def test_migration_backup_hash_never_follows_a_raced_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup = tmp_path / "careeros-20260801T000000000000Z-aaaaaaaa.db"
    target = tmp_path / "unrelated-private-file"
    _write_private_recovery_marker(backup, b"backup")
    _write_private_recovery_marker(target, b"preserve")
    real_open = os.open
    raced = False

    def race_open(candidate: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal raced
        if Path(candidate) == backup and not raced:
            raced = True
            backup.unlink()
            backup.symlink_to(target)
        return real_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(backend_main.os, "open", race_open)
    with pytest.raises((OSError, RuntimeError)):
        backend_main._sha256_file(backup)

    assert target.read_bytes() == b"preserve"


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
        shutil.rmtree(data_dir)


def test_parent_liveness_probe_recognizes_the_test_process() -> None:
    assert backend_main.parent_process_is_alive(os.getpid()) is True
    assert backend_main.parent_process_is_alive(0) is False


def test_windows_parent_probe_uses_pointer_sized_handle_signatures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ctypes
    from ctypes import wintypes
    from types import SimpleNamespace

    class FakeFunction:
        def __init__(self, result: object) -> None:
            self.result = result
            self.calls: list[tuple[object, ...]] = []
            self.argtypes = None
            self.restype = None

        def __call__(self, *arguments: object) -> object:
            self.calls.append(arguments)
            return self.result

    large_handle = 0x1_0000_0001
    open_process = FakeFunction(large_handle)
    wait_for_single_object = FakeFunction(0x00000102)
    close_handle = FakeFunction(1)
    kernel32 = SimpleNamespace(
        OpenProcess=open_process,
        WaitForSingleObject=wait_for_single_object,
        CloseHandle=close_handle,
    )
    monkeypatch.setattr(backend_main.os, "name", "nt")
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(kernel32=kernel32), raising=False)

    assert backend_main.parent_process_is_alive(4242) is True
    assert open_process.argtypes == [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    assert open_process.restype is wintypes.HANDLE
    assert wait_for_single_object.argtypes == [wintypes.HANDLE, wintypes.DWORD]
    assert wait_for_single_object.restype is wintypes.DWORD
    assert close_handle.argtypes == [wintypes.HANDLE]
    assert close_handle.restype is wintypes.BOOL
    assert open_process.calls == [(0x00100000, False, 4242)]
    assert wait_for_single_object.calls == [(large_handle, 0)]
    assert close_handle.calls == [(large_handle,)]


def test_parent_watchdog_requests_graceful_shutdown_before_hard_exit() -> None:
    requested = threading.Event()
    completed = threading.Event()
    forced: list[int] = []

    def request_shutdown() -> None:
        requested.set()
        completed.set()

    watcher = backend_main.start_parent_watchdog(
        4242,
        request_shutdown=request_shutdown,
        shutdown_complete=completed,
        interval_seconds=0.001,
        hard_timeout_seconds=0.05,
        parent_probe=lambda _process_id: False,
        force_exit=forced.append,
    )
    watcher.join(timeout=1)

    assert not watcher.is_alive()
    assert requested.is_set()
    assert forced == []


def test_parent_watchdog_forces_exit_only_after_graceful_timeout() -> None:
    requested = threading.Event()
    completed = threading.Event()
    forced: list[int] = []

    watcher = backend_main.start_parent_watchdog(
        4242,
        request_shutdown=requested.set,
        shutdown_complete=completed,
        interval_seconds=0.001,
        hard_timeout_seconds=0.01,
        parent_probe=lambda _process_id: False,
        force_exit=forced.append,
    )
    watcher.join(timeout=1)

    assert not watcher.is_alive()
    assert requested.is_set()
    assert forced == [1]


def test_parent_watchdog_fails_closed_when_shutdown_request_raises() -> None:
    forced: list[int] = []

    def fail_shutdown() -> None:
        raise RuntimeError("simulated controller failure")

    watcher = backend_main.start_parent_watchdog(
        4242,
        request_shutdown=fail_shutdown,
        shutdown_complete=threading.Event(),
        interval_seconds=0.001,
        hard_timeout_seconds=0.05,
        parent_probe=lambda _process_id: False,
        force_exit=forced.append,
    )
    watcher.join(timeout=1)

    assert not watcher.is_alive()
    assert forced == [1]


def test_desktop_instance_lease_blocks_a_second_process() -> None:
    from backend.desktop.lifecycle import desktop_instance_lease

    data_dir = _case_directory("instance-lease")
    context = get_context("spawn")
    result_queue = context.Queue()
    try:
        with desktop_instance_lease(root=data_dir):
            contender = context.Process(
                target=_try_instance_lease,
                args=(str(data_dir), result_queue),
            )
            contender.start()
            contender.join(timeout=15)
            assert contender.exitcode == 0
            assert result_queue.get(timeout=2) == "blocked"

        successor = context.Process(
            target=_try_instance_lease,
            args=(str(data_dir), result_queue),
        )
        successor.start()
        successor.join(timeout=15)
        assert successor.exitcode == 0
        assert result_queue.get(timeout=2) == "acquired"
    finally:
        result_queue.close()
        shutil.rmtree(data_dir)
