import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from backend.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_scraped_job_migration_preserves_sqlite_rows_and_round_trips(monkeypatch):
    temporary = TemporaryDirectory()
    database_path = Path(temporary.name) / "migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    config = _alembic_config(database_url)

    command.upgrade(config, "a1b2c3d4e5f6")
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, username, hashed_password) "
                    "VALUES (1, 'migration-user', 'local-hash')"
                )
            )
            connection.execute(
                sa.text(
                    """
                        INSERT INTO jobs (
                            id, user_id, title, company, description, external_url,
                            platform, platform_job_id, affinity_score
                        ) VALUES
                            (1, 1, 'Engineer', 'Local Co', 'First',
                             'https://jobs.example/1', 'fixture', 'job-1', 90),
                            (2, 1, 'Engineer duplicate', 'Local Co', 'Second',
                             'https://jobs.example/duplicate', 'fixture', 'job-1', 80),
                            (3, 1, NULL, NULL, 'Legacy nullable row',
                             NULL, NULL, NULL, 70)
                        """
                )
            )

        command.upgrade(config, "7d76134d9a36")
        with engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT count(*) FROM jobs")) == 3
            assert connection.scalar(sa.text("SELECT count(*) FROM scraped_jobs")) == 2
            assert (
                connection.scalar(sa.text("SELECT count(*) FROM jobs WHERE scraped_job_id IS NULL"))
                == 0
            )
            fallback = connection.execute(
                sa.text(
                    "SELECT title, company, external_url FROM scraped_jobs "
                    "WHERE platform = 'unknown'"
                )
            ).one()
            assert fallback == ("Untitled role", "Unknown company", "local://legacy-job/3")
            foreign_keys = connection.execute(sa.text("PRAGMA foreign_key_list(jobs)")).all()
            assert any(row[2] == "scraped_jobs" for row in foreign_keys)

        command.downgrade(config, "a1b2c3d4e5f6")
        inspector = sa.inspect(engine)
        assert "scraped_jobs" not in inspector.get_table_names()
        assert "external_url" in {column["name"] for column in inspector.get_columns("jobs")}
        with engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT count(*) FROM jobs")) == 3
            restored = connection.execute(
                sa.text("SELECT title, company, external_url FROM jobs WHERE id = 3")
            ).one()
            assert restored == (
                "Untitled role",
                "Unknown company",
                "local://legacy-job/3",
            )

        command.upgrade(config, "7d76134d9a36")
        with engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT count(*) FROM jobs")) == 3
            assert connection.scalar(sa.text("SELECT count(*) FROM scraped_jobs")) == 2
    finally:
        engine.dispose()
        temporary.cleanup()


def test_resume_schema_migrates_to_head_and_round_trips(monkeypatch):
    temporary = TemporaryDirectory()
    database_path = Path(temporary.name) / "head.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    config = _alembic_config(database_url)

    command.upgrade(config, "head")
    engine = sa.create_engine(database_url)
    try:
        expected = {"resume_drafts", "resume_versions", "resume_artifacts"}
        assert expected <= set(sa.inspect(engine).get_table_names())
        command.downgrade(config, "s9t0u1v2w3x4")
        assert expected.isdisjoint(sa.inspect(engine).get_table_names())
        command.upgrade(config, "head")
        assert expected <= set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()
        temporary.cleanup()


