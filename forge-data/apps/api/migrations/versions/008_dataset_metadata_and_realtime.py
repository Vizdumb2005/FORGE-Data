"""008 - Add dataset metadata column for PII markers.

Revision ID: 008_dataset_metadata
Revises: 007_publishing_system
Create Date: 2026-03-24 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "008_dataset_metadata"
down_revision: str = "007_publishing_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE datasets ADD COLUMN IF NOT EXISTS metadata JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE datasets DROP COLUMN IF EXISTS metadata")
