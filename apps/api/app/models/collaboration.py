"""Collaboration ORM models for workspace comments and chat."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.cell import Cell
    from app.models.user import User
    from app.models.workspace import Workspace


class WorkspaceChatContentType(str, Enum):
    text = "text"
    code_snippet = "code_snippet"
    system = "system"


class WorkspaceComment(Base):
    __tablename__ = "workspace_comments"

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
    cell_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("cells.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_comment_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workspace_comments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    author_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    position_x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position_y: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="comments")
    cell: Mapped[Cell | None] = relationship("Cell", back_populates="comments")
    author: Mapped[User] = relationship("User", foreign_keys=[author_id], back_populates="comments")
    resolver: Mapped[User | None] = relationship(
        "User", foreign_keys=[resolved_by], back_populates="resolved_comments"
    )
    parent_comment: Mapped[WorkspaceComment | None] = relationship(
        "WorkspaceComment", remote_side=[id], back_populates="replies"
    )
    replies: Mapped[list[WorkspaceComment]] = relationship(
        "WorkspaceComment", back_populates="parent_comment", cascade="all, delete-orphan"
    )


class WorkspaceChat(Base):
    __tablename__ = "workspace_chat"

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
    author_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(32),
        default=WorkspaceChatContentType.text.value,
        nullable=False,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="chat_messages")
    author: Mapped[User | None] = relationship("User", back_populates="chat_messages")

