"""009 - Lineage nodes and edges tables.

Revision ID: 009_lineage_tracking
Revises: 008_dataset_metadata
Create Date: 2026-03-24 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "009_lineage_tracking"
down_revision: str = "008_dataset_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lineage_nodes (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            node_type VARCHAR(32) NOT NULL,
            ref_id VARCHAR(128) NOT NULL,
            label VARCHAR(255) NOT NULL,
            metadata JSONB,
            position_x DOUBLE PRECISION NOT NULL DEFAULT 0,
            position_y DOUBLE PRECISION NOT NULL DEFAULT 0,
            last_executed_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_lineage_node_ref UNIQUE (workspace_id, node_type, ref_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_lineage_nodes_workspace_id ON lineage_nodes(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_lineage_nodes_node_type ON lineage_nodes(node_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_lineage_nodes_ref_id ON lineage_nodes(ref_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lineage_edges (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            source_node_id UUID NOT NULL REFERENCES lineage_nodes(id) ON DELETE CASCADE,
            target_node_id UUID NOT NULL REFERENCES lineage_nodes(id) ON DELETE CASCADE,
            edge_type VARCHAR(32) NOT NULL DEFAULT 'transform',
            label VARCHAR(255),
            metadata JSONB,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_lineage_edge UNIQUE (workspace_id, source_node_id, target_node_id, edge_type)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_lineage_edges_workspace_id ON lineage_edges(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_lineage_edges_source_node_id ON lineage_edges(source_node_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_lineage_edges_target_node_id ON lineage_edges(target_node_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lineage_edges")
    op.execute("DROP TABLE IF EXISTS lineage_nodes")

