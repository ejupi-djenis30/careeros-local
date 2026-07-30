"""Extract shared scraped jobs without losing existing SQLite data.

Revision ID: 7d76134d9a36
Revises: a1b2c3d4e5f6
Create Date: 2026-02-22 02:18:30.032780
"""

from typing import Any, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "7d76134d9a36"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCRAPED_INDEXES = (
    "ix_scraped_jobs_platform",
    "ix_scraped_jobs_platform_job_id",
    "ix_scraped_jobs_title",
    "ix_scraped_jobs_company",
    "ix_scraped_jobs_location",
    "ix_scraped_jobs_external_url",
)

_LEGACY_INDEXES = {
    "ix_jobs_url": "external_url",
    "ix_jobs_title": "title",
    "ix_jobs_company": "company",
    "ix_jobs_location": "location",
    "ix_jobs_external_url": "external_url",
    "ix_jobs_platform": "platform",
    "ix_jobs_platform_job_id": "platform_job_id",
}

_LEGACY_COLUMNS = (
    sa.Column("title", sa.String(), nullable=True),
    sa.Column("company", sa.String(), nullable=True),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("location", sa.String(), nullable=True),
    sa.Column("external_url", sa.String(), nullable=True),
    sa.Column("application_url", sa.String(), nullable=True),
    sa.Column("application_email", sa.String(), nullable=True),
    sa.Column("workload", sa.String(), nullable=True),
    sa.Column("publication_date", sa.DateTime(timezone=True), nullable=True),
    sa.Column("platform", sa.String(), nullable=True),
    sa.Column("platform_job_id", sa.String(), nullable=True),
    sa.Column("raw_metadata", sa.JSON(), nullable=True),
    sa.Column("source_query", sa.String(), nullable=True),
)


def _text(value: Any, fallback: str) -> str:
    normalized = str(value).strip() if value is not None else ""
    return normalized or fallback


def _canonical_identity(row: sa.RowMapping) -> tuple[str, str, str]:
    row_id = str(row["id"])
    platform = _text(row["platform"], "unknown")
    external_url = _text(row["external_url"], f"local://legacy-job/{row_id}")
    platform_job_id = _text(row["platform_job_id"], external_url or row_id)
    return platform, platform_job_id, external_url


def _backfill_scraped_jobs() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    jobs = sa.Table("jobs", metadata, autoload_with=bind)
    scraped_jobs = sa.Table("scraped_jobs", metadata, autoload_with=bind)
    identities: dict[tuple[str, str], int] = {}

    rows = bind.execute(sa.select(jobs).order_by(jobs.c.id)).mappings()
    for row in rows:
        platform, platform_job_id, external_url = _canonical_identity(row)
        identity = (platform, platform_job_id)
        scraped_job_id = identities.get(identity)
        if scraped_job_id is None:
            values: dict[str, Any] = {
                "platform": platform,
                "platform_job_id": platform_job_id,
                "title": _text(row["title"], "Untitled role"),
                "company": _text(row["company"], "Unknown company"),
                "description": row["description"],
                "location": row["location"],
                "external_url": external_url,
                "application_url": row["application_url"],
                "application_email": row["application_email"],
                "workload": row["workload"],
                "publication_date": row["publication_date"],
                "raw_metadata": row["raw_metadata"],
                "source_query": row["source_query"],
            }
            if row["created_at"] is not None:
                values["created_at"] = row["created_at"]
                values["updated_at"] = row["updated_at"] or row["created_at"]
            result = bind.execute(scraped_jobs.insert().values(**values))
            scraped_job_id = int(result.inserted_primary_key[0])
            identities[identity] = scraped_job_id
        bind.execute(
            jobs.update().where(jobs.c.id == row["id"]).values(scraped_job_id=scraped_job_id)
        )


