import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.career.models import CandidateProfile, CareerFact
from backend.db.base import Base, configure_sqlite_connection, ensure_sqlite_parent
from backend.models import User
from backend.resumes.canvas import normalize_canvas
from backend.resumes.models import ResumeDraft, ResumeVersion
from backend.resumes.schemas import ResumeDraftResponse, ResumeDraftUpdate, ResumeSync
from backend.resumes.service import ResumeConflictError, ResumeNotFoundError, ResumeService
from backend.resumes.storage import RESUME_DELETE_PENDING_KEY

MANUAL_TITLE = "Synthetic newer manual title"


@dataclass
class SyncVault:
    engine: Engine
    factory: sessionmaker[Session]
    user_id: int
    draft_id: str


@pytest.fixture
def sync_vault(monkeypatch: pytest.MonkeyPatch) -> Iterator[SyncVault]:
    with TemporaryDirectory(prefix="careeros-sync-consistency-") as directory:
        root = Path(directory)
        monkeypatch.setattr("backend.core.config.settings.DATA_DIR", str(root / "data"))
        database_url = "sqlite:///" + (root / "sync.sqlite").as_posix()
        ensure_sqlite_parent(database_url)
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        event.listen(engine, "connect", configure_sqlite_connection)
        factory = sessionmaker(bind=engine, expire_on_commit=True)
        Base.metadata.create_all(engine)
        try:
            with factory() as db:
                user = User(username="synthetic-sync-owner", hashed_password="not-used")
                db.add(user)
                db.flush()
                profile = CandidateProfile(
                    user_id=user.id,
                    display_name="Synthetic owner",
                    summary="Synthetic local engineering profile.",
                    revision=2,
                )
                db.add(profile)
                db.flush()
                experience = CareerFact(
                    profile_id=profile.id,
                    fact_type="experience",
                    position=0,
                    payload={
                        "role": "Synthetic engineer",
                        "organization": "Synthetic organization",
                        "start_date": "2020-01-01",
                        "current": True,
                        "description": "Synthetic experience.",
                    },
                    verification_status="confirmed",
                    confidence=1.0,
                )
                db.add_all(
                    [
                        experience,
                        CareerFact(
                            profile_id=profile.id,
                            fact_type="skill",
                            position=1,
                            payload={
                                "name": "Synthetic current skill",
                                "category": "Engineering",
                                "level": "advanced",
                                "years": 1,
                            },
                            verification_status="confirmed",
                            confidence=1.0,
                        ),
                    ]
                )
                db.flush()
                config = {"order": ["experience"], "include_summary": False}
                canvas = normalize_canvas(
                    None,
                    profile=profile,
                    facts=[experience],
                    template_kind="ats",
                    section_config=config,
                    content_overrides={},
                )
                draft = ResumeDraft(
                    profile_id=profile.id,
                    revision=1,
                    profile_revision=1,
                    title="Synthetic synchronization draft",
                    template_kind="ats",
                    section_config=config,
                    selected_fact_ids=[experience.id],
                    content_overrides={},
                    canvas_document=canvas.model_dump(mode="json"),
                    generation_context={},
                )
                db.add(draft)
                db.commit()
                vault = SyncVault(engine, factory, user.id, draft.id)
            yield vault
        finally:
            engine.dispose()


def _manual_edit(response: ResumeDraftResponse) -> ResumeDraftUpdate:
    assert response.canvas_document is not None
    canvas = response.canvas_document.model_copy(deep=True)
    experience = next(section for section in canvas.sections if section.kind == "experience")
    experience.blocks[0].content.title = MANUAL_TITLE
    experience.blocks[0].manual_fields = ["title"]
    return ResumeDraftUpdate(
        expected_revision=response.revision,
        title=response.title,
        template_kind=response.template_kind,
        template_id=response.template_id,
        template_version=response.template_version,
        locale=response.locale,
        section_config=response.section_config,
        selected_fact_ids=response.selected_fact_ids,
        content_overrides=response.content_overrides,
        photo_asset_id=response.photo_asset_id,
        canvas_document=canvas,
    )


