import json
from pathlib import Path
from tempfile import TemporaryDirectory

import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from backend.career.models import CandidateProfile
from backend.core.config import settings
from backend.resumes.models import ResumeDraft

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_canvas_migration_preserves_legacy_drafts_and_round_trips(monkeypatch):
    with TemporaryDirectory(dir=PROJECT_ROOT / "cmd_outputs") as directory:
        path = Path(directory) / "canvas-migration.db"
        database_url = f"sqlite:///{path.as_posix()}"
        monkeypatch.setattr(settings, "DATABASE_URL", database_url)
        config = _config(database_url)
        command.upgrade(config, "y5z6a7b8c9d0")
        engine = sa.create_engine(database_url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "INSERT INTO users (id, username, hashed_password) "
                        "VALUES (1, 'canvas-user', 'local-hash')"
                    )
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO candidate_profiles "
                        "(id, user_id, revision, display_name, headline, summary, location, "
                        "work_authorization, preferences) VALUES "
                        "(:id, 1, 1, 'Ada', 'Engineer', 'Builds systems', :empty, :empty, :empty)"
                    ),
                    {"id": "11111111-1111-4111-8111-111111111111", "empty": "{}"},
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO resume_drafts "
                        "(id, profile_id, revision, profile_revision, title, template_kind, "
                        "section_config, selected_fact_ids, content_overrides) VALUES "
                        "(:id, :profile, 1, 1, 'Legacy CV', 'ats', :config, :facts, :overrides)"
                    ),
                    {
                        "id": "22222222-2222-4222-8222-222222222222",
                        "profile": "11111111-1111-4111-8111-111111111111",
                        "config": json.dumps({"order": ["skill"], "include_summary": True}),
                        "facts": json.dumps(["33333333-3333-4333-8333-333333333333"]),
                        "overrides": "{}",
                    },
                )

            command.upgrade(config, "z6a7b8c9d0e1")
            columns = {column["name"] for column in sa.inspect(engine).get_columns("resume_drafts")}
            assert {"canvas_document", "generation_context"} <= columns
            with engine.connect() as connection:
                row = connection.execute(
                    sa.text("SELECT title, canvas_document, generation_context FROM resume_drafts")
                ).one()
                assert row[0] == "Legacy CV"
                assert json.loads(row[1]) == {}
                assert json.loads(row[2]) == {}

            command.downgrade(config, "y5z6a7b8c9d0")
            columns = {column["name"] for column in sa.inspect(engine).get_columns("resume_drafts")}
            assert "canvas_document" not in columns
            with engine.connect() as connection:
                assert connection.scalar(sa.text("SELECT count(*) FROM resume_drafts")) == 1
            command.upgrade(config, "head")
            assert "canvas_document" in {
                column["name"] for column in sa.inspect(engine).get_columns("resume_drafts")
            }
        finally:
            engine.dispose()


def test_legacy_empty_canvas_is_normalized_lazily(
    client, auth_headers, db_session, saved_detailed_profile
):
    profile = db_session.query(CandidateProfile).one()
    selected = [fact["id"] for fact in saved_detailed_profile["facts"]]
    draft = ResumeDraft(
        profile_id=profile.id,
        revision=1,
        profile_revision=profile.revision,
        title="Legacy local draft",
        template_kind="ats",
        section_config={"order": ["experience", "education", "skill"]},
        selected_fact_ids=selected,
        content_overrides={},
        canvas_document={},
        generation_context={},
    )
    db_session.add(draft)
    db_session.commit()
    response = client.get(f"/api/v1/resumes/{draft.id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["canvas_document"]["schema_version"] == 1
    assert response.json()["canvas_document"]["sections"][0]["kind"] == "identity"
    db_session.expire_all()
    assert (
        db_session.query(ResumeDraft).filter(ResumeDraft.id == draft.id).one().canvas_document == {}
    )


def test_head_schema_matches_models_and_preserves_relational_integrity(monkeypatch):
    with TemporaryDirectory(dir=PROJECT_ROOT / "cmd_outputs") as directory:
        path = Path(directory) / "head-schema.db"
        database_url = f"sqlite:///{path.as_posix()}"
        monkeypatch.setattr(settings, "DATABASE_URL", database_url)
        config = _config(database_url)
        command.upgrade(config, "z6a7b8c9d0e1")
        engine = sa.create_engine(database_url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "INSERT INTO users "
                        "(id, username, hashed_password, created_at, updated_at) "
                        "VALUES (1, 'legacy-null-user', NULL, NULL, NULL)"
                    )
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO search_profiles "
                        "(id, user_id, created_at, updated_at) VALUES (1, 1, NULL, NULL)"
                    )
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO scraped_jobs "
                        "(id, platform, platform_job_id, title, company, external_url) "
                        "VALUES (1, 'legacy', 'job-1', 'Engineer', 'Local Co', 'local://job-1')"
                    )
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO jobs "
                        "(id, user_id, search_profile_id, scraped_job_id, dismissed, "
                        "created_at, updated_at) VALUES (1, 1, 1, 1, 0, NULL, NULL)"
                    )
                )

            command.upgrade(config, "head")
            inspector = sa.inspect(engine)
            jobs_columns = {column["name"]: column for column in inspector.get_columns("jobs")}
            users_columns = {column["name"]: column for column in inspector.get_columns("users")}
            profile_columns = {
                column["name"]: column for column in inspector.get_columns("search_profiles")
            }
            assert jobs_columns["created_at"]["nullable"] is False
            assert jobs_columns["updated_at"]["nullable"] is False
            assert users_columns["hashed_password"]["nullable"] is False
            assert users_columns["created_at"]["nullable"] is False
            assert users_columns["updated_at"]["nullable"] is False
            assert profile_columns["created_at"]["nullable"] is False
            assert profile_columns["updated_at"]["nullable"] is False

            job_indexes = {index["name"] for index in inspector.get_indexes("jobs")}
            assert {"ix_jobs_applied", "ix_jobs_dismissed", "ix_jobs_user_score"} <= job_indexes
            assert {"ix_job_applied", "ix_job_dismissed", "ix_job_user_profile"}.isdisjoint(
                job_indexes
            )
            assert "ix_scraped_jobs_id" in {
                index["name"] for index in inspector.get_indexes("scraped_jobs")
            }
            assert any(
                foreign_key["constrained_columns"] == ["search_profile_id"]
                and foreign_key["referred_table"] == "search_profiles"
                for foreign_key in inspector.get_foreign_keys("jobs")
            )
            with engine.connect() as connection:
                assert connection.execute(
                    sa.text(
                        "SELECT hashed_password IS NOT NULL, created_at IS NOT NULL, "
                        "updated_at IS NOT NULL FROM users WHERE id = 1"
                    )
                ).one() == (1, 1, 1)
                assert connection.execute(
                    sa.text(
                        "SELECT created_at IS NOT NULL, updated_at IS NOT NULL "
                        "FROM jobs WHERE id = 1"
                    )
                ).one() == (1, 1)

            command.check(config)
        finally:
            engine.dispose()
