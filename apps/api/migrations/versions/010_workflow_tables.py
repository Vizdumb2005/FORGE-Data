"""010 - Add Orion workflow tables.

Revision ID: 010_workflow_tables
Revises: 009_lineage_tracking
Create Date: 2026-03-26 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "010_workflow_tables"
down_revision: str = "009_lineage_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflows (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            schedule_cron VARCHAR(120),
            schedule_timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
            trigger_type VARCHAR(32) NOT NULL DEFAULT 'manual',
            webhook_secret VARCHAR(255),
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflows_workspace_id ON workflows(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflows_created_by ON workflows(created_by)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_nodes (
            id UUID PRIMARY KEY,
            workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
            node_type VARCHAR(32) NOT NULL,
            label VARCHAR(255) NOT NULL,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            position_x INTEGER NOT NULL DEFAULT 0,
            position_y INTEGER NOT NULL DEFAULT 0,
            on_success_node_id UUID REFERENCES workflow_nodes(id) ON DELETE SET NULL,
            on_failure_node_id UUID REFERENCES workflow_nodes(id) ON DELETE SET NULL,
            retry_count INTEGER NOT NULL DEFAULT 0,
            retry_delay_seconds INTEGER NOT NULL DEFAULT 60,
            timeout_seconds INTEGER NOT NULL DEFAULT 300
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_nodes_workflow_id ON workflow_nodes(workflow_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_edges (
            id UUID PRIMARY KEY,
            workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
            source_node_id UUID NOT NULL REFERENCES workflow_nodes(id) ON DELETE CASCADE,
            target_node_id UUID NOT NULL REFERENCES workflow_nodes(id) ON DELETE CASCADE,
            condition VARCHAR(32) NOT NULL DEFAULT 'always'
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_edges_workflow_id ON workflow_edges(workflow_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_edges_source_node_id ON workflow_edges(source_node_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_edges_target_node_id ON workflow_edges(target_node_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id UUID PRIMARY KEY,
            workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
            triggered_by VARCHAR(32) NOT NULL,
            triggered_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            error_message TEXT,
            run_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_runs_workflow_id ON workflow_runs(workflow_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_runs_triggered_by_user_id ON workflow_runs(triggered_by_user_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_node_runs (
            id UUID PRIMARY KEY,
            workflow_run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
            node_id UUID NOT NULL REFERENCES workflow_nodes(id) ON DELETE CASCADE,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            output JSONB,
            logs TEXT,
            error_message TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_node_runs_workflow_run_id ON workflow_node_runs(workflow_run_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_node_runs_node_id ON workflow_node_runs(node_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workflow_node_runs")
    op.execute("DROP TABLE IF EXISTS workflow_runs")
    op.execute("DROP TABLE IF EXISTS workflow_edges")
    op.execute("DROP TABLE IF EXISTS workflow_nodes")
    op.execute("DROP TABLE IF EXISTS workflows")