def _restore_legacy_job_columns() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    jobs = sa.Table("jobs", metadata, autoload_with=bind)
    scraped_jobs = sa.Table("scraped_jobs", metadata, autoload_with=bind)
    fields = [column.name for column in _LEGACY_COLUMNS]
    query = sa.select(
        jobs.c.id.label("job_id"),
        *(scraped_jobs.c[name].label(name) for name in fields),
    ).select_from(jobs.join(scraped_jobs, jobs.c.scraped_job_id == scraped_jobs.c.id))
    for row in bind.execute(query).mappings():
        bind.execute(
            jobs.update()
            .where(jobs.c.id == row["job_id"])
            .values(**{name: row[name] for name in fields})
        )


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    op.create_table(
        "scraped_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("platform_job_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("external_url", sa.String(), nullable=False),
        sa.Column("application_url", sa.String(), nullable=True),
        sa.Column("application_email", sa.String(), nullable=True),
        sa.Column("workload", sa.String(), nullable=True),
        sa.Column("publication_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_metadata", sa.JSON(), nullable=True),
        sa.Column("source_query", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, column in (
        ("ix_scraped_jobs_platform", "platform"),
        ("ix_scraped_jobs_platform_job_id", "platform_job_id"),
        ("ix_scraped_jobs_title", "title"),
        ("ix_scraped_jobs_company", "company"),
        ("ix_scraped_jobs_location", "location"),
        ("ix_scraped_jobs_external_url", "external_url"),
    ):
        op.create_index(name, "scraped_jobs", [column], unique=False)

    op.add_column("jobs", sa.Column("scraped_job_id", sa.Integer(), nullable=True))
    if not is_sqlite:
        op.create_foreign_key(
            "fk_jobs_scraped_job_id",
            "jobs",
            "scraped_jobs",
            ["scraped_job_id"],
            ["id"],
            ondelete="CASCADE",
        )

    _backfill_scraped_jobs()

    for index_name in _LEGACY_INDEXES:
        op.drop_index(index_name, table_name="jobs")

    old_column_names = [column.name for column in _LEGACY_COLUMNS]
    if is_sqlite:
        with op.batch_alter_table("jobs", recreate="always") as batch_op:
            batch_op.alter_column("scraped_job_id", existing_type=sa.Integer(), nullable=False)
            batch_op.create_foreign_key(
                "fk_jobs_scraped_job_id",
                "scraped_jobs",
                ["scraped_job_id"],
                ["id"],
                ondelete="CASCADE",
            )
            for column_name in old_column_names:
                batch_op.drop_column(column_name)
    else:
        op.alter_column("jobs", "scraped_job_id", existing_type=sa.Integer(), nullable=False)
        for column_name in old_column_names:
            op.drop_column("jobs", column_name)

    op.create_index("ix_jobs_scraped_job_id", "jobs", ["scraped_job_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    for column in _LEGACY_COLUMNS:
        op.add_column(
            "jobs",
            sa.Column(column.name, column.type, nullable=True),
        )
    _restore_legacy_job_columns()

    op.drop_index("ix_jobs_scraped_job_id", table_name="jobs")
    if is_sqlite:
        foreign_keys = sa.inspect(bind).get_foreign_keys("jobs")
        has_scraped_fk = any(
            foreign_key.get("constrained_columns") == ["scraped_job_id"]
            for foreign_key in foreign_keys
        )
        with op.batch_alter_table("jobs", recreate="always") as batch_op:
            if has_scraped_fk:
                batch_op.drop_constraint("fk_jobs_scraped_job_id", type_="foreignkey")
            batch_op.drop_column("scraped_job_id")
    else:
        op.drop_constraint("fk_jobs_scraped_job_id", "jobs", type_="foreignkey")
        op.drop_column("jobs", "scraped_job_id")

    for index_name, column_name in _LEGACY_INDEXES.items():
        op.create_index(index_name, "jobs", [column_name], unique=False)
    for index_name in reversed(_SCRAPED_INDEXES):
        op.drop_index(index_name, table_name="scraped_jobs")
    op.drop_table("scraped_jobs")
