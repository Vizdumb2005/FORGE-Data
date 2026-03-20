"""005 — Add semantic metrics and pipeline run tables.

Revision ID: 005_semantic_and_pipelines
Revises: 004_add_missing_columns
Create Date: 2026-03-20 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "005_semantic_and_pipelines"
down_revision: str = "004_add_missing_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            definition TEXT NOT NULL,
            formula_sql TEXT NOT NULL,
            depends_on JSONB,
            embedding JSONB,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_metric_workspace_name UNIQUE (workspace_id, name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_metrics_workspace_id ON metrics(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_metrics_created_by ON metrics(created_by)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS pipelines (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            goal TEXT NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            summary TEXT,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pipelines_workspace_id ON pipelines(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pipelines_created_by ON pipelines(created_by)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id UUID PRIMARY KEY,
            pipeline_id UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            goal TEXT NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            full_report TEXT,
            steps JSONB,
            outputs JSONB,
            retry_count INTEGER NOT NULL DEFAULT 0,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pipeline_runs_pipeline_id ON pipeline_runs(pipeline_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_workspace_id ON pipeline_runs(workspace_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_pipeline_runs_created_by ON pipeline_runs(created_by)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_pipelines (
            id UUID PRIMARY KEY,
            pipeline_run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
            cron_expression VARCHAR(128) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scheduled_pipelines_run_id ON scheduled_pipelines(pipeline_run_id)"
    )


def downgrade() -> None:
    op.drop_table("scheduled_pipelines")
    op.drop_table("pipeline_runs")
    op.drop_table("pipelines")
    op.drop_table("metrics")
