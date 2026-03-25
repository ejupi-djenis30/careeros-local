"""add scraped job normalization columns

Revision ID: d4e5f6a7b8c9
Revises: 4e50d54b9df1
Create Date: 2026-03-25 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = '4e50d54b9df1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('scraped_jobs', sa.Column('normalization_status', sa.String(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalization_version', sa.Integer(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalization_source', sa.String(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalization_confidence', sa.Float(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_title', sa.String(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_role_family', sa.String(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_domain', sa.String(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_seniority', sa.String(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_employment_mode', sa.String(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_contract_type', sa.String(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_qualification_level', sa.String(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_experience_min_years', sa.Integer(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_experience_max_years', sa.Integer(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_workload_min', sa.Integer(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_workload_max', sa.Integer(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_salary_min_chf', sa.Integer(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_salary_max_chf', sa.Integer(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_required_languages', sa.JSON(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_required_skills', sa.JSON(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_education_levels', sa.JSON(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_key_requirements', sa.JSON(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_metadata', sa.JSON(), nullable=True))

    op.create_index(op.f('ix_scraped_jobs_normalization_status'), 'scraped_jobs', ['normalization_status'], unique=False)
    op.create_index(op.f('ix_scraped_jobs_normalized_at'), 'scraped_jobs', ['normalized_at'], unique=False)
    op.create_index(op.f('ix_scraped_jobs_normalized_role_family'), 'scraped_jobs', ['normalized_role_family'], unique=False)
    op.create_index(op.f('ix_scraped_jobs_normalized_domain'), 'scraped_jobs', ['normalized_domain'], unique=False)
    op.create_index(op.f('ix_scraped_jobs_normalized_seniority'), 'scraped_jobs', ['normalized_seniority'], unique=False)
    op.create_index(op.f('ix_scraped_jobs_normalized_employment_mode'), 'scraped_jobs', ['normalized_employment_mode'], unique=False)
    op.create_index(op.f('ix_scraped_jobs_normalized_contract_type'), 'scraped_jobs', ['normalized_contract_type'], unique=False)
    op.create_index(op.f('ix_scraped_jobs_normalized_qualification_level'), 'scraped_jobs', ['normalized_qualification_level'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_scraped_jobs_normalized_qualification_level'), table_name='scraped_jobs')
    op.drop_index(op.f('ix_scraped_jobs_normalized_contract_type'), table_name='scraped_jobs')
    op.drop_index(op.f('ix_scraped_jobs_normalized_employment_mode'), table_name='scraped_jobs')
    op.drop_index(op.f('ix_scraped_jobs_normalized_seniority'), table_name='scraped_jobs')
    op.drop_index(op.f('ix_scraped_jobs_normalized_domain'), table_name='scraped_jobs')
    op.drop_index(op.f('ix_scraped_jobs_normalized_role_family'), table_name='scraped_jobs')
    op.drop_index(op.f('ix_scraped_jobs_normalized_at'), table_name='scraped_jobs')
    op.drop_index(op.f('ix_scraped_jobs_normalization_status'), table_name='scraped_jobs')

    op.drop_column('scraped_jobs', 'normalized_metadata')
    op.drop_column('scraped_jobs', 'normalized_key_requirements')
    op.drop_column('scraped_jobs', 'normalized_education_levels')
    op.drop_column('scraped_jobs', 'normalized_required_skills')
    op.drop_column('scraped_jobs', 'normalized_required_languages')
    op.drop_column('scraped_jobs', 'normalized_salary_max_chf')
    op.drop_column('scraped_jobs', 'normalized_salary_min_chf')
    op.drop_column('scraped_jobs', 'normalized_workload_max')
    op.drop_column('scraped_jobs', 'normalized_workload_min')
    op.drop_column('scraped_jobs', 'normalized_experience_max_years')
    op.drop_column('scraped_jobs', 'normalized_experience_min_years')
    op.drop_column('scraped_jobs', 'normalized_qualification_level')
    op.drop_column('scraped_jobs', 'normalized_contract_type')
    op.drop_column('scraped_jobs', 'normalized_employment_mode')
    op.drop_column('scraped_jobs', 'normalized_seniority')
    op.drop_column('scraped_jobs', 'normalized_domain')
    op.drop_column('scraped_jobs', 'normalized_role_family')
    op.drop_column('scraped_jobs', 'normalized_title')
    op.drop_column('scraped_jobs', 'normalization_confidence')
    op.drop_column('scraped_jobs', 'normalization_source')
    op.drop_column('scraped_jobs', 'normalization_version')
    op.drop_column('scraped_jobs', 'normalized_at')
    op.drop_column('scraped_jobs', 'normalization_status')