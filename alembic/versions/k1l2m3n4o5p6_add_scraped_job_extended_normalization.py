"""add scraped_job extended normalization columns

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-03-26 00:00:00.000000

Adds the following columns to scraped_jobs that exist in the ORM model but were
never included in any previous migration:
  - normalized_preferred_skills     (JSON)
  - normalized_soft_skills          (JSON)
  - normalized_physical_requirements(JSON)
  - normalized_entry_barrier        (String)
  - normalized_career_changer_friendly (Boolean)
  - normalized_hard_blockers        (JSON)
"""

import sqlalchemy as sa

from alembic import op

revision = "k1l2m3n4o5p6"
down_revision = "j0k1l2m3n4o5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scraped_jobs", sa.Column("normalized_preferred_skills", sa.JSON(), nullable=True)
    )
    op.add_column("scraped_jobs", sa.Column("normalized_soft_skills", sa.JSON(), nullable=True))
    op.add_column(
        "scraped_jobs", sa.Column("normalized_physical_requirements", sa.JSON(), nullable=True)
    )
    op.add_column("scraped_jobs", sa.Column("normalized_entry_barrier", sa.String(), nullable=True))
    op.add_column(
        "scraped_jobs", sa.Column("normalized_career_changer_friendly", sa.Boolean(), nullable=True)
    )
    op.add_column("scraped_jobs", sa.Column("normalized_hard_blockers", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("scraped_jobs", "normalized_hard_blockers")
    op.drop_column("scraped_jobs", "normalized_career_changer_friendly")
    op.drop_column("scraped_jobs", "normalized_entry_barrier")
    op.drop_column("scraped_jobs", "normalized_physical_requirements")
    op.drop_column("scraped_jobs", "normalized_soft_skills")
    op.drop_column("scraped_jobs", "normalized_preferred_skills")
