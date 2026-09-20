import pytest
from sqlalchemy.orm import Session

from backend.applications.exceptions import ApplicationConflictError
from backend.applications.models import ApplicationDossierDraft
from backend.applications.schemas import ApplicationDossierDraftPut
from backend.applications.service import ApplicationService
from backend.models import User
from tests.backend.applications.test_material_migration import (
    migrated_material_db as _migrated_material_db,
)
from tests.backend.applications.test_material_migration import (
    seed_material_binding,
)

migrated_material_db = _migrated_material_db


def draft_request(resume_id, text, *, expected_revision=1):
    return ApplicationDossierDraftPut(
        expected_application_revision=1,
        expected_revision=expected_revision,
        resume_draft_id=resume_id,
        expected_resume_draft_revision=1,
        content={
            "cover_letter": text,
            "requirement_matrix": [
                {"client_id": "requirement-1", "requirement": "", "evidence_fact_ids": []}
            ],
        },
    )


def test_two_real_sessions_cannot_overwrite_the_same_dossier_revision(migrated_material_db):
    engine, _ = migrated_material_db
    with Session(engine) as seed:
        user_id, app_id, resume_id, _, dossier_id = seed_material_binding(seed)
    with (
        Session(engine, expire_on_commit=False) as first,
        Session(engine, expire_on_commit=False) as second,
    ):
        first_cached = first.get(ApplicationDossierDraft, dossier_id)
        second_cached = second.get(ApplicationDossierDraft, dossier_id)
        assert first_cached.revision == second_cached.revision == 1
        ApplicationService(first).mutate_dossier_draft_flush_only(
            user_id, app_id, draft_request(resume_id, "First edit")
        )
        with Session(engine) as uncommitted_reader:
            assert uncommitted_reader.get(ApplicationDossierDraft, dossier_id).revision == 1
        first.commit()
        with pytest.raises(ApplicationConflictError):
            ApplicationService(second).mutate_dossier_draft_flush_only(
                user_id, app_id, draft_request(resume_id, "Second edit")
            )
        second.rollback()
    with Session(engine) as verification:
        dossier = verification.get(ApplicationDossierDraft, dossier_id)
        assert dossier.revision == 2
        assert dossier.content["cover_letter"] == "First edit"


def test_flush_only_conflict_leaves_outer_transaction_control_to_caller(
    migrated_material_db, monkeypatch
):
    engine, _ = migrated_material_db
    with Session(engine) as db:
        user_id, app_id, resume_id, _, _ = seed_material_binding(db)
        owner = db.get(User, user_id)
        owner.preference_signals = {"pending_outer_change": True}
        db.flush()
        real_rollback = db.rollback

        def forbidden_rollback():
            pytest.fail("flush-only domain seam rolled back the outer transaction")

        monkeypatch.setattr(db, "rollback", forbidden_rollback)
        with pytest.raises(ApplicationConflictError):
            ApplicationService(db).mutate_dossier_draft_flush_only(
                user_id, app_id, draft_request(resume_id, "Conflict", expected_revision=999)
            )
        assert db.get(User, user_id).preference_signals == {"pending_outer_change": True}
        monkeypatch.setattr(db, "rollback", real_rollback)
        db.rollback()
    with Session(engine) as verification:
        assert verification.get(User, user_id).preference_signals is None
