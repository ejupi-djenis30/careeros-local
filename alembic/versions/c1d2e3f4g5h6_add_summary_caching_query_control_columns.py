"""add summary caching and query control columns

Revision ID: c1d2e3f4g5h6
Revises: aa38af1be029
Create Date: 2026-03-24 16:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4g5h6'
down_revision: Union[str, None] = 'aa38af1be029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Feature 1: LLM-generated job summary stored in scraped_jobs
    op.add_column('scraped_jobs', sa.Column('summary', sa.Text(), nullable=True))

    # Feature 3: Caching CV summary and generated queries on search_profiles
    op.add_column('search_profiles', sa.Column('cached_cv_summary', sa.Text(), nullable=True))
    op.add_column('search_profiles', sa.Column('cached_queries', sa.JSON(), nullable=True))

    # Feature 4: Granular query type control on search_profiles
    op.add_column('search_profiles', sa.Column('max_occupation_queries', sa.Integer(), nullable=True))
    op.add_column('search_profiles', sa.Column('max_keyword_queries', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('search_profiles', 'max_keyword_queries')
    op.drop_column('search_profiles', 'max_occupation_queries')
    op.drop_column('search_profiles', 'cached_queries')
    op.drop_column('search_profiles', 'cached_cv_summary')
    op.drop_column('scraped_jobs', 'summary')
