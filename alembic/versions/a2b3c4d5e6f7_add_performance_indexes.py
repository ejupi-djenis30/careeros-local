"""Add performance indexes for common query patterns

Revision ID: a2b3c4d5e6f7
Revises: f6a7b8c9d0e1
Create Date: 2026-03-26 00:00:00.000000

Adds:
  - ix_job_user_profile: composite index on jobs(user_id, search_profile_id)
  - ix_job_applied: index on jobs(applied)
  - ix_search_profile_user_schedule: composite index on search_profiles(user_id, schedule_enabled)
"""
from typing import Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('ix_job_user_profile', 'jobs', ['user_id', 'search_profile_id'])
    op.create_index('ix_job_applied', 'jobs', ['applied'])
    op.create_index('ix_search_profile_user_schedule', 'search_profiles', ['user_id', 'schedule_enabled'])


def downgrade() -> None:
    op.drop_index('ix_search_profile_user_schedule', table_name='search_profiles')
    op.drop_index('ix_job_applied', table_name='jobs')
    op.drop_index('ix_job_user_profile', table_name='jobs')