def test_application_next_action_projection_migration_round_trips(monkeypatch):
    temporary = TemporaryDirectory()
    database_path = Path(temporary.name) / "application-next-action.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    config = _alembic_config(database_url)

    command.upgrade(config, "c9d0e1f2a3b4")
    engine = sa.create_engine(database_url)
    try:
        application_id = "10000000-0000-4000-8000-000000000001"
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, username, hashed_password) "
                    "VALUES (9001, 'projection-migration', 'test-only')"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO applications "
                    "(id, user_id, revision, current_stage, job_snapshot, created_at, updated_at) "
                    "VALUES (:id, 9001, 7, 'interview', :snapshot, :created_at, :updated_at)"
                ),
                {
                    "id": application_id,
                    "snapshot": json.dumps(
                        {
                            "title": "Platform Engineer",
                            "company": "Local Systems",
                            "location": "Zurich",
                        }
                    ),
                    "created_at": "2026-07-20 07:00:00",
                    "updated_at": "2026-07-21 08:00:00",
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO application_events "
                    "(id, application_id, event_type, stage, occurred_at, payload, created_at) "
                    "VALUES (:id, :application_id, 'stage', 'interview', :occurred_at, '{}', :created_at)"
                ),
                {
                    "id": "10000000-0000-4000-8000-000000000002",
                    "application_id": application_id,
                    "occurred_at": "2026-07-22 09:30:00",
                    "created_at": "2026-07-22 09:30:00",
                },
            )
        before = {column["name"] for column in sa.inspect(engine).get_columns("applications")}
        assert "next_action_task_id" not in before
        command.upgrade(config, "d0e1f2a3b4c5")
        inspector = sa.inspect(engine)
        after = {column["name"] for column in inspector.get_columns("applications")}
        assert {
            "job_title",
            "job_company",
            "job_location",
            "latest_event_at",
            "next_action_task_id",
            "next_action_title",
            "next_action_at",
            "next_action_priority",
        } <= after
        assert "ix_applications_user_stage_next_action" in {
            index["name"] for index in inspector.get_indexes("applications")
        }
        with engine.connect() as connection:
            projected = (
                connection.execute(
                    sa.text(
                        "SELECT revision, current_stage, job_snapshot, job_title, job_company, "
                        "job_location, latest_event_at FROM applications WHERE id = :id"
                    ),
                    {"id": application_id},
                )
                .mappings()
                .one()
            )
        assert projected["revision"] == 7
        assert projected["current_stage"] == "interview"
        assert json.loads(projected["job_snapshot"])["title"] == "Platform Engineer"
        assert projected["job_title"] == "Platform Engineer"
        assert projected["job_company"] == "Local Systems"
        assert projected["job_location"] == "Zurich"
        assert str(projected["latest_event_at"]).startswith("2026-07-22 09:30:00")
        command.downgrade(config, "c9d0e1f2a3b4")
        downgraded = {column["name"] for column in sa.inspect(engine).get_columns("applications")}
        assert "next_action_task_id" not in downgraded
        assert "job_title" not in downgraded
        command.upgrade(config, "head")
        assert "next_action_task_id" in {
            column["name"] for column in sa.inspect(engine).get_columns("applications")
        }
        assert "job_title" in {
            column["name"] for column in sa.inspect(engine).get_columns("applications")
        }
        with engine.connect() as connection:
            preserved = (
                connection.execute(
                    sa.text(
                        "SELECT revision, current_stage, job_title, latest_event_at "
                        "FROM applications WHERE id = :id"
                    ),
                    {"id": application_id},
                )
                .mappings()
                .one()
            )
        assert preserved["revision"] == 7
        assert preserved["current_stage"] == "interview"
        assert preserved["job_title"] == "Platform Engineer"
        assert str(preserved["latest_event_at"]).startswith("2026-07-22 09:30:00")
    finally:
        engine.dispose()
        temporary.cleanup()


