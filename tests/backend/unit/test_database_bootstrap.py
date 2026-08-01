import os
import stat
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from backend.db import sqlite as sqlite_runtime
from backend.db.base import ensure_sqlite_parent
from backend.db.sqlite import SQLiteConfigurationError


def test_file_backed_sqlite_bootstrap_creates_missing_parent() -> None:
    with TemporaryDirectory(prefix="careeros-db-bootstrap-") as directory:
        database = Path(directory) / "nested" / "vault" / "careeros.db"

        ensure_sqlite_parent(f"sqlite:///{database.as_posix()}")

        assert database.parent.is_dir()


def test_in_memory_sqlite_bootstrap_does_not_create_a_directory() -> None:
    with patch("backend.db.sqlite.Path.mkdir") as mkdir:
        ensure_sqlite_parent("sqlite:///:memory:")

    mkdir.assert_not_called()


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://localhost/careeros",
        "sqlite:///file:careeros.db?mode=rw&uri=true",
        "sqlite://",
    ],
)
def test_database_bootstrap_rejects_nonlocal_or_ambiguous_urls(database_url: str) -> None:
    with pytest.raises(SQLiteConfigurationError):
        ensure_sqlite_parent(database_url)


def test_database_bootstrap_rejects_a_hard_link_alias(tmp_path: Path) -> None:
    database = tmp_path / "careeros.db"
    alias = tmp_path / "careeros-alias.db"
    database.touch()
    try:
        os.link(database, alias)
    except OSError:
        pytest.skip("The test filesystem does not support hard links")

    with pytest.raises(SQLiteConfigurationError, match="hard-link"):
        ensure_sqlite_parent(f"sqlite:///{database.as_posix()}")


def test_database_bootstrap_rejects_a_symbolic_link_alias(tmp_path: Path) -> None:
    database = tmp_path / "careeros.db"
    target = tmp_path / "target.db"
    target.touch()
    try:
        database.symlink_to(target)
    except OSError:
        pytest.skip("The test account cannot create a file symlink")

    with pytest.raises(SQLiteConfigurationError, match="non-linked"):
        ensure_sqlite_parent(f"sqlite:///{database.as_posix()}")


def test_data_root_containment_is_checked_before_creating_an_outside_parent(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "private-data"
    outside_parent = tmp_path / "outside" / "nested"
    database = outside_parent / "careeros.db"

    with pytest.raises(SQLiteConfigurationError, match="configured data root"):
        sqlite_runtime.ensure_sqlite_database_parent(
            f"sqlite:///{database.as_posix()}",
            data_root=data_root,
        )

    assert not data_root.exists()
    assert not (tmp_path / "outside").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX owner and mode contract")
def test_source_bootstrap_repairs_private_parent_and_existing_vault_files(
    tmp_path: Path,
) -> None:
    database_parent = tmp_path / "source-data"
    database = database_parent / "careeros.db"
    previous_umask = os.umask(0o022)
    try:
        database_parent.mkdir(mode=0o777)
        database.touch(mode=0o666)
        sidecars = [Path(f"{database}{suffix}") for suffix in ("-journal", "-wal", "-shm")]
        for sidecar in sidecars:
            sidecar.touch(mode=0o666)

        assert stat.S_IMODE(database_parent.stat().st_mode) == 0o755
        assert stat.S_IMODE(database.stat().st_mode) == 0o644

        ensure_sqlite_parent(f"sqlite:///{database.as_posix()}")
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(database_parent.stat().st_mode) == 0o700
    for candidate in (database, *sidecars):
        assert stat.S_IMODE(candidate.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX owner and mode contract")
def test_source_bootstrap_hardens_only_the_data_root_to_nested_vault_chain(
    tmp_path: Path,
) -> None:
    deployment_root = tmp_path / "deployment"
    data_root = deployment_root / "unsafe-data"
    database = data_root / "nested" / "vault" / "careeros.db"
    deployment_root.mkdir(mode=0o755)
    deployment_root.chmod(0o755)
    data_root.mkdir(mode=0o777)
    data_root.chmod(0o777)

    sqlite_runtime.ensure_sqlite_database_parent(
        f"sqlite:///{database.as_posix()}",
        data_root=data_root,
    )

    assert stat.S_IMODE(deployment_root.stat().st_mode) == 0o755
    assert stat.S_IMODE(data_root.stat().st_mode) == 0o700
    assert stat.S_IMODE((data_root / "nested").stat().st_mode) == 0o700
    assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX no-follow descriptor contract")
def test_parent_permission_repair_never_follows_a_raced_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_parent = tmp_path / "vault"
    database_parent.mkdir()
    database = database_parent / "careeros.db"
    target = tmp_path / "target"
    target.mkdir(mode=0o755)
    target.chmod(0o755)
    real_open = os.open
    raced = False

    def race_open(candidate: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal raced
        if Path(candidate) == database_parent and not raced:
            raced = True
            database_parent.rmdir()
            database_parent.symlink_to(target, target_is_directory=True)
        return real_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(sqlite_runtime.os, "open", race_open)

    with pytest.raises(SQLiteConfigurationError, match="parent changed"):
        ensure_sqlite_parent(f"sqlite:///{database.as_posix()}")

    assert stat.S_IMODE(target.stat().st_mode) == 0o755


@pytest.mark.skipif(os.name == "nt", reason="POSIX no-follow descriptor contract")
def test_vault_permission_repair_never_follows_a_raced_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "careeros.db"
    database.write_bytes(b"vault")
    target = tmp_path / "target.db"
    target.write_bytes(b"preserve")
    target.chmod(0o644)
    real_open = os.open
    raced = False

    def race_open(candidate: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal raced
        if Path(candidate) == database and not raced:
            raced = True
            database.unlink()
            database.symlink_to(target)
        return real_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(sqlite_runtime.os, "open", race_open)

    with pytest.raises(
        SQLiteConfigurationError,
        match="vault (?:changed|must be an ordinary non-linked file)",
    ):
        ensure_sqlite_parent(f"sqlite:///{database.as_posix()}")

    assert target.read_bytes() == b"preserve"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


@pytest.mark.skipif(os.name == "nt", reason="POSIX link ownership contract")
def test_sidecar_hard_link_alias_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "careeros.db"
    database.touch()
    wal = Path(f"{database}-wal")
    alias = tmp_path / "wal-alias"
    wal.touch()
    os.link(wal, alias)

    with pytest.raises(SQLiteConfigurationError, match="wal sidecar.*unaliased"):
        ensure_sqlite_parent(f"sqlite:///{database.as_posix()}")


@pytest.mark.skipif(os.name == "nt", reason="POSIX no-follow descriptor contract")
def test_sidecar_symlink_target_is_not_repermissioned(tmp_path: Path) -> None:
    database = tmp_path / "careeros.db"
    database.touch()
    target = tmp_path / "outside-wal"
    target.write_bytes(b"preserve")
    target.chmod(0o644)
    Path(f"{database}-wal").symlink_to(target)

    with pytest.raises(SQLiteConfigurationError, match="wal sidecar.*unaliased"):
        ensure_sqlite_parent(f"sqlite:///{database.as_posix()}")

    assert target.read_bytes() == b"preserve"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
