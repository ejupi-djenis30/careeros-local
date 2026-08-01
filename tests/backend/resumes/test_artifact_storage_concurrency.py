import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock, get_ident

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import backend.resumes.draft_service as draft_service_module
import backend.resumes.publishing as publishing_module
import backend.resumes.storage as storage_module
from backend.career.deletion import begin_vault_maintenance, delete_complete_vault
from backend.career.models import CandidateProfile, CareerFact
from backend.db.base import Base, configure_sqlite_connection, ensure_sqlite_parent
from backend.models import User
from backend.models.user import VAULT_STATE_RESET_PENDING
from backend.resumes.canvas import normalize_canvas
from backend.resumes.draft_service import ResumeDraftService
from backend.resumes.models import ResumeArtifact, ResumeDraft, ResumeVersion
from backend.resumes.publication_service import ResumePublicationService
from backend.resumes.storage import (
    all_resume_publication_journals,
    is_resume_delete_pending,
    remove_stored_artifact,
    write_resume_publication_journal,
)
from backend.services.auth import ACCESS_PURPOSE_SESSION
from backend.services.auth_sessions import issue_auth_session
from backend.storage import atomic
from backend.storage.atomic import StorageWriteError


def _sqlite_vault(tmp_path, monkeypatch):
    data_directory = tmp_path / "private-data"
    monkeypatch.setattr(atomic.settings, "DATA_DIR", str(data_directory))
    database_path = (tmp_path / "resume-artifacts.db").as_posix()
    ensure_sqlite_parent(f"sqlite:///{database_path}")
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", configure_sqlite_connection)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with factory() as session:
        user = User(username="resume-owner", hashed_password="not-used-in-this-test")
        session.add(user)
        session.flush()
        profile = CandidateProfile(
            user_id=user.id,
            display_name="Mira Vale",
            headline="Analytical Engineer",
            summary="Builds dependable local systems.",
            email="mira@example.test",
            location={"city": "Zurich", "country": "CH"},
        )
        session.add(profile)
        session.flush()
        fact = CareerFact(
            profile_id=profile.id,
            fact_type="experience",
            position=0,
            payload={
                "role": "Analytical Engineer",
                "organization": "Local Systems",
                "start_date": "2020-01-01",
                "current": True,
                "description": "Builds durable private applications.",
                "achievements": ["Removed a publication race."],
            },
            verification_status="confirmed",
        )
        session.add(fact)
        session.flush()
        section_config = {
            "order": ["experience"],
            "include_summary": True,
            "include_email": True,
            "include_phone": False,
            "include_location": True,
            "include_links": False,
        }
        canvas = normalize_canvas(
            None,
            profile=profile,
            facts=[fact],
            template_kind="ats",
            section_config=section_config,
            content_overrides={},
        )
        draft = ResumeDraft(
            profile_id=profile.id,
            revision=1,
            profile_revision=profile.revision,
            title="Concurrency resume",
            template_kind="ats",
            section_config=section_config,
            selected_fact_ids=[fact.id],
            content_overrides={},
            canvas_document=canvas.model_dump(mode="json"),
            generation_context={},
        )
        session.add(draft)
        session.commit()
        return engine, factory, data_directory, user.id, draft.id


def _publish(factory, user_id: int, draft_id: str) -> int:
    with factory() as session:
        drafts = ResumeDraftService(session)
        published = ResumePublicationService(session, drafts).publish(user_id, draft_id)
        return published.version_number


def test_two_sqlite_connections_serialize_publication_version_numbers(
    tmp_path, monkeypatch
) -> None:
    engine, factory, data_directory, user_id, draft_id = _sqlite_vault(tmp_path, monkeypatch)
    original_store = publishing_module.store_resume_artifact
    first_store_entered = Event()
    release_first_store = Event()
    second_finished = Event()
    state_lock = Lock()
    blocking_thread: int | None = None
    blocked = False

    def gated_store(**kwargs):
        nonlocal blocked, blocking_thread
        thread_id = get_ident()
        with state_lock:
            if blocking_thread is None:
                blocking_thread = thread_id
            should_block = thread_id == blocking_thread and not blocked
            if should_block:
                blocked = True
        if should_block:
            first_store_entered.set()
            assert release_first_store.wait(5)
        return original_store(**kwargs)

    monkeypatch.setattr(publishing_module, "store_resume_artifact", gated_store)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(_publish, factory, user_id, draft_id)
            assert first_store_entered.wait(5)

            def publish_second() -> int:
                try:
                    return _publish(factory, user_id, draft_id)
                finally:
                    second_finished.set()

            second = executor.submit(publish_second)
            assert not second_finished.wait(0.2)
            release_first_store.set()
            assert sorted((first.result(timeout=5), second.result(timeout=5))) == [1, 2]

        with factory() as verification:
            assert [
                version.version_number
                for version in verification.query(ResumeVersion)
                .order_by(ResumeVersion.version_number)
                .all()
            ] == [1, 2]
            assert verification.query(ResumeArtifact).count() == 4
            paths = [artifact.storage_path for artifact in verification.query(ResumeArtifact).all()]
        assert all((data_directory / path).is_file() for path in paths)
        assert list(data_directory.rglob(".write-*")) == []
    finally:
        release_first_store.set()
        engine.dispose()


