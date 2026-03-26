"""Add UniqueConstraint to jobs table (user_id, scraped_job_id, search_profile_id)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_job_user_scraped_profile',
        'jobs',
        ['user_id', 'scraped_job_id', 'search_profile_id'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_job_user_scraped_profile',
        'jobs',
        type_='unique',
    )
