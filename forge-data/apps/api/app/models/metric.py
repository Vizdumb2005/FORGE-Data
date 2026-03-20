"""Metric ORM model for semantic memory definitions."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Metric(Base):
    __tablename__ = "metrics"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_metric_workspace_name"),)

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    formula_sql: Mapped[str] = mapped_column(Text, nullable=False)
    depends_on: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Metric id={self.id!r} name={self.name!r} workspace={self.workspace_id!r}>"
