"""Add analysis_structured, red_flags to jobs; posting_quality to scraped_jobs

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-07-01 00:00:00.000000

Adds Phase 3+4 columns:
  jobs:
    - analysis_structured    (JSON)  — structured evidence-grounded analysis output
    - red_flags              (JSON)  — list of red flag strings detected in job posting
  scraped_jobs:
    - posting_quality        (Float) — 0.0-1.0 information richness score of description
"""

import sqlalchemy as sa

from alembic import op

revision = "m3n4o5p6q7r8"
down_revision = "l2m3n4o5p6q7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("analysis_structured", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("red_flags", sa.JSON(), nullable=True))
    op.add_column("scraped_jobs", sa.Column("posting_quality", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("scraped_jobs", "posting_quality")
    op.drop_column("jobs", "red_flags")
    op.drop_column("jobs", "analysis_structured")
