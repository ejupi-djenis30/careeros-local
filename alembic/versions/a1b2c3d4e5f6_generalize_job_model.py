"""generalize_job_model

Revision ID: a1b2c3d4e5f6
Revises: 7b2a37169931
Create Date: 2026-02-21 21:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '7b2a37169931'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update Jobs table
    # Rename url to external_url
    op.alter_column('jobs', 'url', new_column_name='external_url')
    
    # Add new columns
    op.add_column('jobs', sa.Column('application_url', sa.String(), nullable=True))
    op.add_column('jobs', sa.Column('platform', sa.String(), nullable=True))
    op.add_column('jobs', sa.Column('platform_job_id', sa.String(), nullable=True))
    op.add_column('jobs', sa.Column('raw_metadata', sa.JSON(), nullable=True))
    op.add_column('jobs', sa.Column('distance_km', sa.Float(), nullable=True))
    
    # Indices
    op.create_index(op.f('ix_jobs_external_url'), 'jobs', ['external_url'], unique=False)
    op.create_index(op.f('ix_jobs_platform'), 'jobs', ['platform'], unique=False)
    op.create_index(op.f('ix_jobs_platform_job_id'), 'jobs', ['platform_job_id'], unique=False)
    
    # Data migration: transfer jobroom_url to external_url if external_url is null
    # or just ensure jobroom_url data isn't lost. 
    # Since we are dropping jobroom_url, we should move its content to external_url if external_url is empty.
    op.execute("UPDATE jobs SET external_url = jobroom_url WHERE external_url IS NULL OR external_url = ''")
    
    # Drop jobroom_url
    op.drop_column('jobs', 'jobroom_url')
    
    # 2. Update Search Profiles table
    op.add_column('search_profiles', sa.Column('advanced_preferences', sa.JSON(), nullable=True))
    op.add_column('search_profiles', sa.Column('max_queries', sa.Integer(), nullable=True))
    op.add_column('search_profiles', sa.Column('is_history', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('search_profiles', sa.Column('is_stopped', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('search_profiles', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True))

    # 3. Update Users table (add updated_at if missing)
    op.add_column('users', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True))


def downgrade() -> None:
    # Reverse Search Profiles
    op.drop_column('search_profiles', 'updated_at')
    op.drop_column('search_profiles', 'is_stopped')
    op.drop_column('search_profiles', 'is_history')
    op.drop_column('search_profiles', 'max_queries')
    op.drop_column('search_profiles', 'advanced_preferences')
    
    # Reverse Users
    op.drop_column('users', 'updated_at')
    
    # Reverse Jobs
    op.add_column('jobs', sa.Column('jobroom_url', sa.String(), nullable=True))
    op.drop_index(op.f('ix_jobs_platform_job_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_platform'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_external_url'), table_name='jobs')
    op.drop_column('jobs', 'distance_km')
    op.drop_column('jobs', 'raw_metadata')
    op.drop_column('jobs', 'platform_job_id')
    op.drop_column('jobs', 'platform')
    op.drop_column('jobs', 'application_url')
    op.alter_column('jobs', 'external_url', new_column_name='url')
