"""004 — Add missing columns: users.ollama_base_url, workspaces.deleted_at.

Revision ID: 004_add_missing_columns
Revises: 003_versioning_quality
Create Date: 2026-03-12 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "004_add_missing_columns"
down_revision: str = "003_versioning_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ollama_base_url VARCHAR(512)")
    op.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")


def downgrade() -> None:
    op.drop_column("workspaces", "deleted_at")
    op.drop_column("users", "ollama_base_url")
