"""Tests for Campaign persistence models, constraints, and foreign key behaviors."""

from __future__ import annotations

import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from backend.applications.models import Application
from backend.campaigns.models import (
    ALLOWED_ARTIFACT_CATEGORIES,
    Campaign,
    CampaignApplication,
    CampaignArtifact,
)
from backend.career.models import CandidateProfile, CareerAsset
from backend.models import User
from backend.models.base_model import Base


@pytest.fixture
def db_session():
    with tempfile.TemporaryDirectory(prefix="careeros-test-models-") as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = sa.create_engine(
            f"sqlite:///{db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        sa.event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as session:
            yield session
        engine.dispose()


def _seed_base_entities(session: Session) -> tuple[User, CandidateProfile, CareerAsset, Application]:
    user = User(username="test-user", hashed_password="pw")
    session.add(user)
    session.flush()

    profile = CandidateProfile(user_id=user.id, display_name="Test Profile", revision=1)
    session.add(profile)
    session.flush()

    asset = CareerAsset(
        profile_id=profile.id,
        kind="campaign_document",
        original_name="cv.pdf",
        media_type="application/pdf",
        sha256="a" * 64,
        byte_size=1234,
        storage_path=f"assets/campaign/{('a' * 64)[:2]}/{'a' * 64}",
    )
    session.add(asset)
    session.flush()

    app = Application(
        user_id=user.id,
        revision=1,
        current_stage="applied",
        job_snapshot={"title": "Engineer", "company": "Acme Corp"},
        job_title="Engineer",
        job_company="Acme Corp",
        latest_event_at=datetime.now(timezone.utc),
    )
    session.add(app)
    session.commit()
    return user, profile, asset, app


def test_campaign_creation_and_user_cascade(db_session: Session):
    user, _, _, _ = _seed_base_entities(db_session)
    campaign = Campaign(
        user_id=user.id,
        name="Summer 2026",
        source_fingerprint="f" * 64,
        tracker_sha256="t" * 64,
        summary={"total": 10},
    )
    db_session.add(campaign)
    db_session.commit()

    campaign_id = campaign.id
    assert campaign.id is not None
    assert campaign.created_at is not None
    assert campaign.updated_at is not None

    # Deleting user cascades to campaign via database FK
    db_session.delete(user)
    db_session.commit()
    db_session.expunge_all()
    assert db_session.get(Campaign, campaign_id) is None


def test_campaign_user_fingerprint_uniqueness(db_session: Session):
    user1, _, _, _ = _seed_base_entities(db_session)
    user2 = User(username="user-2", hashed_password="pw")
    db_session.add(user2)
    db_session.commit()

    c1 = Campaign(user_id=user1.id, name="C1", source_fingerprint="1" * 64, summary={})
    db_session.add(c1)
    db_session.commit()

    # Same user, same fingerprint -> error
    c1_dup = Campaign(user_id=user1.id, name="C1-dup", source_fingerprint="1" * 64, summary={})
    db_session.add(c1_dup)
    with pytest.raises(sa.exc.IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Different user, same fingerprint -> allowed
    c2 = Campaign(user_id=user2.id, name="C2", source_fingerprint="1" * 64, summary={})
    db_session.add(c2)
    db_session.commit()
    assert c2.id is not None


def test_campaign_application_uniqueness_and_cascades(db_session: Session):
    user, _, _, app = _seed_base_entities(db_session)
    campaign = Campaign(user_id=user.id, name="C1", source_fingerprint="2" * 64, summary={})
    db_session.add(campaign)
    db_session.commit()

    camp_app = CampaignApplication(
        campaign_id=campaign.id,
        application_id=app.id,
        source_application_id="SRC-001",
        source_order=1,
        source_status="Applied",
        priority="High",
        platform="LinkedIn",
        category="Tech",
        outcome="Screening",
        found_at=date(2026, 1, 1),
        applied_at=date(2026, 1, 2),
        follow_up_at=date(2026, 1, 16),
        last_update_at=date(2026, 1, 5),
        tracker_record={"Application ID": "SRC-001"},
        provenance={"tracker": True},
    )
    db_session.add(camp_app)
    db_session.commit()

    # Duplicate source_application_id in same campaign -> error
    app2 = Application(
        user_id=user.id,
        revision=1,
        current_stage="saved",
        job_snapshot={"title": "Dev"},
        job_title="Dev",
        job_company="Globex",
        latest_event_at=datetime.now(timezone.utc),
    )
    db_session.add(app2)
    db_session.commit()

    dup_src = CampaignApplication(
        campaign_id=campaign.id,
        application_id=app2.id,
        source_application_id="SRC-001",
        source_order=2,
    )
    db_session.add(dup_src)
    with pytest.raises(sa.exc.IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Duplicate application_id in same campaign -> error
    dup_app = CampaignApplication(
        campaign_id=campaign.id,
        application_id=app.id,
        source_application_id="SRC-002",
        source_order=2,
    )
    db_session.add(dup_app)
    with pytest.raises(sa.exc.IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Deleting campaign cascades to CampaignApplication
    db_session.delete(campaign)
    db_session.commit()
    assert db_session.get(CampaignApplication, camp_app.id) is None


def test_campaign_artifact_constraints_and_cascades(db_session: Session):
    user, _, asset, app = _seed_base_entities(db_session)
    campaign = Campaign(user_id=user.id, name="C-Art", source_fingerprint="3" * 64, summary={})
    db_session.add(campaign)
    db_session.commit()

    now = datetime.now(timezone.utc)
    artifact = CampaignArtifact(
        campaign_id=campaign.id,
        application_id=app.id,
        asset_id=asset.id,
        relative_path="application-packets/APP-001/cv.pdf",
        display_name="cv.pdf",
        category="cv",
        source_order=0,
        created_at=now,
    )
    db_session.add(artifact)
    db_session.commit()

    # Duplicate relative_path in same campaign -> error
    dup_path = CampaignArtifact(
        campaign_id=campaign.id,
        application_id=None,
        asset_id=asset.id,
        relative_path="application-packets/APP-001/cv.pdf",
        display_name="another_cv.pdf",
        category="cv",
        source_order=1,
        created_at=now,
    )
    db_session.add(dup_path)
    with pytest.raises(sa.exc.IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Category check constraint: every allowed category succeeds
    for cat in ALLOWED_ARTIFACT_CATEGORIES:
        art = CampaignArtifact(
            campaign_id=campaign.id,
            application_id=None,
            asset_id=asset.id,
            relative_path=f"test/{cat}.dat",
            display_name=f"{cat}.dat",
            category=cat,
            source_order=1,
            created_at=now,
        )
        db_session.add(art)
        db_session.commit()

    # Category check constraint: 'credential' must FAIL closed
    cred_artifact = CampaignArtifact(
        campaign_id=campaign.id,
        application_id=None,
        asset_id=asset.id,
        relative_path="credentials/creds.xlsx",
        display_name="creds.xlsx",
        category="credential",
        source_order=99,
        created_at=now,
    )
    db_session.add(cred_artifact)
    with pytest.raises(sa.exc.IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Unrecognized category must also FAIL
    bad_artifact = CampaignArtifact(
        campaign_id=campaign.id,
        application_id=None,
        asset_id=asset.id,
        relative_path="bad/file.dat",
        display_name="file.dat",
        category="unrecognized_cat",
        source_order=99,
        created_at=now,
    )
    db_session.add(bad_artifact)
    with pytest.raises(sa.exc.IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Deleting Application sets application_id to NULL (SET NULL)
    db_session.delete(app)
    db_session.commit()
    refreshed = db_session.get(CampaignArtifact, artifact.id)
    assert refreshed is not None
    assert refreshed.application_id is None

    # Deleting CareerAsset while referenced raises IntegrityError (RESTRICT)
    db_session.delete(asset)
    with pytest.raises(sa.exc.IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_campaign_artifact_default_created_at(db_session: Session):
    user, _, asset, _ = _seed_base_entities(db_session)
    campaign = Campaign(user_id=user.id, name="C-Default-Created", source_fingerprint="9" * 64, summary={})
    db_session.add(campaign)
    db_session.commit()

    before = datetime.now(timezone.utc)
    artifact = CampaignArtifact(
        campaign_id=campaign.id,
        application_id=None,
        asset_id=asset.id,
        relative_path="scripts/export.py",
        display_name="export.py",
        category="script",
    )
    db_session.add(artifact)
    db_session.commit()

    assert artifact.id is not None
    assert artifact.created_at is not None
    assert artifact.created_at.tzinfo is not None
    after = datetime.now(timezone.utc)
    assert before <= artifact.created_at <= after
