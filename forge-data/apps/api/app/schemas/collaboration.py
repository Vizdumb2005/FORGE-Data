"""Schemas for collaboration comments/chat and websocket state payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    cell_id: str | None = None
    parent_comment_id: str | None = None
    position_x: int | None = None
    position_y: int | None = None


class WorkspaceCommentResolveRequest(BaseModel):
    resolved: bool = True


class WorkspaceCommentAuthor(BaseModel):
    user_id: str
    full_name: str


class WorkspaceCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    cell_id: str | None
    parent_comment_id: str | None
    author_id: str
    content: str
    resolved: bool
    resolved_by: str | None
    resolved_at: datetime | None
    position_x: int | None
    position_y: int | None
    created_at: datetime
    updated_at: datetime
    author: WorkspaceCommentAuthor | None = None
    replies: list["WorkspaceCommentRead"] = []


class WorkspaceChatCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    content_type: str = Field(default="text", pattern="^(text|code_snippet|system)$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceChatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    author_id: str | None
    author_name: str | None = None
    content: str
    content_type: str
    metadata: dict[str, Any]
    created_at: datetime


class PresenceUserState(BaseModel):
    user_id: str
    full_name: str
    avatar_color: str
    cursor_x: float = 0
    cursor_y: float = 0
    active_cell_id: str | None = None
    last_seen: int


class CellLockState(BaseModel):
    cell_id: str
    locked_by_user_id: str
    locked_by_name: str
    locked_at: int


WorkspaceCommentRead.model_rebuild()

