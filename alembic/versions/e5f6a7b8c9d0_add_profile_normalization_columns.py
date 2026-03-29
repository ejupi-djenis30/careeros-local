"""add profile normalization columns

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-25 20:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "search_profiles", sa.Column("profile_normalization_status", sa.String(), nullable=True)
    )
    op.add_column(
        "search_profiles",
        sa.Column("profile_normalized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "search_profiles",
        sa.Column("profile_normalization_fingerprint", sa.String(), nullable=True),
    )
    op.add_column(
        "search_profiles", sa.Column("profile_normalized_seniority", sa.String(), nullable=True)
    )
    op.add_column(
        "search_profiles", sa.Column("profile_normalized_domain", sa.String(), nullable=True)
    )
    op.add_column(
        "search_profiles", sa.Column("profile_normalized_role_family", sa.String(), nullable=True)
    )
    op.add_column(
        "search_profiles",
        sa.Column("profile_normalized_qualification_level", sa.String(), nullable=True),
    )
    op.add_column(
        "search_profiles",
        sa.Column("profile_normalized_experience_years", sa.Integer(), nullable=True),
    )
    op.add_column(
        "search_profiles", sa.Column("profile_normalized_languages", sa.JSON(), nullable=True)
    )
    op.add_column(
        "search_profiles", sa.Column("profile_normalized_skills", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("search_profiles", "profile_normalized_skills")
    op.drop_column("search_profiles", "profile_normalized_languages")
    op.drop_column("search_profiles", "profile_normalized_experience_years")
    op.drop_column("search_profiles", "profile_normalized_qualification_level")
    op.drop_column("search_profiles", "profile_normalized_role_family")
    op.drop_column("search_profiles", "profile_normalized_domain")
    op.drop_column("search_profiles", "profile_normalized_seniority")
    op.drop_column("search_profiles", "profile_normalization_fingerprint")
    op.drop_column("search_profiles", "profile_normalized_at")
    op.drop_column("search_profiles", "profile_normalization_status")
