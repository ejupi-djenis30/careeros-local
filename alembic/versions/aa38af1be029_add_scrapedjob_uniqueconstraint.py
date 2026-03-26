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
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    # SQLite does not support ALTER ADD CONSTRAINT; use batch_alter_table (copy-and-move)
    if is_sqlite:
        with op.batch_alter_table('scraped_jobs') as batch_op:
            batch_op.create_unique_constraint(
                'uq_scraped_job_platform_id',
                ['platform', 'platform_job_id']
            )
    else:
        op.create_unique_constraint(
            'uq_scraped_job_platform_id',
            'scraped_jobs',
            ['platform', 'platform_job_id']
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    if is_sqlite:
        with op.batch_alter_table('scraped_jobs') as batch_op:
            batch_op.drop_constraint('uq_scraped_job_platform_id', type_='unique')
    else:
        op.drop_constraint('uq_scraped_job_platform_id', 'scraped_jobs', type_='unique')

