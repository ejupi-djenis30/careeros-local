"""Add user feedback tracking columns and user preference signals

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-03-28 00:00:00.000000

Phase 2: User Feedback Loop
  jobs:
    - viewed_at        (DateTime) — first time user opened analysis panel
    - dismissed        (Boolean)  — user explicitly not-interested
    - dismissed_at     (DateTime) — timestamp of dismissal
    - feedback_signal  (String)   — optional dismissal reason
  users:
    - preference_signals    (JSON)     — aggregated behavioural signals
    - preference_updated_at (DateTime) — when signals were last recomputed
"""
import sqlalchemy as sa
from alembic import op

revision = 'n4o5p6q7r8s9'
down_revision = 'm3n4o5p6q7r8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── jobs table ────────────────────────────────────────────────────────────
    op.add_column('jobs', sa.Column('viewed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('jobs', sa.Column('dismissed', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('jobs', sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('jobs', sa.Column('feedback_signal', sa.String(), nullable=True))
    op.create_index('ix_job_dismissed', 'jobs', ['dismissed'])

    # ── users table ───────────────────────────────────────────────────────────
    op.add_column('users', sa.Column('preference_signals', sa.JSON(), nullable=True))
    op.add_column('users', sa.Column('preference_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'preference_updated_at')
    op.drop_column('users', 'preference_signals')

    op.drop_index('ix_job_dismissed', table_name='jobs')
    op.drop_column('jobs', 'feedback_signal')
    op.drop_column('jobs', 'dismissed_at')
    op.drop_column('jobs', 'dismissed')
    op.drop_column('jobs', 'viewed_at')
