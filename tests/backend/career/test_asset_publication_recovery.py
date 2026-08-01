from __future__ import annotations

import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest
from PIL import Image
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import backend.career.asset_publication as publication_module
import backend.career.sources as sources_module
from backend.career.asset_publication import (
    begin_asset_publication_write,
    write_asset_publication_journal,
)
from backend.career.deletion import begin_vault_maintenance, delete_complete_vault
from backend.career.models import CandidateProfile, CareerAsset, SourceDocument
from backend.career.source_parsing import PreparedSourceDocument, prepare_source_document
from backend.db.base import Base, configure_sqlite_connection, ensure_sqlite_parent
from backend.models import User
from backend.models.user import VAULT_STATE_RESET_PENDING
from backend.resumes.photos import persist_normalized_profile_photo
from backend.services.auth import ACCESS_PURPOSE_SESSION
from backend.services.auth_sessions import issue_auth_session
from backend.storage.atomic import StorageWriteError, atomic_write


@dataclass(frozen=True)
class AssetVault:
    engine: object
    factory: sessionmaker
    data_directory: Path
    user_ids: tuple[int, int]
    profile_ids: tuple[str, str]


@pytest.fixture
def asset_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_directory = tmp_path / "private-data"
    monkeypatch.setattr("backend.storage.atomic.settings.DATA_DIR", str(data_directory))
    database_path = (tmp_path / "asset-publication.db").as_posix()
    ensure_sqlite_parent(f"sqlite:///{database_path}")
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", configure_sqlite_connection)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as setup:
        users = [
            User(username=f"asset-recovery-{index}", hashed_password="not-used")
            for index in range(2)
        ]
        setup.add_all(users)
        setup.flush()
        profiles = [
            CandidateProfile(user_id=user.id, display_name=f"Recovery profile {index}")
            for index, user in enumerate(users)
        ]
        setup.add_all(profiles)
        setup.commit()
        vault = AssetVault(
            engine=engine,
            factory=factory,
            data_directory=data_directory,
            user_ids=(users[0].id, users[1].id),
            profile_ids=(profiles[0].id, profiles[1].id),
        )
    try:
        yield vault
    finally:
        engine.dispose()


def _prepared_source(data: bytes = b"Durable local source evidence.") -> PreparedSourceDocument:
    return prepare_source_document(
        filename="evidence.txt",
        media_type="text/plain",
        data=data,
    )


def _normalized_photo() -> bytes:
    output = BytesIO()
    Image.new("RGB", (720, 720), (25, 50, 75)).save(output, format="JPEG", quality=90)
    return output.getvalue()


def _journal_files(vault: AssetVault) -> list[Path]:
    directory = vault.data_directory / "assets" / ".publication-journal"
    return sorted(directory.glob("*.json")) if directory.exists() else []


def _source_path(vault: AssetVault, prepared: PreparedSourceDocument) -> Path:
    return vault.data_directory / "assets" / prepared.sha256[:2] / prepared.sha256


def _photo_path(vault: AssetVault, normalized: bytes) -> Path:
    digest = hashlib.sha256(normalized).hexdigest()
    return vault.data_directory / "assets" / "photos" / digest[:2] / f"{digest}.jpg"


def _reconcile(vault: AssetVault) -> int:
    with vault.factory() as recovery:
        reconciled = begin_asset_publication_write(recovery)
        recovery.rollback()
        return reconciled


def test_source_commit_acknowledgement_error_returns_committed_asset(asset_vault: AssetVault):
    prepared = _prepared_source()
    with asset_vault.factory() as session:
        real_commit = session.commit

        def commit_then_raise() -> None:
            real_commit()
            raise RuntimeError("synthetic lost source commit acknowledgement")

        with patch.object(session, "commit", side_effect=commit_then_raise):
            response = sources_module.persist_prepared_source_document(
                session,
                user_id=asset_vault.user_ids[0],
                prepared=prepared,
            )

    with asset_vault.factory() as verification:
        assert verification.query(SourceDocument).count() == 1
        assert verification.query(CareerAsset).count() == 1
        assert verification.get(SourceDocument, response.id) is not None
    assert _source_path(asset_vault, prepared).read_bytes() == prepared.data
    assert _journal_files(asset_vault) == []


