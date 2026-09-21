"""Tests for campaign_document asset publication journal and recovery semantics."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.career.asset_publication import (
    _expected_storage_path,
    begin_asset_publication_write,
    write_asset_publication_journal,
)
from backend.career.models import CandidateProfile, CareerAsset
from backend.db.base import Base, configure_sqlite_connection, ensure_sqlite_parent
from backend.models import User
from backend.storage.atomic import atomic_write, resolve_data_path


@pytest.fixture
def asset_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_directory = tmp_path / "private-data"
    monkeypatch.setattr("backend.storage.atomic.settings.DATA_DIR", str(data_directory))
    db_path = (tmp_path / "test_asset.db").as_posix()
    db_url = f"sqlite:///{db_path}"
    ensure_sqlite_parent(db_url)
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", configure_sqlite_connection)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        user = User(username="asset-user", hashed_password="pw")
        session.add(user)
        session.flush()
        profile = CandidateProfile(user_id=user.id, display_name="Asset Profile")
        session.add(profile)
        session.commit()
        profile_id = profile.id

    try:
        yield engine, factory, data_directory, profile_id
    finally:
        engine.dispose()


def test_expected_storage_path_all_kinds():
    sha = "e" * 64
    assert _expected_storage_path("campaign_document", sha) == f"assets/campaign/{sha[:2]}/{sha}"
    assert _expected_storage_path("source_document", sha) == f"assets/{sha[:2]}/{sha}"
    assert _expected_storage_path("profile_photo", sha) == f"assets/photos/{sha[:2]}/{sha}.jpg"

    with pytest.raises(ValueError, match="Invalid asset publication kind"):
        _expected_storage_path("unsupported_kind", sha)


@pytest.mark.parametrize(
    ("kind", "filename_suffix"),
    [
        ("campaign_document", ""),
        ("source_document", ""),
        ("profile_photo", ".jpg"),
    ],
)
def test_asset_publication_recovery_committed(asset_vault, kind: str, filename_suffix: str):
    _, factory, data_directory, profile_id = asset_vault
    data = f"Committed payload for {kind}".encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    byte_size = len(data)
    storage_path = _expected_storage_path(kind, sha)
    op_id = "11111111-1111-4111-8111-111111111111"

    # 1. Write journal and bytes
    write_asset_publication_journal(
        operation_id=op_id,
        profile_id=profile_id,
        kind=kind,
        storage_path=storage_path,
        sha256=sha,
        byte_size=byte_size,
    )
    atomic_write(storage_path, data)

    # 2. Add CareerAsset row to DB (committed)
    with factory() as session:
        asset = CareerAsset(
            profile_id=profile_id,
            kind=kind,
            original_name=f"test{filename_suffix}",
            media_type="application/octet-stream",
            sha256=sha,
            byte_size=byte_size,
            storage_path=storage_path,
        )
        session.add(asset)
        session.commit()

    # 3. Reconcile crash recovery
    with factory() as session:
        count = begin_asset_publication_write(session)
        assert count == 1
        session.rollback()

    # 4. Verified: file is preserved and journal file is unlinked
    abs_path = resolve_data_path(storage_path, create_root=False)
    assert abs_path.exists()
    assert abs_path.read_bytes() == data

    journal_dir = data_directory / "assets" / ".publication-journal"
    assert not (journal_dir / f"{op_id}.json").exists()


@pytest.mark.parametrize(
    ("kind", "filename_suffix"),
    [
        ("campaign_document", ""),
        ("source_document", ""),
        ("profile_photo", ".jpg"),
    ],
)
def test_asset_publication_recovery_uncommitted(asset_vault, kind: str, filename_suffix: str):
    _, factory, data_directory, profile_id = asset_vault
    data = f"Uncommitted payload for {kind}".encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    byte_size = len(data)
    storage_path = _expected_storage_path(kind, sha)
    op_id = "22222222-2222-4222-8222-222222222222"

    # 1. Write journal and bytes, but do NOT commit to DB
    write_asset_publication_journal(
        operation_id=op_id,
        profile_id=profile_id,
        kind=kind,
        storage_path=storage_path,
        sha256=sha,
        byte_size=byte_size,
    )
    atomic_write(storage_path, data)

    abs_path = resolve_data_path(storage_path, create_root=False)
    assert abs_path.exists()

    # 2. Reconcile crash recovery without DB commit
    with factory() as session:
        count = begin_asset_publication_write(session)
        assert count == 1
        session.rollback()

    # 3. Verified: uncommitted file is removed and journal is unlinked
    assert not abs_path.exists()
    journal_dir = data_directory / "assets" / ".publication-journal"
    assert not (journal_dir / f"{op_id}.json").exists()
