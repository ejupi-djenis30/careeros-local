"""Tests for campaign workspace Alembic migration and downgrade fail-closed behavior."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models import User


@pytest.fixture
def disposable_migration_db(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="careeros-campaign-migration-") as folder:
        db_file = Path(folder) / "disposable_vault.sqlite"
        url = f"sqlite:///{db_file.as_posix()}"
        monkeypatch.setattr(settings, "DATABASE_URL", url)
        project = Path(__file__).resolve().parents[3]
        config = Config(str(project / "alembic.ini"))
        config.set_main_option("script_location", str(project / "backend/migrations"))
        config.set_main_option("sqlalchemy.url", url)

        # Upgrade to parent revision first
        command.upgrade(config, "b3c4d5e6f7a9")

        engine = sa.create_engine(url)
        sa.event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
        try:
            yield engine, config
        finally:
            engine.dispose()


def test_empty_campaign_migration_roundtrips_up_down_up(disposable_migration_db):
    engine, config = disposable_migration_db

    # 1. Upgrade to campaign workspace revision
    command.upgrade(config, "c0a1b2c3d4e5")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    assert "campaigns" in tables
    assert "campaign_applications" in tables
    assert "campaign_artifacts" in tables

    # Verify column existence
    campaign_cols = {col["name"] for col in inspector.get_columns("campaigns")}
    assert {"id", "user_id", "name", "source_fingerprint", "tracker_sha256", "summary", "created_at", "updated_at"}.issubset(campaign_cols)

    # 2. Downgrade when empty succeeds
    command.downgrade(config, "b3c4d5e6f7a9")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    assert "campaigns" not in tables
    assert "campaign_applications" not in tables
    assert "campaign_artifacts" not in tables

    # 3. Upgrade back to head succeeds
    command.upgrade(config, "c0a1b2c3d4e5")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    assert "campaigns" in tables
    assert "campaign_applications" in tables
    assert "campaign_artifacts" in tables


def test_downgrade_refuses_when_campaign_rows_exist(disposable_migration_db):
    engine, config = disposable_migration_db

    # Upgrade to head
    command.upgrade(config, "c0a1b2c3d4e5")

    # Insert a user and a campaign row
    with Session(engine) as session:
        user = User(username="migration-tester", hashed_password="pw")
        session.add(user)
        session.flush()

        session.execute(
            sa.text(
                "INSERT INTO campaigns (id, user_id, name, source_fingerprint, summary) "
                "VALUES (:id, :user_id, :name, :fp, :summary)"
            ),
            {
                "id": "c" * 36,
                "user_id": user.id,
                "name": "Active Campaign",
                "fp": "f" * 64,
                "summary": "{}",
            },
        )
        session.commit()

    # Attempt downgrade -> must fail closed
    with pytest.raises(RuntimeError, match="Cannot downgrade schema while campaign rows exist"):
        command.downgrade(config, "b3c4d5e6f7a9")

    # Verify tables and rows still intact
    inspector = sa.inspect(engine)
    assert "campaigns" in inspector.get_table_names()
    with Session(engine) as session:
        count = session.execute(sa.text("SELECT COUNT(*) FROM campaigns")).scalar_one()
        assert count == 1
        current_rev = session.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
        assert current_rev == "c0a1b2c3d4e5"


def test_campaign_migration_exact_indexes_constraints_and_foreign_keys(disposable_migration_db):
    engine, config = disposable_migration_db
    command.upgrade(config, "c0a1b2c3d4e5")
    inspector = sa.inspect(engine)

    # 1. Exact Index Names
    campaign_indexes = {idx["name"] for idx in inspector.get_indexes("campaigns")}
    expected_campaign_indexes = {"ix_campaigns_user_id", "ix_campaigns_user_created_at"}
    assert expected_campaign_indexes.issubset(campaign_indexes)

    app_indexes = {idx["name"] for idx in inspector.get_indexes("campaign_applications")}
    expected_app_indexes = {
        "ix_campaign_applications_campaign_id",
        "ix_campaign_applications_application_id",
        "ix_campaign_applications_campaign_source_order",
        "ix_campaign_applications_campaign_priority",
    }
    assert expected_app_indexes.issubset(app_indexes)

    artifact_indexes = {idx["name"] for idx in inspector.get_indexes("campaign_artifacts")}
    expected_artifact_indexes = {
        "ix_campaign_artifacts_campaign_id",
        "ix_campaign_artifacts_application_id",
        "ix_campaign_artifacts_asset_id",
        "ix_campaign_artifacts_campaign_source_order",
    }
    assert expected_artifact_indexes.issubset(artifact_indexes)

    # 2. Unique Constraints
    def get_all_uniques(table_name: str) -> list[tuple[str | None, list[str]]]:
        uniques = []
        for uq in inspector.get_unique_constraints(table_name):
            uniques.append((uq.get("name"), uq.get("column_names", [])))
        for idx in inspector.get_indexes(table_name):
            if idx.get("unique"):
                uniques.append((idx.get("name"), idx.get("column_names", [])))
        return uniques

    campaign_uniques = [cols for _, cols in get_all_uniques("campaigns")]
    assert ["user_id", "source_fingerprint"] in campaign_uniques

    app_uniques = [cols for _, cols in get_all_uniques("campaign_applications")]
    assert ["campaign_id", "source_application_id"] in app_uniques
    assert ["campaign_id", "application_id"] in app_uniques

    artifact_uniques = [cols for _, cols in get_all_uniques("campaign_artifacts")]
    assert ["campaign_id", "relative_path"] in artifact_uniques

    # 3. Foreign Key ondelete policies
    def get_fk_map(table_name: str) -> dict[str, dict[str, str]]:
        fk_map = {}
        for fk in inspector.get_foreign_keys(table_name):
            col = fk["constrained_columns"][0]
            ref_table = fk["referred_table"]
            ondelete = (
                fk.get("options", {}).get("ondelete")
                or fk.get("ondelete")
                or ""
            ).upper()
            fk_map[col] = {"referred_table": ref_table, "ondelete": ondelete}
        return fk_map

    c_fks = get_fk_map("campaigns")
    assert c_fks["user_id"]["referred_table"] == "users"
    assert c_fks["user_id"]["ondelete"] == "CASCADE"

    ca_fks = get_fk_map("campaign_applications")
    assert ca_fks["campaign_id"]["referred_table"] == "campaigns"
    assert ca_fks["campaign_id"]["ondelete"] == "CASCADE"
    assert ca_fks["application_id"]["referred_table"] == "applications"
    assert ca_fks["application_id"]["ondelete"] == "CASCADE"

    art_fks = get_fk_map("campaign_artifacts")
    assert art_fks["campaign_id"]["referred_table"] == "campaigns"
    assert art_fks["campaign_id"]["ondelete"] == "CASCADE"
    assert art_fks["application_id"]["referred_table"] == "applications"
    assert art_fks["application_id"]["ondelete"] == "SET NULL"
    assert art_fks["asset_id"]["referred_table"] == "career_assets"
    assert art_fks["asset_id"]["ondelete"] == "RESTRICT"

    # 4. Category Check Constraint
    with Session(engine) as session:
        user = User(username="check-tester", hashed_password="pw")
        session.add(user)
        session.flush()

        session.execute(
            sa.text(
                "INSERT INTO campaigns (id, user_id, name, source_fingerprint, summary) "
                "VALUES ('c-chk', :uid, 'Check Campaign', :fp, '{}')"
            ),
            {"uid": user.id, "fp": "c" * 64},
        )
        session.execute(
            sa.text(
                "INSERT INTO candidate_profiles (id, user_id, display_name, revision, location, work_authorization, preferences) "
                "VALUES ('p-chk', :uid, 'Profile', 1, '{}', '[]', '{}')"
            ),
            {"uid": user.id},
        )
        session.execute(
            sa.text(
                "INSERT INTO career_assets (id, profile_id, kind, original_name, media_type, sha256, byte_size, storage_path, normalized) "
                "VALUES ('a-chk', 'p-chk', 'campaign_document', 'f.txt', 'text/plain', :sha, 10, 'assets/campaign/cc/cc', 0)"
            ),
            {"sha": "c" * 64},
        )
        session.commit()

        # Valid category succeeds
        session.execute(
            sa.text(
                "INSERT INTO campaign_artifacts (id, campaign_id, asset_id, relative_path, display_name, category) "
                "VALUES ('art-valid', 'c-chk', 'a-chk', 'vac/1.md', '1.md', 'vacancy')"
            )
        )
        session.commit()

        # 'credential' category raises IntegrityError
        with pytest.raises(sa.exc.IntegrityError):
            session.execute(
                sa.text(
                    "INSERT INTO campaign_artifacts (id, campaign_id, asset_id, relative_path, display_name, category) "
                    "VALUES ('art-cred', 'c-chk', 'a-chk', 'cred/1.xlsx', '1.xlsx', 'credential')"
                )
            )
            session.commit()
        session.rollback()