def test_legacy_heuristic_analysis_is_quarantined_and_not_restored(monkeypatch):
    temporary = TemporaryDirectory()
    database_path = Path(temporary.name) / "analysis-provenance.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    config = _alembic_config(database_url)

    command.upgrade(config, "d0e1f2a3b4c5")
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, username, hashed_password) "
                    "VALUES (9101, 'analysis-migration', 'test-only'), "
                    "(9102, 'analysis-migration-other', 'test-only')"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO candidate_profiles "
                    "(id, user_id, revision, display_name, headline, summary, location, "
                    "work_authorization, preferences) VALUES "
                    "('91000000-0000-4000-8000-000000000001', 9101, 1, 'Legacy', '', '', "
                    "'{}', '[]', '{}')"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO coach_conversations (id, profile_id, title) VALUES "
                    "('91000000-0000-4000-8000-000000000002', "
                    "'91000000-0000-4000-8000-000000000001', 'Legacy coach')"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO coach_messages "
                    "(id, conversation_id, role, content, cited_fact_ids, cited_job_ids, "
                    "model_id, generation_metadata, created_at) VALUES "
                    "('91000000-0000-4000-8000-000000000003', "
                    "'91000000-0000-4000-8000-000000000002', 'user', 'Question', '[]', "
                    "'[]', NULL, '{}', '2026-07-22 00:00:00'), "
                    "('91000000-0000-4000-8000-000000000004', "
                    "'91000000-0000-4000-8000-000000000002', 'assistant', "
                    "'Unattested legacy advice', '[]', '[]', 'legacy-model', '{}', "
                    "'2026-07-22 00:00:01')"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO scraped_jobs "
                    "(id, platform, platform_job_id, title, company, external_url, "
                    "source_query) VALUES "
                    "(9201, 'fixture', 'legacy', 'Legacy role', 'Local Co', "
                    "'https://jobs.example/legacy', 'private legacy query'), "
                    "(9202, 'fixture', 'model', 'Model role', 'Local Co', "
                    "'https://jobs.example/model', 'private model query')"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO jobs "
                    "(id, user_id, scraped_job_id, affinity_score, affinity_analysis, "
                    "worth_applying, skill_match_score, analysis_structured, red_flags, applied, "
                    "created_at, updated_at) "
                    "VALUES "
                    "(9301, 9101, 9201, 88, 'Heuristic text', 1, 90, :legacy, '[\"flag\"]', 1, "
                    "'2026-07-22 00:00:00', '2026-07-22 00:00:00'), "
                    "(9302, 9101, 9202, 79, 'Model text', 1, 82, :model, '[]', 0, "
                    "'2026-07-22 00:00:00', '2026-07-22 00:00:00'), "
                    "(9303, 9102, 9201, NULL, NULL, 0, NULL, NULL, NULL, 0, "
                    "'2026-07-22 00:00:00', '2026-07-22 00:00:00')"
                ),
                {
                    "legacy": json.dumps({"mode": "deterministic_local", "verdict": "strong"}),
                    "model": json.dumps({"verdict": "supported", "evidence_citations": []}),
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO applications "
                    "(id, user_id, job_id, revision, current_stage, job_snapshot, job_title, "
                    "job_company, latest_event_at, created_at, updated_at) VALUES "
                    "('91000000-0000-4000-8000-000000000005', 9101, 9301, 1, 'saved', "
                    ":snapshot, 'Legacy role', 'Local Co', '2026-07-22 00:00:00', "
                    "'2026-07-22 00:00:00', '2026-07-22 00:00:00')"
                ),
                {
                    "snapshot": json.dumps(
                        {
                            "schema_version": 1,
                            "title": "Legacy role",
                            "company": "Local Co",
                            "affinity_analysis": "Legacy top-level snapshot claim",
                            "raw_metadata": {"analysis": "Legacy nested metadata claim"},
                            "match": {
                                "score": 99,
                                "analysis": "Legacy embedded snapshot claim",
                                "worth_applying": True,
                            },
                        }
                    )
                },
            )

        command.upgrade(config, "head")
        columns = {column["name"] for column in sa.inspect(engine).get_columns("jobs")}
        assert {
            "analysis_provenance",
            "analysis_model_id",
            "analysis_contract_version",
            "analysis_validated_at",
            "analysis_legacy_snapshot",
            "source_query",
        } <= columns
        assert "source_query" not in {
            column["name"] for column in sa.inspect(engine).get_columns("scraped_jobs")
        }
        with engine.connect() as connection:
            legacy = connection.execute(
                sa.text(
                    "SELECT affinity_score, affinity_analysis, worth_applying, "
                    "skill_match_score, analysis_structured, red_flags, applied "
                    "FROM jobs WHERE id = 9301"
                )
            ).one()
            model = connection.execute(
                sa.text(
                    "SELECT affinity_score, affinity_analysis, worth_applying, "
                    "analysis_structured FROM jobs WHERE id = 9302"
                )
            ).one()
            legacy_snapshot = connection.scalar(
                sa.text("SELECT analysis_legacy_snapshot FROM jobs WHERE id = 9301")
            )
            model_snapshot = connection.scalar(
                sa.text("SELECT analysis_legacy_snapshot FROM jobs WHERE id = 9302")
            )
            application_snapshot = connection.scalar(
                sa.text(
                    "SELECT job_snapshot FROM applications "
                    "WHERE id = '91000000-0000-4000-8000-000000000005'"
                )
            )
            migrated_source_queries = connection.execute(
                sa.text("SELECT id, source_query FROM jobs ORDER BY id")
            ).all()
            migrated_assistant = connection.execute(
                sa.text(
                    "SELECT content, generation_metadata FROM coach_messages "
                    "WHERE role = 'assistant'"
                )
            ).one()
        assert legacy == (None, None, 0, None, None, None, 1)
        assert model == (None, None, 0, None)
        assert json.loads(legacy_snapshot)["analysis"]["affinity_analysis"] == "Heuristic text"
        assert json.loads(legacy_snapshot)["analysis"]["worth_applying"] is True
        assert json.loads(model_snapshot)["analysis"]["affinity_analysis"] == "Model text"
        migrated_application_snapshot = json.loads(application_snapshot)
        assert migrated_application_snapshot["match"] == {
            "score": None,
            "analysis": None,
            "worth_applying": None,
            "receipt_verified": False,
            "quarantine_reason": "pre_v1_4_unverified_application_match",
        }
        assert "affinity_analysis" not in migrated_application_snapshot
        assert "Legacy embedded snapshot claim" not in application_snapshot
        assert "Legacy nested metadata claim" not in application_snapshot
        assert migrated_source_queries == [
            (9301, None),
            (9302, "private model query"),
            (9303, None),
        ]
        assert migrated_assistant[0] == "Unattested legacy advice"
        assert json.loads(migrated_assistant[1]) == {
            "provenance": "quarantined",
            "quarantine_reason": "pre_v1_4_unverified_coach_output",
            "source_generation_metadata": {},
        }
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT count(*) FROM coach_messages WHERE role = 'assistant'")
                )
                == 1
            )
            assert (
                connection.scalar(
                    sa.text("SELECT count(*) FROM coach_messages WHERE role = 'user'")
                )
                == 1
            )

        command.downgrade(config, "d0e1f2a3b4c5")
        assert "analysis_provenance" not in {
            column["name"] for column in sa.inspect(engine).get_columns("jobs")
        }
        assert "source_query" not in {
            column["name"] for column in sa.inspect(engine).get_columns("jobs")
        }
        assert "source_query" in {
            column["name"] for column in sa.inspect(engine).get_columns("scraped_jobs")
        }
        with engine.connect() as connection:
            restored_legacy = connection.execute(
                sa.text(
                    "SELECT affinity_score, affinity_analysis, worth_applying, applied "
                    "FROM jobs WHERE id = 9301"
                )
            ).one()
            restored_model = connection.execute(
                sa.text(
                    "SELECT affinity_score, affinity_analysis, worth_applying "
                    "FROM jobs WHERE id = 9302"
                )
            ).one()
            downgraded_application_snapshot = connection.scalar(
                sa.text(
                    "SELECT job_snapshot FROM applications "
                    "WHERE id = '91000000-0000-4000-8000-000000000005'"
                )
            )
            downgraded_source_queries = connection.execute(
                sa.text("SELECT id, source_query FROM scraped_jobs ORDER BY id")
            ).all()
            downgraded_assistant = connection.execute(
                sa.text(
                    "SELECT content, generation_metadata FROM coach_messages "
                    "WHERE role = 'assistant'"
                )
            ).one()
        assert restored_legacy == (88.0, "Heuristic text", 1, 1)
        assert restored_model == (79.0, "Model text", 1)
        assert json.loads(downgraded_application_snapshot)["match"] == {
            "score": None,
            "analysis": None,
            "worth_applying": None,
            "receipt_verified": False,
            "quarantine_reason": "pre_v1_4_unverified_application_match",
        }
        assert "Legacy embedded snapshot claim" not in downgraded_application_snapshot
        assert "Legacy nested metadata claim" not in downgraded_application_snapshot
        assert downgraded_source_queries == [
            (9201, None),
            (9202, "private model query"),
        ]
        assert downgraded_assistant[0] == "Unattested legacy advice"
        assert json.loads(downgraded_assistant[1]) == {}
        command.upgrade(config, "head")
        with engine.begin() as connection:
            connection.execute(
                sa.text("UPDATE jobs SET source_query = 'private current query' WHERE id = 9301")
            )
        with pytest.raises(RuntimeError, match="distinct per-user queries"):
            command.downgrade(config, "d0e1f2a3b4c5")
        assert "source_query" in {
            column["name"] for column in sa.inspect(engine).get_columns("jobs")
        }
        with engine.begin() as connection:
            connection.execute(sa.text("UPDATE jobs SET source_query = NULL WHERE id = 9301"))
            connection.execute(
                sa.text(
                    "UPDATE jobs SET analysis_legacy_snapshot = NULL, affinity_score = 100, "
                    "analysis_provenance = 'local_model_validated' WHERE id = 9301"
                )
            )
        with pytest.raises(RuntimeError, match="current validated analysis"):
            command.downgrade(config, "d0e1f2a3b4c5")
        assert "analysis_provenance" in {
            column["name"] for column in sa.inspect(engine).get_columns("jobs")
        }
    finally:
        engine.dispose()
        temporary.cleanup()
