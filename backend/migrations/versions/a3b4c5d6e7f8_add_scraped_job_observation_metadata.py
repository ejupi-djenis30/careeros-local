"""Add durable observation metadata to the shared job catalog.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scraped_jobs") as batch_op:
        batch_op.add_column(sa.Column("first_seen_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("last_changed_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("content_revision", sa.Integer()))

    scraped_jobs = sa.table(
        "scraped_jobs",
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("first_seen_at", sa.DateTime(timezone=True)),
        sa.column("last_seen_at", sa.DateTime(timezone=True)),
        sa.column("last_changed_at", sa.DateTime(timezone=True)),
        sa.column("content_revision", sa.Integer()),
    )
    first_known_observation = sa.func.coalesce(
        scraped_jobs.c.created_at,
        sa.func.current_timestamp(),
    )
    op.get_bind().execute(
        scraped_jobs.update().values(
            first_seen_at=first_known_observation,
            last_seen_at=first_known_observation,
            last_changed_at=first_known_observation,
            content_revision=1,
        )
    )

    with op.batch_alter_table("scraped_jobs") as batch_op:
        batch_op.alter_column(
            "first_seen_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        batch_op.alter_column(
            "last_seen_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        batch_op.alter_column(
            "last_changed_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        batch_op.alter_column(
            "content_revision",
            existing_type=sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        )
        batch_op.create_index(
            "ix_scraped_jobs_last_seen_at",
            ["last_seen_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("scraped_jobs") as batch_op:
        batch_op.drop_index("ix_scraped_jobs_last_seen_at")
        batch_op.drop_column("content_revision")
        batch_op.drop_column("last_changed_at")
        batch_op.drop_column("last_seen_at")
        batch_op.drop_column("first_seen_at")
