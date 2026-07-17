"""Add local resume drafts, immutable versions and artifacts.

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "t0u1v2w3x4y5"
down_revision: Union[str, None] = "s9t0u1v2w3x4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resume_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("template_kind", sa.String(length=20), nullable=False),
        sa.Column("section_config", sa.JSON(), nullable=False),
        sa.Column("selected_fact_ids", sa.JSON(), nullable=False),
        sa.Column("content_overrides", sa.JSON(), nullable=False),
        sa.Column("photo_asset_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["photo_asset_id"], ["career_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["profile_id"], ["candidate_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resume_drafts_profile_id", "resume_drafts", ["profile_id"])
    op.create_table(
        "resume_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("draft_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("semantic_version", sa.String(length=30), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("selected_fact_ids", sa.JSON(), nullable=False),
        sa.Column("template_kind", sa.String(length=20), nullable=False),
        sa.Column("renderer_version", sa.String(length=30), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality_report", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["resume_drafts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draft_id", "version_number", name="uq_resume_version_draft_number"),
    )
    op.create_index("ix_resume_versions_draft_id", "resume_versions", ["draft_id"])
    op.create_table(
        "resume_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["resume_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "format", name="uq_resume_artifact_version_format"),
    )
    op.create_index("ix_resume_artifacts_version_id", "resume_artifacts", ["version_id"])


def downgrade() -> None:
    op.drop_index("ix_resume_artifacts_version_id", table_name="resume_artifacts")
    op.drop_table("resume_artifacts")
    op.drop_index("ix_resume_versions_draft_id", table_name="resume_versions")
    op.drop_table("resume_versions")
    op.drop_index("ix_resume_drafts_profile_id", table_name="resume_drafts")
    op.drop_table("resume_drafts")
