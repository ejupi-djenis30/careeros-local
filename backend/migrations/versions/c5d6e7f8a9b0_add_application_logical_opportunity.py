"""Add durable logical-opportunity identity to applications.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_APPLICATION_SCRAPED_JOB_FK = "fk_applications_scraped_job_id"
_APPLICATION_SCRAPED_JOB_INDEX = "ix_applications_scraped_job_id"
_APPLICATION_LOGICAL_OPPORTUNITY_UNIQUE = "uq_application_user_scraped_job"


def _backfill_logical_opportunities() -> None:
    applications = sa.table(
        "applications",
        sa.column("id", sa.String(length=36)),
        sa.column("user_id", sa.Integer()),
        sa.column("job_id", sa.Integer()),
        sa.column("scraped_job_id", sa.Integer()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    jobs = sa.table(
        "jobs",
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.Integer()),
        sa.column("scraped_job_id", sa.Integer()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            applications.c.id,
            applications.c.user_id,
            jobs.c.scraped_job_id,
        )
        .select_from(
            applications.join(
                jobs,
                sa.and_(
                    applications.c.job_id == jobs.c.id,
                    applications.c.user_id == jobs.c.user_id,
                ),
            )
        )
        .order_by(
            applications.c.user_id,
            jobs.c.scraped_job_id,
            sa.case((applications.c.updated_at.is_(None), 1), else_=0),
            applications.c.updated_at.desc(),
            applications.c.id.asc(),
        )
    ).mappings()

    assigned: set[tuple[int, int]] = set()
    for row in rows:
        logical_opportunity = (row["user_id"], row["scraped_job_id"])
        if logical_opportunity in assigned:
            continue
        connection.execute(
            applications.update()
            .where(applications.c.id == row["id"])
            .values(scraped_job_id=row["scraped_job_id"])
        )
        assigned.add(logical_opportunity)


def upgrade() -> None:
    with op.batch_alter_table("applications") as batch_op:
        batch_op.add_column(sa.Column("scraped_job_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            _APPLICATION_SCRAPED_JOB_FK,
            "scraped_jobs",
            ["scraped_job_id"],
            ["id"],
            ondelete="SET NULL",
        )

    _backfill_logical_opportunities()

    with op.batch_alter_table("applications") as batch_op:
        batch_op.create_index(
            _APPLICATION_SCRAPED_JOB_INDEX,
            ["scraped_job_id"],
            unique=False,
        )
        batch_op.create_unique_constraint(
            _APPLICATION_LOGICAL_OPPORTUNITY_UNIQUE,
            ["user_id", "scraped_job_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_constraint(
            _APPLICATION_LOGICAL_OPPORTUNITY_UNIQUE,
            type_="unique",
        )
        batch_op.drop_index(_APPLICATION_SCRAPED_JOB_INDEX)
        batch_op.drop_constraint(
            _APPLICATION_SCRAPED_JOB_FK,
            type_="foreignkey",
        )
        batch_op.drop_column("scraped_job_id")
