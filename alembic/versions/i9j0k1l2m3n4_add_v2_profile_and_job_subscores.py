"""Add V2 profile normalization columns and missing job sub-score columns

Adds to search_profiles:
- profile_normalized_role_type
- profile_normalized_industry_sectors
- profile_normalized_transferable_skills
- profile_search_intent_role_type
- profile_search_intent_seniority_min
- profile_search_intent_seniority_max
- profile_search_intent_dealbreakers
- profile_search_intent_flexibility

Adds to jobs:
- transferability_score
- qualification_gap_score

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-03-26 00:00:00.000000
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'i9j0k1l2m3n4'
down_revision: Union[str, None] = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── search_profiles: V2 enhanced candidate profile ────────────────────
    op.add_column('search_profiles', sa.Column('profile_normalized_role_type', sa.String(), nullable=True))
    op.add_column('search_profiles', sa.Column('profile_normalized_industry_sectors', sa.JSON(), nullable=True))
    op.add_column('search_profiles', sa.Column('profile_normalized_transferable_skills', sa.JSON(), nullable=True))

    # ── search_profiles: V2 enhanced search intent ────────────────────────
    op.add_column('search_profiles', sa.Column('profile_search_intent_role_type', sa.String(), nullable=True))
    op.add_column('search_profiles', sa.Column('profile_search_intent_seniority_min', sa.String(), nullable=True))
    op.add_column('search_profiles', sa.Column('profile_search_intent_seniority_max', sa.String(), nullable=True))
    op.add_column('search_profiles', sa.Column('profile_search_intent_dealbreakers', sa.JSON(), nullable=True))
    op.add_column('search_profiles', sa.Column('profile_search_intent_flexibility', sa.JSON(), nullable=True))

    # ── jobs: missing dimensional sub-scores ─────────────────────────────
    op.add_column('jobs', sa.Column('transferability_score', sa.Float(), nullable=True))
    op.add_column('jobs', sa.Column('qualification_gap_score', sa.Float(), nullable=True))


def downgrade() -> None:
    # ── jobs: missing dimensional sub-scores ─────────────────────────────
    op.drop_column('jobs', 'qualification_gap_score')
    op.drop_column('jobs', 'transferability_score')

    # ── search_profiles: V2 enhanced search intent ────────────────────────
    op.drop_column('search_profiles', 'profile_search_intent_flexibility')
    op.drop_column('search_profiles', 'profile_search_intent_dealbreakers')
    op.drop_column('search_profiles', 'profile_search_intent_seniority_max')
    op.drop_column('search_profiles', 'profile_search_intent_seniority_min')
    op.drop_column('search_profiles', 'profile_search_intent_role_type')

    # ── search_profiles: V2 enhanced candidate profile ────────────────────
    op.drop_column('search_profiles', 'profile_normalized_transferable_skills')
    op.drop_column('search_profiles', 'profile_normalized_industry_sectors')
    op.drop_column('search_profiles', 'profile_normalized_role_type')