def test_photo_commit_acknowledgement_error_returns_committed_asset(asset_vault: AssetVault):
    normalized = _normalized_photo()
    with asset_vault.factory() as session:
        real_commit = session.commit

        def commit_then_raise() -> None:
            real_commit()
            raise RuntimeError("synthetic lost photo commit acknowledgement")

        with patch.object(session, "commit", side_effect=commit_then_raise):
            response = persist_normalized_profile_photo(
                session,
                user_id=asset_vault.user_ids[0],
                filename="portrait.jpg",
                normalized=normalized,
                width=720,
                height=720,
            )

    with asset_vault.factory() as verification:
        asset = verification.get(CareerAsset, response.id)
        profile = verification.get(CandidateProfile, asset_vault.profile_ids[0])
        assert asset is not None
        assert profile is not None and profile.photo_asset_id == asset.id
    assert _photo_path(asset_vault, normalized).read_bytes() == normalized
    assert _journal_files(asset_vault) == []


def test_source_commit_ack_cannot_unlink_a_concurrent_cross_profile_reference(
    asset_vault: AssetVault,
) -> None:
    prepared = _prepared_source(b"One source path shared across profiles.")
    first_commit_published = Event()
    second_commit_finished = Event()

    def publish_first() -> str:
        with asset_vault.factory() as session:
            real_commit = session.commit

            def commit_then_wait_and_raise() -> None:
                real_commit()
                first_commit_published.set()
                if not second_commit_finished.wait(timeout=5):
                    raise AssertionError("second profile did not bind the shared source")
                raise RuntimeError("synthetic delayed source commit acknowledgement")

            with patch.object(session, "commit", side_effect=commit_then_wait_and_raise):
                return sources_module.persist_prepared_source_document(
                    session,
                    user_id=asset_vault.user_ids[0],
                    prepared=prepared,
                ).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(publish_first)
        assert first_commit_published.wait(timeout=5)
        try:
            with asset_vault.factory() as second_session:
                second_id = sources_module.persist_prepared_source_document(
                    second_session,
                    user_id=asset_vault.user_ids[1],
                    prepared=prepared,
                ).id
        finally:
            second_commit_finished.set()
        first_id = first.result(timeout=5)

    with asset_vault.factory() as verification:
        assets = verification.query(CareerAsset).all()
        assert verification.query(SourceDocument).count() == 2
        assert {asset.profile_id for asset in assets} == set(asset_vault.profile_ids)
        assert len({asset.storage_path for asset in assets}) == 1
    assert first_id != second_id
    assert _source_path(asset_vault, prepared).read_bytes() == prepared.data
    assert _journal_files(asset_vault) == []


def test_photo_commit_ack_cannot_unlink_a_concurrent_cross_profile_reference(
    asset_vault: AssetVault,
) -> None:
    normalized = _normalized_photo()
    first_commit_published = Event()
    second_commit_finished = Event()

    def publish_first() -> str:
        with asset_vault.factory() as session:
            real_commit = session.commit

            def commit_then_wait_and_raise() -> None:
                real_commit()
                first_commit_published.set()
                if not second_commit_finished.wait(timeout=5):
                    raise AssertionError("second profile did not bind the shared photo")
                raise RuntimeError("synthetic delayed photo commit acknowledgement")

            with patch.object(session, "commit", side_effect=commit_then_wait_and_raise):
                return persist_normalized_profile_photo(
                    session,
                    user_id=asset_vault.user_ids[0],
                    filename="portrait-a.jpg",
                    normalized=normalized,
                    width=720,
                    height=720,
                ).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(publish_first)
        assert first_commit_published.wait(timeout=5)
        try:
            with asset_vault.factory() as second_session:
                second_id = persist_normalized_profile_photo(
                    second_session,
                    user_id=asset_vault.user_ids[1],
                    filename="portrait-b.jpg",
                    normalized=normalized,
                    width=720,
                    height=720,
                ).id
        finally:
            second_commit_finished.set()
        first_id = first.result(timeout=5)

    with asset_vault.factory() as verification:
        assets = verification.query(CareerAsset).all()
        assert len(assets) == 2
        assert {asset.profile_id for asset in assets} == set(asset_vault.profile_ids)
        assert len({asset.storage_path for asset in assets}) == 1
    assert first_id != second_id
    assert _photo_path(asset_vault, normalized).read_bytes() == normalized
    assert _journal_files(asset_vault) == []