def test_commit_acknowledgement_error_never_unlinks_committed_artifacts(
    tmp_path, monkeypatch
) -> None:
    engine, factory, data_directory, user_id, draft_id = _sqlite_vault(tmp_path, monkeypatch)
    try:
        with factory() as session:
            original_commit = session.commit

            def commit_then_raise() -> None:
                original_commit()
                raise RuntimeError("synthetic lost commit acknowledgement")

            monkeypatch.setattr(session, "commit", commit_then_raise)
            drafts = ResumeDraftService(session)
            published = ResumePublicationService(session, drafts).publish(user_id, draft_id)
            assert published.version_number == 1

        with factory() as verification:
            assert verification.query(ResumeVersion).count() == 1
            artifacts = verification.query(ResumeArtifact).all()
            assert len(artifacts) == 2
        assert all((data_directory / artifact.storage_path).is_file() for artifact in artifacts)
    finally:
        engine.dispose()


def test_precommit_failure_rolls_back_rows_and_durable_files(tmp_path, monkeypatch) -> None:
    engine, factory, data_directory, user_id, draft_id = _sqlite_vault(tmp_path, monkeypatch)
    try:
        with factory() as session:

            def fail_commit() -> None:
                raise RuntimeError("synthetic pre-commit failure")

            monkeypatch.setattr(session, "commit", fail_commit)
            drafts = ResumeDraftService(session)
            with pytest.raises(RuntimeError, match="pre-commit"):
                ResumePublicationService(session, drafts).publish(user_id, draft_id)

        with factory() as verification:
            assert verification.query(ResumeVersion).count() == 0
            assert verification.query(ResumeArtifact).count() == 0
        assert [path for path in data_directory.rglob("*") if path.is_file()] == []
    finally:
        engine.dispose()


def test_next_locked_publication_recovers_files_left_by_process_death(
    tmp_path, monkeypatch
) -> None:
    engine, factory, data_directory, user_id, draft_id = _sqlite_vault(tmp_path, monkeypatch)
    original_store = publishing_module.store_resume_artifact

    class SimulatedProcessDeath(BaseException):
        pass

    crashed = False

    def die_after_first_durable_write(**kwargs):
        nonlocal crashed
        stored = original_store(**kwargs)
        if not crashed:
            crashed = True
            raise SimulatedProcessDeath
        return stored

    try:
        monkeypatch.setattr(
            publishing_module,
            "store_resume_artifact",
            die_after_first_durable_write,
        )
        with factory() as interrupted:
            drafts = ResumeDraftService(interrupted)
            with pytest.raises(SimulatedProcessDeath):
                ResumePublicationService(interrupted, drafts).publish(user_id, draft_id)

        crash_artifacts = [
            path
            for path in data_directory.rglob("*")
            if path.is_file() and path.suffix in {".pdf", ".docx"}
        ]
        assert len(crash_artifacts) == 1
        assert len(list(data_directory.rglob(".publication-journal/*.json"))) == 1
        with factory() as verification:
            assert verification.query(ResumeVersion).count() == 0
            assert verification.query(ResumeArtifact).count() == 0

        monkeypatch.setattr(
            publishing_module,
            "store_resume_artifact",
            original_store,
        )
        assert _publish(factory, user_id, draft_id) == 1

        assert not crash_artifacts[0].exists()
        assert list(data_directory.rglob(".publication-journal/*.json")) == []
        with factory() as verification:
            assert verification.query(ResumeVersion).count() == 1
            artifacts = verification.query(ResumeArtifact).all()
            assert len(artifacts) == 2
        assert all((data_directory / artifact.storage_path).is_file() for artifact in artifacts)
    finally:
        engine.dispose()


