"""011 - Add workflow trigger_config JSONB.

Revision ID: 011_workflow_trigger_config
Revises: 010_workflow_tables
Create Date: 2026-03-27 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "011_workflow_trigger_config"
down_revision: str = "010_workflow_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE workflows ADD COLUMN IF NOT EXISTS trigger_config JSONB NOT NULL DEFAULT '{}'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE workflows DROP COLUMN IF EXISTS trigger_config")

