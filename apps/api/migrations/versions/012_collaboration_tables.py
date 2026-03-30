"""012 - Add collaboration comments and chat tables.

Revision ID: 012_collaboration_tables
Revises: 011_workflow_trigger_config
Create Date: 2026-03-27 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "012_collaboration_tables"
down_revision: str = "011_workflow_trigger_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_comments (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            cell_id UUID REFERENCES cells(id) ON DELETE SET NULL,
            parent_comment_id UUID REFERENCES workspace_comments(id) ON DELETE CASCADE,
            author_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            resolved BOOLEAN NOT NULL DEFAULT FALSE,
            resolved_by UUID REFERENCES users(id) ON DELETE SET NULL,
            resolved_at TIMESTAMPTZ,
            position_x INTEGER,
            position_y INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_workspace_comments_workspace_id ON workspace_comments(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workspace_comments_cell_id ON workspace_comments(cell_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workspace_comments_parent_comment_id ON workspace_comments(parent_comment_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workspace_comments_author_id ON workspace_comments(author_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workspace_comments_resolved_by ON workspace_comments(resolved_by)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_chat (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            author_id UUID REFERENCES users(id) ON DELETE SET NULL,
            content TEXT NOT NULL,
            content_type VARCHAR(32) NOT NULL DEFAULT 'text',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_workspace_chat_workspace_id ON workspace_chat(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workspace_chat_author_id ON workspace_chat(author_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workspace_chat_created_at ON workspace_chat(created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workspace_chat")
    op.execute("DROP TABLE IF EXISTS workspace_comments")

