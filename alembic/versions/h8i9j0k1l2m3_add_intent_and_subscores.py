"""Add dual-signal intent columns and dimensional sub-scores

Adds:
- search_profiles: 7 search_intent columns (intent domain/seniority/role/qualification/skills/flags)
- scraped_jobs: normalized_industry_sector, normalized_role_type
- jobs: 5 dimensional sub-score columns (skill/experience/intent/language/location match)

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-03-26 00:00:00.000000

"""
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'h8i9j0k1l2m3'
# This migration depends on g7h8i9j0k1l2, which drops the deprecated `summary` column.
# Ensure g7h8i9j0k1l2 is applied before this revision so the migration chain remains linear.
down_revision: Union[str, None] = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── search_profiles: search intent columns ────────────────────────────
    op.add_column('search_profiles', sa.Column('profile_search_intent_domain', sa.String(), nullable=True))
    op.add_column('search_profiles', sa.Column('profile_search_intent_seniority', sa.String(), nullable=True))
    op.add_column('search_profiles', sa.Column('profile_search_intent_role_family', sa.String(), nullable=True))
    op.add_column('search_profiles', sa.Column('profile_search_intent_qualification_level', sa.String(), nullable=True))
    op.add_column('search_profiles', sa.Column('profile_search_intent_skills', sa.JSON(), nullable=True))
    op.add_column('search_profiles', sa.Column('profile_search_intent_open_to_unrelated', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('search_profiles', sa.Column('profile_search_intent_keywords', sa.JSON(), nullable=True))

    # ── scraped_jobs: industry sector + role type ─────────────────────────
    op.add_column('scraped_jobs', sa.Column('normalized_industry_sector', sa.String(), nullable=True))
    op.add_column('scraped_jobs', sa.Column('normalized_role_type', sa.String(), nullable=True))
    op.create_index('ix_scraped_jobs_normalized_role_type', 'scraped_jobs', ['normalized_role_type'])

    # ── jobs: dimensional sub-scores ─────────────────────────────────────
    op.add_column('jobs', sa.Column('skill_match_score', sa.Float(), nullable=True))
    op.add_column('jobs', sa.Column('experience_match_score', sa.Float(), nullable=True))
    op.add_column('jobs', sa.Column('intent_match_score', sa.Float(), nullable=True))
    op.add_column('jobs', sa.Column('language_match_score', sa.Float(), nullable=True))
    op.add_column('jobs', sa.Column('location_match_score', sa.Float(), nullable=True))


def downgrade() -> None:
    # ── jobs: dimensional sub-scores ─────────────────────────────────────
    op.drop_column('jobs', 'location_match_score')
    op.drop_column('jobs', 'language_match_score')
    op.drop_column('jobs', 'intent_match_score')
    op.drop_column('jobs', 'experience_match_score')
    op.drop_column('jobs', 'skill_match_score')

    # ── scraped_jobs: industry sector + role type ─────────────────────────
    op.drop_index('ix_scraped_jobs_normalized_role_type', table_name='scraped_jobs')
    op.drop_column('scraped_jobs', 'normalized_role_type')
    op.drop_column('scraped_jobs', 'normalized_industry_sector')

    # ── search_profiles: search intent columns ────────────────────────────
    op.drop_column('search_profiles', 'profile_search_intent_keywords')
    op.drop_column('search_profiles', 'profile_search_intent_open_to_unrelated')
    op.drop_column('search_profiles', 'profile_search_intent_skills')
    op.drop_column('search_profiles', 'profile_search_intent_qualification_level')
    op.drop_column('search_profiles', 'profile_search_intent_role_family')
    op.drop_column('search_profiles', 'profile_search_intent_seniority')
    op.drop_column('search_profiles', 'profile_search_intent_domain')
