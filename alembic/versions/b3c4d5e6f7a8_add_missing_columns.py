"""add missing columns search_profile_id and contract_type

Revision ID: b3c4d5e6f7a8
Revises: 7d76134d9a36
Create Date: 2026-02-22 15:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = '7d76134d9a36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add search_profile_id to jobs table (nullable FK to search_profiles)
    op.add_column('jobs', sa.Column('search_profile_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_jobs_search_profile_id', 'jobs', 'search_profiles',
        ['search_profile_id'], ['id']
    )
    op.create_index(op.f('ix_jobs_search_profile_id'), 'jobs', ['search_profile_id'], unique=False)

    # Add contract_type to search_profiles table
    op.add_column('search_profiles', sa.Column('contract_type', sa.String(), nullable=True, server_default='any'))


def downgrade() -> None:
    op.drop_index(op.f('ix_jobs_search_profile_id'), table_name='jobs')
    op.drop_constraint('fk_jobs_search_profile_id', 'jobs', type_='foreignkey')
    op.drop_column('jobs', 'search_profile_id')
    op.drop_column('search_profiles', 'contract_type')
