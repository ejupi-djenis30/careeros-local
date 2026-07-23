"""split_job_model_and_extend_profile

Revision ID: 4e50d54b9df1
Revises: c1d2e3f4g5h6
Create Date: 2026-03-24 21:39:57.557028
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "4e50d54b9df1"
down_revision: Union[str, None] = "c1d2e3f4g5h6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This revision was generated on a divergent branch.
    # It is intentionally a no-op to keep a single linear head.
    pass


def downgrade() -> None:
    pass