def test_sqlite_vault_reset_waits_for_crashed_publisher_then_erases_journal(
    tmp_path,
    monkeypatch,
) -> None:
    engine, factory, data_directory, user_id, draft_id = _sqlite_vault(tmp_path, monkeypatch)
    original_store = publishing_module.store_resume_artifact
    artifact_written = Event()
    release_publisher = Event()
    deletion_finished = Event()
    crashed = False

    class SimulatedProcessDeath(BaseException):
        pass

    def stop_after_first_artifact(**kwargs):
        nonlocal crashed
        stored = original_store(**kwargs)
        if not crashed:
            crashed = True
            artifact_written.set()
            assert release_publisher.wait(timeout=5)
            raise SimulatedProcessDeath
        return stored

    def publish() -> None:
        with factory() as session:
            drafts = ResumeDraftService(session)
            ResumePublicationService(session, drafts).publish(user_id, draft_id)

    def erase(session_id: str) -> None:
        try:
            with factory() as session:
                delete_complete_vault(
                    session,
                    user_id,
                    maintenance_session_id=session_id,
                )
        finally:
            deletion_finished.set()

    try:
        with factory() as preparation:
            owner = preparation.get(User, user_id)
            assert owner is not None
            authority = issue_auth_session(preparation, owner)
            begin_vault_maintenance(
                preparation,
                user_id,
                authority.session_id,
                VAULT_STATE_RESET_PENDING,
                token_purpose=ACCESS_PURPOSE_SESSION,
            )

        monkeypatch.setattr(
            publishing_module,
            "store_resume_artifact",
            stop_after_first_artifact,
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            publication = pool.submit(publish)
            assert artifact_written.wait(timeout=5)
            deletion = pool.submit(erase, authority.session_id)
            # The journal and first artifact were written while publication held
            # SQLite's writer reservation. Reset must wait for that transaction
            # to roll back before taking its coherent recovery snapshot.
            assert not deletion_finished.wait(timeout=0.2)
            release_publisher.set()
            with pytest.raises(SimulatedProcessDeath):
                publication.result(timeout=5)
            deletion.result(timeout=5)

        assert [path for path in (data_directory / "resumes").rglob("*") if path.is_file()] == []
        with factory() as verification:
            assert verification.query(CandidateProfile).count() == 0
            assert verification.query(ResumeDraft).count() == 0
            assert verification.query(ResumeVersion).count() == 0
            assert verification.query(ResumeArtifact).count() == 0
    finally:
        release_publisher.set()
        engine.dispose()


def test_failed_artifact_unlink_keeps_durable_delete_state_for_retry(tmp_path, monkeypatch) -> None:
    engine, factory, data_directory, user_id, draft_id = _sqlite_vault(tmp_path, monkeypatch)
    try:
        assert _publish(factory, user_id, draft_id) == 1
        original_remove = draft_service_module.remove_stored_artifact
        calls = 0

        def fail_second_unlink(relative_path: str) -> bool:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic locked artifact")
            return original_remove(relative_path)

        monkeypatch.setattr(
            draft_service_module,
            "remove_stored_artifact",
            fail_second_unlink,
        )
        with factory() as first_delete:
            with pytest.raises(OSError, match="locked artifact"):
                ResumeDraftService(first_delete).delete(user_id, draft_id)

        with factory() as verification:
            draft = verification.get(ResumeDraft, draft_id)
            assert draft is not None
            assert is_resume_delete_pending(draft.generation_context)
            paths = [artifact.storage_path for artifact in verification.query(ResumeArtifact).all()]
            assert len(paths) == 2
        assert sum((data_directory / path).is_file() for path in paths) == 1

        monkeypatch.setattr(
            draft_service_module,
            "remove_stored_artifact",
            original_remove,
        )
        with factory() as retry:
            ResumeDraftService(retry).delete(user_id, draft_id)
        with factory() as idempotent_retry:
            ResumeDraftService(idempotent_retry).delete(user_id, draft_id)

        with factory() as verification:
            assert verification.get(ResumeDraft, draft_id) is None
            assert verification.query(ResumeVersion).count() == 0
            assert verification.query(ResumeArtifact).count() == 0
        assert [path for path in data_directory.rglob("*") if path.is_file()] == []
    finally:
        engine.dispose()


def test_artifact_unlink_fsyncs_its_parent_directory(tmp_path, monkeypatch) -> None:
    data_directory = tmp_path / "private-data"
    monkeypatch.setattr(atomic.settings, "DATA_DIR", str(data_directory))
    stored = publishing_module.store_resume_artifact(
        profile_id="profile",
        version_id="version",
        format="pdf",
        data=b"durable resume",
    )
    synced = []
    monkeypatch.setattr(atomic, "fsync_directory", lambda directory: synced.append(directory))

    assert remove_stored_artifact(stored.relative_path) is True
    assert synced == [stored.absolute_path.parent]
    assert not stored.absolute_path.exists()


def test_publication_journal_scan_counts_every_entry_and_stops_at_bound(
    tmp_path,
    monkeypatch,
) -> None:
    data_directory = tmp_path / "private-data"
    monkeypatch.setattr(atomic.settings, "DATA_DIR", str(data_directory))
    monkeypatch.setattr(storage_module, "_PUBLICATION_JOURNAL_SCAN_LIMIT", 2)
    journal_directory = data_directory / "resumes" / ".publication-journal"
    journal_directory.mkdir(parents=True)
    (journal_directory / "unrelated.tmp").write_bytes(b"bounded residue")
    write_resume_publication_journal(
        draft_id="draft-a",
        version_id="version-a",
        artifact_paths=[f"resumes/profile/version-a/{'a' * 64}.pdf"],
    )
    (journal_directory / "second-unexpected-entry").write_bytes(b"bounded residue")

    with pytest.raises(
        StorageWriteError,
        match="Too many pending resume publication recovery records",
    ):
        all_resume_publication_journals()


def _resume_journal(data_directory: Path, *, version_id: str = "version-a") -> Path:
    relative_path = write_resume_publication_journal(
        draft_id="draft-a",
        version_id=version_id,
        artifact_paths=[f"resumes/profile/{version_id}/{'a' * 64}.pdf"],
    )
    return data_directory / relative_path


def test_resume_publication_journal_rejects_oversized_content(tmp_path, monkeypatch) -> None:
    data_directory = tmp_path / "private-data"
    monkeypatch.setattr(atomic.settings, "DATA_DIR", str(data_directory))
    journal = _resume_journal(data_directory)
    journal.write_bytes(b"x" * (storage_module._PUBLICATION_JOURNAL_MAX_BYTES + 1))

    with pytest.raises(StorageWriteError, match="recovery metadata is invalid"):
        all_resume_publication_journals()


def test_resume_publication_journal_rejects_symlink_without_following_target(
    tmp_path,
    monkeypatch,
) -> None:
    data_directory = tmp_path / "private-data"
    monkeypatch.setattr(atomic.settings, "DATA_DIR", str(data_directory))
    journal = _resume_journal(data_directory)
    payload = journal.read_bytes()
    external = tmp_path / "external-resume-journal.json"
    external.write_bytes(payload)
    journal.unlink()
    try:
        journal.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"File symlinks are unavailable: {exc}")

    with pytest.raises(StorageWriteError, match="recovery metadata is invalid"):
        all_resume_publication_journals()

    assert external.read_bytes() == payload


