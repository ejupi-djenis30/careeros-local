"""Add ScrapedJob UniqueConstraint

Revision ID: aa38af1be029
Revises: b3c4d5e6f7a8
Create Date: 2026-03-24 13:49:41.398436
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa38af1be029'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add unique constraint to scraped_jobs (Incremental change)
    op.create_unique_constraint(
        'uq_scraped_job_platform_id', 
        'scraped_jobs', 
        ['platform', 'platform_job_id']
    )


def downgrade() -> None:
    op.drop_constraint('uq_scraped_job_platform_id', 'scraped_jobs', type_='unique')

