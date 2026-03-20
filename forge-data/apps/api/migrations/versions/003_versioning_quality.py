"""003 — Add dataset_versions, data_quality_rulesets, data_quality_reports tables.

Revision ID: 003_versioning_quality
Revises: 002_add_profile_data
Create Date: 2026-03-11 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "003_versioning_quality"
down_revision: str = "002_add_profile_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Use raw SQL with IF NOT EXISTS for idempotency
    op.execute("""
        CREATE TABLE IF NOT EXISTS dataset_versions (
            id UUID PRIMARY KEY,
            dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
            version_number INTEGER NOT NULL,
            message TEXT,
            schema_snapshot JSONB,
            row_count INTEGER,
            size_bytes BIGINT,
            parquet_path VARCHAR(1024) NOT NULL DEFAULT '',
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dataset_versions_dataset_id ON dataset_versions(dataset_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS data_quality_rulesets (
            id UUID PRIMARY KEY,
            dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL DEFAULT 'default',
            rules JSONB NOT NULL DEFAULT '[]',
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_data_quality_rulesets_dataset_id ON data_quality_rulesets(dataset_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS data_quality_reports (
            id UUID PRIMARY KEY,
            dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
            version_number INTEGER,
            passed INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            results JSONB NOT NULL DEFAULT '[]',
            ruleset_id UUID REFERENCES data_quality_rulesets(id) ON DELETE SET NULL,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_data_quality_reports_dataset_id ON data_quality_reports(dataset_id)"
    )


def downgrade() -> None:
    op.drop_table("data_quality_reports")
    op.drop_table("data_quality_rulesets")
    op.drop_table("dataset_versions")
