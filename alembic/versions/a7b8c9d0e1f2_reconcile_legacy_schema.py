"""Reconcile legacy tables with the production ORM schema.

Revision ID: a7b8c9d0e1f2
Revises: z6a7b8c9d0e1
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "z6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UNUSABLE_PASSWORD = "!local-password-required!"


def _index_names(table_name: str) -> set[str]:
    return {
        str(index["name"])
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name")
    }


def _drop_index_if_present(table_name: str, index_name: str) -> None:
    if index_name in _index_names(table_name):
        op.drop_index(index_name, table_name=table_name)


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    if index_name not in _index_names(table_name):
        op.create_index(index_name, table_name, columns, unique=False)


def _backfill_required_values() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    users = sa.Table("users", metadata, autoload_with=bind)
    jobs = sa.Table("jobs", metadata, autoload_with=bind)
    profiles = sa.Table("search_profiles", metadata, autoload_with=bind)
    now = sa.func.current_timestamp()

    bind.execute(
        users.update()
        .where(users.c.hashed_password.is_(None))
        .values(hashed_password=_UNUSABLE_PASSWORD)
    )
    for table in (users, jobs, profiles):
        bind.execute(table.update().where(table.c.created_at.is_(None)).values(created_at=now))
        bind.execute(
            table.update()
            .where(table.c.updated_at.is_(None))
            .values(updated_at=sa.func.coalesce(table.c.created_at, now))
        )


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    recreate = "always" if is_sqlite else "auto"
    has_profile_fk = any(
        foreign_key.get("constrained_columns") == ["search_profile_id"]
        and foreign_key.get("referred_table") == "search_profiles"
        for foreign_key in sa.inspect(bind).get_foreign_keys("jobs")
    )

    _backfill_required_values()

    with op.batch_alter_table("users", recreate=recreate) as batch_op:
        batch_op.alter_column(
            "hashed_password", existing_type=sa.String(), existing_nullable=True, nullable=False
        )
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
            nullable=False,
        )

    with op.batch_alter_table("search_profiles", recreate=recreate) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
            nullable=False,
        )

    with op.batch_alter_table("jobs", recreate=recreate) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
            nullable=False,
        )
        if not has_profile_fk:
            batch_op.create_foreign_key(
                "fk_jobs_search_profile_id",
                "search_profiles",
                ["search_profile_id"],
                ["id"],
            )

    for legacy_name in ("ix_job_applied", "ix_job_dismissed", "ix_job_user_profile"):
        _drop_index_if_present("jobs", legacy_name)
    _create_index_if_missing("jobs", "ix_jobs_applied", ["applied"])
    _create_index_if_missing("jobs", "ix_jobs_dismissed", ["dismissed"])
    _create_index_if_missing("jobs", "ix_jobs_user_profile", ["user_id", "search_profile_id"])
    _create_index_if_missing("jobs", "ix_jobs_user_score", ["user_id", "affinity_score"])
    _create_index_if_missing("scraped_jobs", "ix_scraped_jobs_id", ["id"])
    _create_index_if_missing(
        "scraped_jobs",
        "ix_scraped_jobs_domain_seniority_role",
        ["normalized_domain", "normalized_seniority", "normalized_role_type"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    recreate = "always" if is_sqlite else "auto"

    _drop_index_if_present("scraped_jobs", "ix_scraped_jobs_id")
    _drop_index_if_present("jobs", "ix_jobs_applied")
    _drop_index_if_present("jobs", "ix_jobs_dismissed")
    _create_index_if_missing("jobs", "ix_job_applied", ["applied"])
    _create_index_if_missing("jobs", "ix_job_dismissed", ["dismissed"])
    _create_index_if_missing("jobs", "ix_job_user_profile", ["user_id", "search_profile_id"])

    with op.batch_alter_table("jobs", recreate=recreate) as batch_op:
        if is_sqlite:
            batch_op.drop_constraint("fk_jobs_search_profile_id", type_="foreignkey")
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            nullable=True,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            nullable=True,
        )

    with op.batch_alter_table("search_profiles", recreate=recreate) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            nullable=True,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            nullable=True,
        )

    with op.batch_alter_table("users", recreate=recreate) as batch_op:
        batch_op.alter_column(
            "hashed_password", existing_type=sa.String(), existing_nullable=False, nullable=True
        )
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            nullable=True,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            nullable=True,
        )

    users = sa.Table("users", sa.MetaData(), autoload_with=bind)
    bind.execute(
        users.update()
        .where(users.c.hashed_password == _UNUSABLE_PASSWORD)
        .values(hashed_password=None)
    )