def test_resume_publication_journal_rejects_hard_link_alias(tmp_path, monkeypatch) -> None:
    data_directory = tmp_path / "private-data"
    monkeypatch.setattr(atomic.settings, "DATA_DIR", str(data_directory))
    journal = _resume_journal(data_directory)
    alias = tmp_path / "resume-journal-hard-link"
    try:
        os.link(journal, alias)
    except OSError as exc:
        pytest.skip(f"Hard links are unavailable: {exc}")

    with pytest.raises(StorageWriteError, match="recovery metadata is invalid"):
        all_resume_publication_journals()

    assert journal.read_bytes() == alias.read_bytes()


def test_resume_publication_journal_rejects_lstat_open_swap(tmp_path, monkeypatch) -> None:
    data_directory = tmp_path / "private-data"
    monkeypatch.setattr(atomic.settings, "DATA_DIR", str(data_directory))
    journal = _resume_journal(data_directory)
    replacement = tmp_path / "replacement-resume-journal.json"
    replacement.write_bytes(journal.read_bytes())
    real_open = atomic.os.open
    swapped = False

    def swap_then_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if Path(path) == journal and not swapped:
            swapped = True
            replacement.replace(journal)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(atomic.os, "open", swap_then_open)
    with pytest.raises(StorageWriteError, match="recovery metadata is invalid"):
        all_resume_publication_journals()

    assert swapped is True


@pytest.mark.skipif(os.name != "nt", reason="Windows reparse-point contract")
def test_resume_publication_journal_rejects_directory_junction(tmp_path, monkeypatch) -> None:
    data_directory = tmp_path / "private-data"
    monkeypatch.setattr(atomic.settings, "DATA_DIR", str(data_directory))
    journal = _resume_journal(data_directory)
    journal.unlink()
    external = tmp_path / "external-journal-directory"
    external.mkdir()
    sentinel = external / "sentinel"
    sentinel.write_bytes(b"must remain")
    creation = subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(journal), str(external)],
        capture_output=True,
        check=False,
        text=True,
    )
    if creation.returncode != 0:
        pytest.skip(f"Directory junctions are unavailable: {creation.stderr.strip()}")
    try:
        with pytest.raises(StorageWriteError, match="recovery metadata is invalid"):
            all_resume_publication_journals()
        assert sentinel.read_bytes() == b"must remain"
    finally:
        os.rmdir(journal)
