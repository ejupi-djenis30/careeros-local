"""add composite indexes for common filter combinations

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'j0k1l2m3n4o5'
down_revision = 'i9j0k1l2m3n4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Composite index for the most common scraped_jobs filter combination
    # (domain + seniority + role_type) used during normalization-based filtering.
    op.create_index(
        'ix_scraped_jobs_domain_seniority_role',
        'scraped_jobs',
        ['normalized_domain', 'normalized_seniority', 'normalized_role_type'],
        unique=False
    )

    # Composite index for jobs table filtered by user + profile (common query pattern)
    op.create_index(
        'ix_jobs_user_profile',
        'jobs',
        ['user_id', 'search_profile_id'],
        unique=False
    )

    # Composite index for jobs sorted by score (most common sort in job listing)
    op.create_index(
        'ix_jobs_user_score',
        'jobs',
        ['user_id', 'affinity_score'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_jobs_user_score', table_name='jobs')
    op.drop_index('ix_jobs_user_profile', table_name='jobs')
    op.drop_index('ix_scraped_jobs_domain_seniority_role', table_name='scraped_jobs')
