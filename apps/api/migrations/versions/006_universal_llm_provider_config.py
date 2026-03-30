"""006 — Add universal per-user LLM provider config storage.

Revision ID: 006_universal_llm_config
Revises: 005_semantic_and_pipelines
Create Date: 2026-03-20 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "006_universal_llm_config"
down_revision: str = "005_semantic_and_pipelines"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS llm_api_keys JSONB")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS llm_provider_config JSONB")


def downgrade() -> None:
    op.drop_column("users", "llm_provider_config")
    op.drop_column("users", "llm_api_keys")
