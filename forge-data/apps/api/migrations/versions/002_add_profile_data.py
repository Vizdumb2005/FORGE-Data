"""002 — Add profile_data column to datasets table.

Revision ID: 002_add_profile_data
Revises: 001_initial
Create Date: 2026-03-11 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "002_add_profile_data"
down_revision: str = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE datasets ADD COLUMN IF NOT EXISTS profile_data JSONB")


def downgrade() -> None:
    op.drop_column("datasets", "profile_data")
