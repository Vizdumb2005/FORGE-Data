"""007 - Add publishing dashboards and scheduled reports tables.

Revision ID: 007_publishing_system
Revises: 006_universal_llm_config
Create Date: 2026-03-24 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "007_publishing_system"
down_revision: str = "006_universal_llm_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS published_dashboards (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            title VARCHAR(255) NOT NULL,
            slug VARCHAR(64) NOT NULL UNIQUE,
            cell_ids JSONB NOT NULL,
            snapshot JSONB NOT NULL,
            is_public BOOLEAN NOT NULL DEFAULT true,
            password_hash VARCHAR(255),
            refresh_interval_minutes INTEGER,
            last_refreshed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_published_dashboards_workspace_id "
        "ON published_dashboards(workspace_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_published_dashboards_created_by "
        "ON published_dashboards(created_by)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_published_dashboards_slug "
        "ON published_dashboards(slug)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_reports (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            cell_ids JSONB NOT NULL,
            format VARCHAR(16) NOT NULL,
            cron_expression VARCHAR(128) NOT NULL,
            delivery JSONB NOT NULL,
            celery_task_name VARCHAR(255) NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT true,
            last_sent_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            title TEXT
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scheduled_reports_workspace_id ON scheduled_reports(workspace_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scheduled_reports_created_by ON scheduled_reports(created_by)"
    )


def downgrade() -> None:
    op.drop_table("scheduled_reports")
    op.drop_table("published_dashboards")

