"""Cell ORM model — a single code/SQL/markdown/AI cell within a workspace."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.workspace import Workspace


class CellType(str, Enum):
    code = "code"
    sql = "sql"
    markdown = "markdown"
    chart = "chart"
    ai_chat = "ai_chat"


class CellLanguage(str, Enum):
    python = "python"
    sql = "sql"
    r = "r"
    javascript = "javascript"
    markdown = "markdown"


class Cell(Base):
    __tablename__ = "cells"

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

    # ── Layout (grid coordinates, zero-based) ──────────────────────────────
    position_x: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    position_y: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=4, nullable=False)

    # ── Cell kind & language ───────────────────────────────────────────────
    cell_type: Mapped[str] = mapped_column(String(32), default=CellType.code.value, nullable=False)
    language: Mapped[str] = mapped_column(
        String(32), default=CellLanguage.python.value, nullable=False
    )

    # ── Content & execution output ─────────────────────────────────────────
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Output schema (example):
    # {
    #   "status": "ok" | "error",
    #   "output_type": "stream" | "display_data" | "execute_result" | "error",
    #   "text": "...",
    #   "data": {"text/plain": "...", "text/html": "...", "image/png": "..."},
    #   "ename": "...",  # on error
    #   "evalue": "...",
    #   "traceback": [...],
    #   "execution_count": 1
    # }

    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # kernel_id stores the Jupyter kernel assigned to this cell's workspace session
    kernel_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="cells")

    def __repr__(self) -> str:
        return (
            f"<Cell id={self.id!r} type={self.cell_type!r} "
            f"lang={self.language!r} ws={self.workspace_id!r}>"
        )
