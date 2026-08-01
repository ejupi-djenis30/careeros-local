"""Add durable per-user vault maintenance state.

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-07-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: str | Sequence[str] | None = "f8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "vault_lifecycle_state",
                sa.String(length=24),
                server_default="ready",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "vault_maintenance_fingerprint",
                sa.String(length=64),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "ck_user_vault_lifecycle_state",
            "vault_lifecycle_state IN "
            "('ready', 'reset_pending', 'restore_pending', 'erasure_pending')",
        )
        batch_op.create_check_constraint(
            "ck_user_vault_maintenance_fingerprint",
            "(vault_lifecycle_state = 'restore_pending' "
            "AND vault_maintenance_fingerprint IS NOT NULL) OR "
            "(vault_lifecycle_state != 'restore_pending' "
            "AND vault_maintenance_fingerprint IS NULL)",
        )
        batch_op.create_check_constraint(
            "ck_user_vault_maintenance_fingerprint_shape",
            "vault_maintenance_fingerprint IS NULL OR "
            "(length(vault_maintenance_fingerprint) = 64 "
            "AND vault_maintenance_fingerprint = lower(vault_maintenance_fingerprint) "
            "AND vault_maintenance_fingerprint NOT GLOB '*[^0-9a-f]*')",
        )
        batch_op.create_index(
            "ix_users_vault_lifecycle_state",
            ["vault_lifecycle_state"],
            unique=False,
        )


def downgrade() -> None:
    pending = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM users WHERE vault_lifecycle_state != 'ready'")
    )
    if pending:
        raise RuntimeError(
            "Cannot downgrade while vault maintenance is pending; complete cleanup first"
        )
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_vault_lifecycle_state")
        batch_op.drop_constraint("ck_user_vault_maintenance_fingerprint_shape", type_="check")
        batch_op.drop_constraint("ck_user_vault_maintenance_fingerprint", type_="check")
        batch_op.drop_constraint("ck_user_vault_lifecycle_state", type_="check")
        batch_op.drop_column("vault_maintenance_fingerprint")
        batch_op.drop_column("vault_lifecycle_state")
