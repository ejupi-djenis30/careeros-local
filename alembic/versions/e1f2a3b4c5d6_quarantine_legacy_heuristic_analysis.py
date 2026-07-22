"""Quarantine unverified matches and add durable analysis provenance.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-22
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ANALYSIS_FIELDS = (
    "affinity_score",
    "affinity_analysis",
    "worth_applying",
    "skill_match_score",
    "experience_match_score",
    "intent_match_score",
    "language_match_score",
    "location_match_score",
    "transferability_score",
    "qualification_gap_score",
    "analysis_structured",
    "red_flags",
)
APPLICATION_SNAPSHOT_SAFE_FIELDS = frozenset(
    {
        "title",
        "company",
        "description",
        "location",
        "external_url",
        "application_url",
        "application_email",
        "workload",
        "publication_date",
        "platform",
        "platform_job_id",
    }
)


def _decoded(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def _quarantined_application_snapshot(value: object) -> dict[str, object]:
    decoded = _decoded(value)
    source = decoded if isinstance(decoded, dict) else {}
    snapshot = {
        field: source[field] for field in APPLICATION_SNAPSHOT_SAFE_FIELDS if field in source
    }
    # Never retain the raw historical match under another key: downgrade must not be able to
    # resurrect prose or scores that predate receipt and evidence verification.
    snapshot["schema_version"] = 2
    snapshot["match"] = {
        "score": None,
        "analysis": None,
        "worth_applying": None,
        "receipt_verified": False,
        "quarantine_reason": "pre_v1_4_unverified_application_match",
    }
    return snapshot


def _quarantined_coach_metadata(value: object) -> dict[str, object]:
    decoded = _decoded(value)
    source = decoded if isinstance(decoded, dict) else {"legacy_value": decoded}
    return {
        "provenance": "quarantined",
        "quarantine_reason": "pre_v1_4_unverified_coach_output",
        "source_generation_metadata": source,
    }


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("source_query", sa.String()))
        batch_op.add_column(sa.Column("analysis_provenance", sa.String(length=40)))
        batch_op.add_column(sa.Column("analysis_model_id", sa.String(length=240)))
        batch_op.add_column(sa.Column("analysis_contract_version", sa.String(length=20)))
        batch_op.add_column(sa.Column("analysis_validated_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("analysis_execution_id", sa.String(length=36)))
        batch_op.add_column(sa.Column("analysis_output_fingerprint", sa.String(length=64)))
        batch_op.add_column(sa.Column("analysis_execution_row_index", sa.Integer()))
        batch_op.add_column(sa.Column("analysis_row_fingerprint", sa.String(length=64)))
        batch_op.add_column(sa.Column("analysis_input_fingerprint", sa.String(length=64)))
        batch_op.add_column(sa.Column("analysis_legacy_snapshot", sa.JSON()))
        batch_op.create_index("ix_jobs_analysis_execution_id", ["analysis_execution_id"])

    with op.batch_alter_table("ai_executions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "row_fingerprints",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )

        batch_op.add_column(
            sa.Column(
                "row_input_fingerprints",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )

    connection = op.get_bind()
    source_jobs = sa.table(
        "jobs",
        sa.column("user_id", sa.Integer()),
        sa.column("scraped_job_id", sa.Integer()),
        sa.column("source_query", sa.String()),
    )
    source_scraped_jobs = sa.table(
        "scraped_jobs",
        sa.column("id", sa.Integer()),
        sa.column("source_query", sa.String()),
    )
    # The historical field lived on a provider-global listing. It can only be attributed to
    # a user when that shared listing has never crossed a user boundary. Ambiguous values are
    # intentionally discarded instead of disclosing one user's query to another user.
    for row in connection.execute(
        sa.select(source_scraped_jobs.c.id, source_scraped_jobs.c.source_query).where(
            source_scraped_jobs.c.source_query.is_not(None)
        )
    ).mappings():
        user_ids = set(
            connection.execute(
                sa.select(source_jobs.c.user_id).where(source_jobs.c.scraped_job_id == row["id"])
            ).scalars()
        )
        if len(user_ids) == 1:
            connection.execute(
                source_jobs.update()
                .where(source_jobs.c.scraped_job_id == row["id"])
                .values(source_query=row["source_query"])
            )

    with op.batch_alter_table("scraped_jobs") as batch_op:
        batch_op.drop_column("source_query")

    coach_messages = sa.table(
        "coach_messages",
        sa.column("id", sa.String(length=36)),
        sa.column("role", sa.String(length=20)),
        sa.column("generation_metadata", sa.JSON()),
    )
    # Historical assistant prose predates claim-level grounding. Preserve it for audit and
    # portability, but mark it non-renderable until a fresh local-model reply is generated.
    for row in connection.execute(
        sa.select(coach_messages).where(coach_messages.c.role == "assistant")
    ).mappings():
        connection.execute(
            coach_messages.update()
            .where(coach_messages.c.id == row["id"])
            .values(generation_metadata=_quarantined_coach_metadata(row["generation_metadata"]))
        )

    jobs = sa.table(
        "jobs",
        sa.column("id", sa.Integer()),
        sa.column("affinity_score", sa.Float()),
        sa.column("affinity_analysis", sa.Text()),
        sa.column("worth_applying", sa.Boolean()),
        sa.column("skill_match_score", sa.Float()),
        sa.column("experience_match_score", sa.Float()),
        sa.column("intent_match_score", sa.Float()),
        sa.column("language_match_score", sa.Float()),
        sa.column("location_match_score", sa.Float()),
        sa.column("transferability_score", sa.Float()),
        sa.column("qualification_gap_score", sa.Float()),
        sa.column("analysis_structured", sa.JSON()),
        sa.column("red_flags", sa.JSON()),
        sa.column("analysis_legacy_snapshot", sa.JSON()),
    )
    # No row created before this migration can carry a model identity, contract version,
    # content-grounded citations and validation timestamp. Preserve the listing and all
    # user actions, but remove every pre-v1.4 analysis claim instead of guessing its trust.
    for row in connection.execute(sa.select(jobs)).mappings():
        has_analysis = bool(row["worth_applying"]) or any(
            row[field] is not None for field in ANALYSIS_FIELDS if field != "worth_applying"
        )
        if not has_analysis:
            continue
        preserved = {
            field: _decoded(row[field])
            for field in ANALYSIS_FIELDS
            if row[field] is not None or field == "worth_applying"
        }
        connection.execute(
            jobs.update()
            .where(jobs.c.id == row["id"])
            .values(
                affinity_score=None,
                affinity_analysis=None,
                worth_applying=False,
                skill_match_score=None,
                experience_match_score=None,
                intent_match_score=None,
                language_match_score=None,
                location_match_score=None,
                transferability_score=None,
                qualification_gap_score=None,
                analysis_structured=sa.null(),
                red_flags=sa.null(),
                analysis_legacy_snapshot={
                    "schema_version": "1.0",
                    "reason": "pre_v1_4_unverified",
                    "analysis": preserved,
                },
            )
        )

    applications = sa.table(
        "applications",
        sa.column("id", sa.String(length=36)),
        sa.column("job_snapshot", sa.JSON()),
    )
    for row in connection.execute(sa.select(applications)).mappings():
        connection.execute(
            applications.update()
            .where(applications.c.id == row["id"])
            .values(job_snapshot=_quarantined_application_snapshot(row["job_snapshot"]))
        )


def downgrade() -> None:
    jobs = sa.table(
        "jobs",
        sa.column("id", sa.Integer()),
        sa.column("scraped_job_id", sa.Integer()),
        sa.column("source_query", sa.String()),
        sa.column("affinity_score", sa.Float()),
        sa.column("affinity_analysis", sa.Text()),
        sa.column("worth_applying", sa.Boolean()),
        sa.column("skill_match_score", sa.Float()),
        sa.column("experience_match_score", sa.Float()),
        sa.column("intent_match_score", sa.Float()),
        sa.column("language_match_score", sa.Float()),
        sa.column("location_match_score", sa.Float()),
        sa.column("transferability_score", sa.Float()),
        sa.column("qualification_gap_score", sa.Float()),
        sa.column("analysis_structured", sa.JSON()),
        sa.column("red_flags", sa.JSON()),
        sa.column("analysis_legacy_snapshot", sa.JSON()),
    )
    connection = op.get_bind()
    rows = list(connection.execute(sa.select(jobs)).mappings())
    # The target schema has no provenance columns. Refuse the downgrade before changing
    # any row when a current analysis would otherwise survive as apparently trusted data.
    for row in rows:
        has_current_analysis = bool(row["worth_applying"]) or any(
            row[field] is not None for field in ANALYSIS_FIELDS if field != "worth_applying"
        )
        if has_current_analysis:
            raise RuntimeError(
                "Cannot downgrade while current validated analysis exists. Export the vault, "
                "clear current analysis, then retry the downgrade."
            )

    source_queries_by_scraped_id: dict[int, set[str | None]] = {}
    for row in rows:
        source_query = row["source_query"]
        source_queries_by_scraped_id.setdefault(row["scraped_job_id"], set()).add(source_query)
    conflicting_source_ids = sorted(
        scraped_job_id
        for scraped_job_id, source_queries in source_queries_by_scraped_id.items()
        if len(source_queries) > 1
    )
    if conflicting_source_ids:
        raise RuntimeError(
            "Cannot downgrade because the legacy shared scraped_jobs.source_query column "
            "cannot safely represent distinct per-user queries for scraped job(s): "
            + ", ".join(str(value) for value in conflicting_source_ids)
        )

    for row in rows:
        snapshot = _decoded(row["analysis_legacy_snapshot"])
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("analysis"), dict):
            continue
        preserved = {
            field: value
            for field, value in snapshot["analysis"].items()
            if field in ANALYSIS_FIELDS
        }
        connection.execute(jobs.update().where(jobs.c.id == row["id"]).values(**preserved))

    coach_messages = sa.table(
        "coach_messages",
        sa.column("id", sa.String(length=36)),
        sa.column("role", sa.String(length=20)),
        sa.column("generation_metadata", sa.JSON()),
    )
    for row in connection.execute(
        sa.select(coach_messages).where(coach_messages.c.role == "assistant")
    ).mappings():
        metadata = _decoded(row["generation_metadata"])
        if (
            isinstance(metadata, dict)
            and set(metadata)
            == {
                "provenance",
                "quarantine_reason",
                "source_generation_metadata",
            }
            and metadata.get("provenance") == "quarantined"
            and metadata.get("quarantine_reason") == "pre_v1_4_unverified_coach_output"
            and isinstance(metadata.get("source_generation_metadata"), dict)
        ):
            connection.execute(
                coach_messages.update()
                .where(coach_messages.c.id == row["id"])
                .values(generation_metadata=metadata["source_generation_metadata"])
            )

    # Application snapshot analysis is intentionally not restored. The prior schema had no
    # trustworthy receipt binding for the copied projection, so reviving it on downgrade would
    # silently turn quarantined claims back into application data.

    with op.batch_alter_table("scraped_jobs") as batch_op:
        batch_op.add_column(sa.Column("source_query", sa.String()))

    source_scraped_jobs = sa.table(
        "scraped_jobs",
        sa.column("id", sa.Integer()),
        sa.column("source_query", sa.String()),
    )
    for scraped_job_id, source_queries in source_queries_by_scraped_id.items():
        non_null_queries = {value for value in source_queries if value is not None}
        if non_null_queries:
            connection.execute(
                source_scraped_jobs.update()
                .where(source_scraped_jobs.c.id == scraped_job_id)
                .values(source_query=next(iter(non_null_queries)))
            )

    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_index("ix_jobs_analysis_execution_id")
        batch_op.drop_column("analysis_legacy_snapshot")
        batch_op.drop_column("analysis_input_fingerprint")
        batch_op.drop_column("analysis_row_fingerprint")
        batch_op.drop_column("analysis_execution_row_index")
        batch_op.drop_column("analysis_output_fingerprint")
        batch_op.drop_column("analysis_execution_id")
        batch_op.drop_column("analysis_validated_at")
        batch_op.drop_column("analysis_contract_version")
        batch_op.drop_column("analysis_model_id")
        batch_op.drop_column("analysis_provenance")
        batch_op.drop_column("source_query")

    with op.batch_alter_table("ai_executions") as batch_op:
        batch_op.drop_column("row_input_fingerprints")
        batch_op.drop_column("row_fingerprints")
