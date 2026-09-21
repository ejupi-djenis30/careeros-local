import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from backend.applications.models import (
    Application,
    ApplicationDossierDraft,
    ApplicationPacketArtifact,
)
from backend.career.models import CandidateProfile
from backend.core.config import settings
from backend.models import User
from backend.resumes.models import ResumeDraft, ResumeVersion


@pytest.fixture
def migrated_material_db(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="careeros-material-migration-") as folder:
        url = "sqlite:///" + (Path(folder) / "vault.sqlite").as_posix()
        monkeypatch.setattr(settings, "DATABASE_URL", url)
        project = Path(__file__).resolve().parents[3]
        config = Config(str(project / "alembic.ini"))
        config.set_main_option("script_location", str(project / "backend/migrations"))
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "b3c4d5e6f7a9")
        engine = sa.create_engine(url)
        sa.event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
        try:
            yield engine, config
        finally:
            engine.dispose()


def seed_material_binding(db, *, draft_bound=True):
    user = User(username="material-owner", hashed_password="unused")
    db.add(user)
    db.flush()
    profile = CandidateProfile(user_id=user.id, display_name="Synthetic Owner", revision=1)
    db.add(profile)
    db.flush()
    resume = ResumeDraft(
        profile_id=profile.id,
        profile_revision=1,
        revision=1,
        title="Synthetic CV",
        template_kind="ats",
    )
    db.add(resume)
    db.flush()
    now = datetime.now(timezone.utc)
    version = ResumeVersion(
        draft_id=resume.id,
        version_number=1,
        semantic_version="1.0.0",
        snapshot={"legacy": "immutable"},
        snapshot_sha256="a" * 64,
        profile_revision=1,
        selected_fact_ids=[],
        template_kind="ats",
        renderer_version="legacy",
        published_at=now,
        quality_report={"passed": True},
    )
    db.add(version)
    db.flush()
    application = Application(
        user_id=user.id,
        resume_version_id=version.id,
        revision=1,
        current_stage="preparing",
        job_snapshot={"title": "Synthetic"},
        job_title="Synthetic",
        job_company="Example",
        latest_event_at=now,
    )
    db.add(application)
    db.flush()
    dossier = ApplicationDossierDraft(
        application_id=application.id,
        application_revision=1,
        revision=1,
        content={"requirement_matrix": []},
        resume_draft_id=resume.id if draft_bound else None,
        resume_draft_revision=1 if draft_bound else None,
        resume_version_id=None if draft_bound else version.id,
    )
    db.add(dossier)
    db.commit()
    return user.id, application.id, resume.id, version.id, dossier.id


def test_migrated_binding_checks_and_resume_delete_cascade(migrated_material_db):
    engine, _ = migrated_material_db
    with Session(engine) as db:
        _, _, resume_id, version_id, dossier_id = seed_material_binding(db)
        for values in [
            dict(resume_draft_revision=None),
            dict(resume_draft_revision=0),
            dict(resume_version_id=version_id),
        ]:
            with pytest.raises(sa.exc.IntegrityError):
                db.execute(
                    sa.update(ApplicationDossierDraft)
                    .where(ApplicationDossierDraft.id == dossier_id)
                    .values(**values)
                )
            db.rollback()
        db.execute(sa.delete(ResumeDraft).where(ResumeDraft.id == resume_id))
        db.commit()
        assert db.get(ApplicationDossierDraft, dossier_id) is None


@pytest.mark.parametrize("pending", ["draft", "packet"])
def test_populated_material_downgrade_rejects_before_any_schema_or_data_loss(
    migrated_material_db, pending
):
    engine, config = migrated_material_db
    with Session(engine) as db:
        _, app_id, _, version_id, dossier_id = seed_material_binding(
            db, draft_bound=pending == "draft"
        )
        if pending == "packet":
            db.add(
                ApplicationPacketArtifact(
                    application_id=app_id,
                    dossier_id=dossier_id,
                    storage_path="synthetic-unused.zip",
                    sha256="b" * 64,
                    byte_size=100,
                )
            )
            db.commit()
    with pytest.raises(RuntimeError, match="Cannot downgrade"):
        command.downgrade(config, "b2c3d4e5f6a7")
    assert "application_packet_artifacts" in sa.inspect(engine).get_table_names()
    with Session(engine) as db:
        assert db.get(ApplicationDossierDraft, dossier_id) is not None
        assert db.get(ResumeVersion, version_id).snapshot == {"legacy": "immutable"}
        assert (
            db.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
            == "b3c4d5e6f7a9"
        )


def test_legacy_version_binding_roundtrips_material_downgrade_upgrade(migrated_material_db):
    engine, config = migrated_material_db
    with Session(engine) as db:
        _, _, _, version_id, dossier_id = seed_material_binding(db, draft_bound=False)
    command.downgrade(config, "b2c3d4e5f6a7")
    command.upgrade(config, "b3c4d5e6f7a9")
    with Session(engine) as db:
        assert db.get(ApplicationDossierDraft, dossier_id).resume_version_id == version_id
        version = db.get(ResumeVersion, version_id)
        assert version.snapshot == {"legacy": "immutable"}
        assert version.snapshot_sha256 == "a" * 64