@pytest.fixture
def stale_edit(sync_vault: SyncVault) -> Iterator[ResumeService]:
    with sync_vault.factory() as cached, sync_vault.factory() as writer:
        service = ResumeService(cached)
        loaded = (
            service.drafts.draft(sync_vault.user_id, sync_vault.draft_id),
            service.drafts.profile(sync_vault.user_id),
        )
        assert loaded[0].revision == 1
        assert loaded[1].revision == 2
        writer_service = ResumeService(writer)
        current = writer_service.get(sync_vault.user_id, sync_vault.draft_id)
        acknowledged = writer_service.update(
            sync_vault.user_id, sync_vault.draft_id, _manual_edit(current)
        )
        assert acknowledged.revision == 2
        yield service


def _fingerprint(vault: SyncVault) -> str:
    with vault.factory() as db:
        inventory = {}
        for model in (CandidateProfile, CareerFact, ResumeDraft, ResumeVersion):
            rows = [
                {column.name: getattr(row, column.name) for column in model.__table__.columns}
                for row in db.query(model).all()
            ]
            inventory[model.__tablename__] = sorted(
                rows, key=lambda row: json.dumps(row, sort_keys=True, default=str)
            )
        return hashlib.sha256(
            json.dumps(inventory, sort_keys=True, default=str).encode()
        ).hexdigest()


def _sync(mode: str, revision: int) -> ResumeSync:
    return ResumeSync.model_validate(
        {
            "expected_revision": revision,
            "mode": mode,
            "sections": ["skill"] if mode == "apply" else [],
        }
    )


@pytest.mark.parametrize("mode", ["apply", "reset"])
def test_cached_stale_sync_preserves_committed_manual_edit(
    sync_vault: SyncVault, stale_edit: ResumeService, mode: str
) -> None:
    before = _fingerprint(sync_vault)
    with pytest.raises(ResumeConflictError):
        stale_edit.synchronize(sync_vault.user_id, sync_vault.draft_id, _sync(mode, 1))
    stale_edit.drafts.db.rollback()
    assert _fingerprint(sync_vault) == before


@pytest.mark.usefixtures("stale_edit")
@pytest.mark.parametrize("mode", ["apply", "reset"])
def test_fresh_stale_sync_is_rejected(sync_vault: SyncVault, mode: str) -> None:
    before = _fingerprint(sync_vault)
    with sync_vault.factory() as db:
        with pytest.raises(ResumeConflictError):
            ResumeService(db).synchronize(sync_vault.user_id, sync_vault.draft_id, _sync(mode, 1))
        db.rollback()
    assert _fingerprint(sync_vault) == before


@pytest.mark.usefixtures("stale_edit")
@pytest.mark.parametrize("mode", ["apply", "reset"])
def test_current_sync_updates_once_and_preserves_apply_manual_fields(
    sync_vault: SyncVault, mode: str
) -> None:
    with sync_vault.factory() as db:
        result = ResumeService(db).synchronize(
            sync_vault.user_id, sync_vault.draft_id, _sync(mode, 2)
        )
        assert result.applied and result.draft is not None
        assert result.draft.revision == 3
        assert result.draft.profile_revision == 2
        assert len(result.draft.selected_fact_ids) == 2
        assert (MANUAL_TITLE in result.draft.model_dump_json()) == (mode == "apply")
        assert db.query(CareerFact).count() == 2


@pytest.mark.usefixtures("stale_edit")
def test_preview_uses_no_write_or_writer_reservation(sync_vault: SyncVault) -> None:
    before = _fingerprint(sync_vault)
    writes = []
    commits = []

    def inspect_sql(_connection, _cursor, statement, _parameters, _context, _many):
        normalized = statement.strip().upper()
        if normalized.startswith(("UPDATE ", "INSERT ", "DELETE ", "BEGIN IMMEDIATE")):
            writes.append(True)

    def inspect_commit(_connection):
        commits.append(True)

    event.listen(sync_vault.engine, "before_cursor_execute", inspect_sql)
    event.listen(sync_vault.engine, "commit", inspect_commit)
    try:
        with sync_vault.factory() as db:
            result = ResumeService(db).synchronize(
                sync_vault.user_id, sync_vault.draft_id, _sync("preview", 2)
            )
            assert not result.applied and result.draft is None
    finally:
        event.remove(sync_vault.engine, "before_cursor_execute", inspect_sql)
        event.remove(sync_vault.engine, "commit", inspect_commit)
    assert len(writes) == len(commits) == 0
    assert _fingerprint(sync_vault) == before


