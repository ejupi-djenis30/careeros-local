"""extract scraped jobs

Revision ID: 7d76134d9a36
Revises: a1b2c3d4e5f6
Create Date: 2026-02-22 02:18:30.032780
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d76134d9a36'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create scraped_jobs table
    op.create_table('scraped_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('platform_job_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('company', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('external_url', sa.String(), nullable=False),
        sa.Column('application_url', sa.String(), nullable=True),
        sa.Column('application_email', sa.String(), nullable=True),
        sa.Column('workload', sa.String(), nullable=True),
        sa.Column('publication_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_metadata', sa.JSON(), nullable=True),
        sa.Column('source_query', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scraped_jobs_platform'), 'scraped_jobs', ['platform'], unique=False)
    op.create_index(op.f('ix_scraped_jobs_platform_job_id'), 'scraped_jobs', ['platform_job_id'], unique=False)
    op.create_index(op.f('ix_scraped_jobs_title'), 'scraped_jobs', ['title'], unique=False)
    op.create_index(op.f('ix_scraped_jobs_company'), 'scraped_jobs', ['company'], unique=False)
    op.create_index(op.f('ix_scraped_jobs_location'), 'scraped_jobs', ['location'], unique=False)
    op.create_index(op.f('ix_scraped_jobs_external_url'), 'scraped_jobs', ['external_url'], unique=False)

    # 2. Add scraped_job_id to jobs (nullable initially)
    op.add_column('jobs', sa.Column('scraped_job_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_jobs_scraped_job_id', 'jobs', 'scraped_jobs', ['scraped_job_id'], ['id'])

    # 3. Data migration block
    op.execute("""
        INSERT INTO scraped_jobs (
            platform, platform_job_id, title, company, description, location, 
            external_url, application_url, application_email, workload, 
            publication_date, raw_metadata, source_query, created_at, updated_at
        )
        SELECT DISTINCT ON (platform, platform_job_id)
            platform, platform_job_id, title, company, description, location, 
            external_url, application_url, application_email, workload, 
            publication_date, raw_metadata, source_query, created_at, COALESCE(updated_at, created_at)
        FROM jobs
        WHERE platform IS NOT NULL AND platform_job_id IS NOT NULL;
    """)

    op.execute("""
        INSERT INTO scraped_jobs (
            platform, platform_job_id, title, company, description, location, 
            external_url, application_url, application_email, workload, 
            publication_date, raw_metadata, source_query, created_at, updated_at
        )
        SELECT DISTINCT ON (external_url)
            COALESCE(platform, 'unknown'), 
            COALESCE(platform_job_id, external_url, id::text), 
            title, company, description, location, 
            external_url, application_url, application_email, workload, 
            publication_date, raw_metadata, source_query, created_at, COALESCE(updated_at, created_at)
        FROM jobs
        WHERE platform IS NULL OR platform_job_id IS NULL;
    """)

    # Link jobs
    op.execute("""
        UPDATE jobs
        SET scraped_job_id = scraped_jobs.id
        FROM scraped_jobs
        WHERE 
            COALESCE(jobs.platform, 'unknown') = scraped_jobs.platform 
            AND COALESCE(jobs.platform_job_id, jobs.external_url, jobs.id::text) = scraped_jobs.platform_job_id
    """)

    # 4. Make it non-nullable
    op.alter_column('jobs', 'scraped_job_id', existing_type=sa.Integer(), nullable=False)
    op.create_index(op.f('ix_jobs_scraped_job_id'), 'jobs', ['scraped_job_id'], unique=False)

    # 5. Drop old columns
    op.drop_index('ix_jobs_title', table_name='jobs')
    op.drop_index('ix_jobs_company', table_name='jobs')
    op.drop_index('ix_jobs_location', table_name='jobs')
    op.drop_index('ix_jobs_external_url', table_name='jobs')
    op.drop_index('ix_jobs_platform', table_name='jobs')
    op.drop_index('ix_jobs_platform_job_id', table_name='jobs')

    op.drop_column('jobs', 'title')
    op.drop_column('jobs', 'company')
    op.drop_column('jobs', 'description')
    op.drop_column('jobs', 'location')
    op.drop_column('jobs', 'external_url')
    op.drop_column('jobs', 'application_url')
    op.drop_column('jobs', 'application_email')
    op.drop_column('jobs', 'workload')
    op.drop_column('jobs', 'publication_date')
    op.drop_column('jobs', 'platform')
    op.drop_column('jobs', 'platform_job_id')
    op.drop_column('jobs', 'raw_metadata')
    op.drop_column('jobs', 'source_query')


def downgrade() -> None:
    pass