@pytest.mark.parametrize("asset_kind", ["source", "photo"])
def test_precommit_failure_removes_only_unreferenced_journal_owned_bytes(
    asset_vault: AssetVault,
    asset_kind: str,
) -> None:
    prepared = _prepared_source()
    normalized = _normalized_photo()
    with asset_vault.factory() as session:

        def fail_before_commit() -> None:
            raise RuntimeError("synthetic precommit failure")

        with patch.object(session, "commit", side_effect=fail_before_commit):
            with pytest.raises(RuntimeError, match="precommit"):
                if asset_kind == "source":
                    sources_module.persist_prepared_source_document(
                        session,
                        user_id=asset_vault.user_ids[0],
                        prepared=prepared,
                    )
                else:
                    persist_normalized_profile_photo(
                        session,
                        user_id=asset_vault.user_ids[0],
                        filename="portrait.jpg",
                        normalized=normalized,
                        width=720,
                        height=720,
                    )

    with asset_vault.factory() as verification:
        assert verification.query(CareerAsset).count() == 0
        assert verification.query(SourceDocument).count() == 0
    assert not _source_path(asset_vault, prepared).exists()
    assert not _photo_path(asset_vault, normalized).exists()
    assert _journal_files(asset_vault) == []


def test_hard_crash_after_publish_is_reconciled_without_a_database_row(
    asset_vault: AssetVault,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_source(b"Crash-left source bytes.")
    real_atomic_write = sources_module.atomic_write

    class SimulatedProcessDeath(BaseException):
        pass

    def publish_then_die(relative_path, data):
        real_atomic_write(relative_path, data)
        raise SimulatedProcessDeath

    monkeypatch.setattr(sources_module, "atomic_write", publish_then_die)
    with asset_vault.factory() as interrupted:
        with pytest.raises(SimulatedProcessDeath):
            sources_module.persist_prepared_source_document(
                interrupted,
                user_id=asset_vault.user_ids[0],
                prepared=prepared,
            )

    assert _source_path(asset_vault, prepared).is_file()
    assert len(_journal_files(asset_vault)) == 1
    monkeypatch.setattr(sources_module, "atomic_write", real_atomic_write)

    assert _reconcile(asset_vault) == 1
    with asset_vault.factory() as verification:
        assert verification.query(CareerAsset).count() == 0
        assert verification.query(SourceDocument).count() == 0
    assert not _source_path(asset_vault, prepared).exists()
    assert _journal_files(asset_vault) == []


def test_hard_crash_after_commit_keeps_referenced_bytes_and_clears_journal(
    asset_vault: AssetVault,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_source(b"Committed source bytes survive recovery.")
    real_remove = sources_module.remove_asset_publication_journal

    class SimulatedProcessDeath(BaseException):
        pass

    def die_before_journal_cleanup(_relative_path: str) -> bool:
        raise SimulatedProcessDeath

    monkeypatch.setattr(
        sources_module,
        "remove_asset_publication_journal",
        die_before_journal_cleanup,
    )
    with asset_vault.factory() as interrupted:
        with pytest.raises(SimulatedProcessDeath):
            sources_module.persist_prepared_source_document(
                interrupted,
                user_id=asset_vault.user_ids[0],
                prepared=prepared,
            )

    assert _source_path(asset_vault, prepared).read_bytes() == prepared.data
    assert len(_journal_files(asset_vault)) == 1
    monkeypatch.setattr(sources_module, "remove_asset_publication_journal", real_remove)

    assert _reconcile(asset_vault) == 1
    with asset_vault.factory() as verification:
        assert verification.query(CareerAsset).count() == 1
        assert verification.query(SourceDocument).count() == 1
    assert _source_path(asset_vault, prepared).read_bytes() == prepared.data
    assert _journal_files(asset_vault) == []


def test_malformed_journal_fails_closed_without_unlinking_bytes(asset_vault: AssetVault) -> None:
    journal_directory = asset_vault.data_directory / "assets" / ".publication-journal"
    journal_directory.mkdir(parents=True)
    (journal_directory / "malformed.json").write_text("{}", encoding="utf-8")
    sentinel = asset_vault.data_directory / "assets" / "sentinel.bin"
    sentinel.write_bytes(b"must remain")

    with asset_vault.factory() as recovery:
        with pytest.raises(StorageWriteError, match="recovery metadata is invalid"):
            begin_asset_publication_write(recovery)

    assert sentinel.read_bytes() == b"must remain"
    assert (journal_directory / "malformed.json").is_file()


def test_journal_scan_limit_fails_before_parsing_or_unlinking(
    asset_vault: AssetVault,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal_directory = asset_vault.data_directory / "assets" / ".publication-journal"
    journal_directory.mkdir(parents=True)
    for index in range(3):
        (journal_directory / f"record-{index}.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(publication_module, "_JOURNAL_SCAN_LIMIT", 2)
    sentinel = asset_vault.data_directory / "assets" / "sentinel.bin"
    sentinel.write_bytes(b"must remain")

    with asset_vault.factory() as recovery:
        with pytest.raises(StorageWriteError, match="Too many pending"):
            begin_asset_publication_write(recovery)

    assert sentinel.read_bytes() == b"must remain"
    assert len(list(journal_directory.glob("*.json"))) == 3


def _pending_source_journal(vault: AssetVault) -> Path:
    content = b"pending journal read contract"
    digest = hashlib.sha256(content).hexdigest()
    relative_path = write_asset_publication_journal(
        operation_id=str(uuid.uuid4()),
        profile_id=vault.profile_ids[0],
        kind="source_document",
        storage_path=f"assets/{digest[:2]}/{digest}",
        sha256=digest,
        byte_size=len(content),
    )
    return vault.data_directory / relative_path


def test_oversized_journal_is_rejected_before_json_allocation(asset_vault: AssetVault) -> None:
    journal = _pending_source_journal(asset_vault)
    journal.write_bytes(b"x" * (publication_module._JOURNAL_MAX_BYTES + 1))

    with asset_vault.factory() as recovery:
        with pytest.raises(StorageWriteError, match="recovery metadata is invalid"):
            begin_asset_publication_write(recovery)

    assert journal.stat().st_size == publication_module._JOURNAL_MAX_BYTES + 1


def test_symlink_journal_is_rejected_without_following_its_target(asset_vault: AssetVault) -> None:
    journal = _pending_source_journal(asset_vault)
    payload = journal.read_bytes()
    external = asset_vault.data_directory / "external-journal-target.json"
    external.write_bytes(payload)
    journal.unlink()
    try:
        journal.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"journal symlinks are unavailable: {exc}")

    with asset_vault.factory() as recovery:
        with pytest.raises(StorageWriteError, match="recovery metadata is invalid"):
            begin_asset_publication_write(recovery)

    assert external.read_bytes() == payload
    assert journal.is_symlink()


def test_hard_linked_journal_is_rejected_as_ambiguous(asset_vault: AssetVault) -> None:
    journal = _pending_source_journal(asset_vault)
    alias = asset_vault.data_directory / "journal-hard-link-alias"
    try:
        os.link(journal, alias)
    except OSError as exc:
        pytest.skip(f"journal hard links are unavailable: {exc}")

    with asset_vault.factory() as recovery:
        with pytest.raises(StorageWriteError, match="recovery metadata is invalid"):
            begin_asset_publication_write(recovery)

    assert journal.read_bytes() == alias.read_bytes()
    assert journal.stat().st_nlink >= 2


def test_journal_swap_between_lstat_and_open_is_rejected(
    asset_vault: AssetVault,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = _pending_source_journal(asset_vault)
    replacement = asset_vault.data_directory / "replacement-journal.json"
    replacement.write_bytes(journal.read_bytes())
    real_open = publication_module.os.open
    swapped = False

    def swap_then_open(path, flags):
        nonlocal swapped
        if Path(path) == journal and not swapped:
            swapped = True
            replacement.replace(journal)
        return real_open(path, flags)

    monkeypatch.setattr(publication_module.os, "open", swap_then_open)
    with asset_vault.factory() as recovery:
        with pytest.raises(StorageWriteError, match="recovery metadata is invalid"):
            begin_asset_publication_write(recovery)

    assert swapped is True
    assert journal.is_file()


def test_vault_deletion_reconciles_asset_journals_under_its_writer_lock(
    asset_vault: AssetVault,
) -> None:
    content = b"uncommitted source bytes left before vault reset"
    digest = hashlib.sha256(content).hexdigest()
    storage_path = f"assets/{digest[:2]}/{digest}"
    journal_path = write_asset_publication_journal(
        operation_id=str(uuid.uuid4()),
        profile_id=asset_vault.profile_ids[0],
        kind="source_document",
        storage_path=storage_path,
        sha256=digest,
        byte_size=len(content),
    )
    absolute_path, _created = atomic_write(storage_path, content)

    with asset_vault.factory() as session:
        owner = session.get(User, asset_vault.user_ids[0])
        assert owner is not None
        authority = issue_auth_session(session, owner)
        begin_vault_maintenance(
            session,
            owner.id,
            authority.session_id,
            VAULT_STATE_RESET_PENDING,
            token_purpose=ACCESS_PURPOSE_SESSION,
        )
        delete_complete_vault(
            session,
            owner.id,
            maintenance_session_id=authority.session_id,
        )

    assert not absolute_path.exists()
    assert not (asset_vault.data_directory / journal_path).exists()
    with asset_vault.factory() as verification:
        assert verification.get(CandidateProfile, asset_vault.profile_ids[0]) is None
        assert verification.get(CandidateProfile, asset_vault.profile_ids[1]) is not None