@pytest.mark.parametrize("mode", ["apply", "reset", "preview"])
def test_sync_cannot_mutate_another_owners_draft(sync_vault: SyncVault, mode: str) -> None:
    with sync_vault.factory() as db:
        foreign = User(username="synthetic-other-sync-owner", hashed_password="not-used")
        db.add(foreign)
        db.flush()
        db.add(CandidateProfile(user_id=foreign.id, display_name="Synthetic other owner"))
        db.commit()
        foreign_id = foreign.id
    before = _fingerprint(sync_vault)
    with sync_vault.factory() as db:
        with pytest.raises(ResumeNotFoundError):
            ResumeService(db).synchronize(foreign_id, sync_vault.draft_id, _sync(mode, 1))
        db.rollback()
    assert _fingerprint(sync_vault) == before


@pytest.mark.usefixtures("stale_edit")
@pytest.mark.parametrize("mode", ["apply", "reset"])
def test_failed_sync_rolls_back_flushed_changes(
    sync_vault: SyncVault, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _fingerprint(sync_vault)
    with sync_vault.factory() as db:

        def fail_commit() -> None:
            db.flush()
            raise OSError("Synthetic failure before commit")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(OSError, match="Synthetic failure before commit"):
            ResumeService(db).synchronize(sync_vault.user_id, sync_vault.draft_id, _sync(mode, 2))
        db.rollback()
    assert _fingerprint(sync_vault) == before


@pytest.mark.usefixtures("stale_edit")
@pytest.mark.parametrize("mode", ["apply", "reset"])
def test_sync_ack_validation_failure_rolls_back_changes(
    sync_vault: SyncVault, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _fingerprint(sync_vault)
    with sync_vault.factory() as db:
        service = ResumeService(db)

        def invalid_ack(_profile: CandidateProfile, _draft: ResumeDraft) -> ResumeDraftResponse:
            return ResumeDraftResponse.model_validate({})

        monkeypatch.setattr(service.drafts, "response", invalid_ack)
        with pytest.raises(ValidationError):
            service.synchronize(sync_vault.user_id, sync_vault.draft_id, _sync(mode, 2))
        db.rollback()
    assert _fingerprint(sync_vault) == before


def test_sync_refreshes_cached_profile_facts(sync_vault: SyncVault) -> None:
    with sync_vault.factory() as cached, sync_vault.factory() as writer:
        service = ResumeService(cached)
        profile = service.drafts.profile(sync_vault.user_id)
        assert profile.revision == 2 and len(profile.facts) == 2
        current = writer.get(CandidateProfile, profile.id)
        assert current is not None
        writer.add(
            CareerFact(
                profile_id=current.id,
                fact_type="skill",
                position=2,
                payload={
                    "name": "Synthetic latest skill",
                    "category": "Engineering",
                    "level": "advanced",
                    "years": 1,
                },
                verification_status="confirmed",
                confidence=1.0,
            )
        )
        current.revision += 1
        writer.commit()
        result = service.synchronize(sync_vault.user_id, sync_vault.draft_id, _sync("apply", 1))
        assert result.current_profile_revision == 3 and result.draft is not None
        assert result.draft.profile_revision == 3
        assert len(result.draft.selected_fact_ids) == 3


@pytest.mark.parametrize("mode", ["apply", "reset"])
def test_sync_cannot_reactivate_cached_deletion_pending_draft(
    sync_vault: SyncVault, mode: str
) -> None:
    with sync_vault.factory() as cached, sync_vault.factory() as writer:
        service = ResumeService(cached)
        loaded = service.drafts.draft(sync_vault.user_id, sync_vault.draft_id)
        assert loaded.revision == 1
        current = writer.get(ResumeDraft, sync_vault.draft_id)
        assert current is not None
        current.generation_context = {RESUME_DELETE_PENDING_KEY: {"version": 1}}
        current.revision += 1
        writer.commit()
        before = _fingerprint(sync_vault)
        with pytest.raises(ResumeNotFoundError):
            service.synchronize(sync_vault.user_id, sync_vault.draft_id, _sync(mode, 1))
        cached.rollback()
        assert _fingerprint(sync_vault) == before
