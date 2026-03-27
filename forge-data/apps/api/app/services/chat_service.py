"""Workspace chat service for persistence and realtime broadcasting."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ValidationError
from app.core.ws import ws_manager
from app.models.collaboration import WorkspaceChat, WorkspaceChatContentType
from app.models.user import User


class WorkspaceChatService:
    async def send_message(
        self,
        db: AsyncSession,
        workspace_id: str,
        author: User | None,
        content: str,
        content_type: str = WorkspaceChatContentType.text.value,
        metadata: dict[str, Any] | None = None,
    ) -> WorkspaceChat:
        value = content.strip()
        if not value:
            raise ValidationError("Message content is required")
        message = WorkspaceChat(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            author_id=author.id if author else None,
            content=value,
            content_type=content_type,
            metadata_json=metadata or {},
        )
        db.add(message)
        await db.flush()
        await db.refresh(message)
        await ws_manager.broadcast_to_workspace(
            workspace_id,
            {
                "type": "chat_message",
                "data": self.serialize_message(message, author_name=author.full_name if author else None),
            },
        )
        return message

    async def get_messages(
        self,
        db: AsyncSession,
        workspace_id: str,
        limit: int = 50,
        before_id: str | None = None,
    ) -> list[WorkspaceChat]:
        safe_limit = max(1, min(limit, 200))
        stmt = (
            select(WorkspaceChat)
            .options(selectinload(WorkspaceChat.author))
            .where(WorkspaceChat.workspace_id == workspace_id)
            .order_by(desc(WorkspaceChat.created_at), desc(WorkspaceChat.id))
            .limit(safe_limit)
        )
        if before_id:
            before = await db.get(WorkspaceChat, before_id)
            if before and before.workspace_id == workspace_id:
                stmt = stmt.where(WorkspaceChat.created_at < before.created_at)
        result = await db.execute(stmt)
        messages = list(result.scalars().all())
        messages.reverse()
        return messages

    async def send_system_message(
        self,
        db: AsyncSession,
        workspace_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> WorkspaceChat:
        return await self.send_message(
            db=db,
            workspace_id=workspace_id,
            author=None,
            content=content,
            content_type=WorkspaceChatContentType.system.value,
            metadata=metadata or {},
        )

    @staticmethod
    def serialize_message(message: WorkspaceChat, author_name: str | None = None) -> dict[str, Any]:
        return {
            "id": message.id,
            "workspace_id": message.workspace_id,
            "author_id": message.author_id,
            "author_name": author_name or (message.author.full_name if getattr(message, "author", None) else None),
            "content": message.content,
            "content_type": message.content_type,
            "metadata": message.metadata_json or {},
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }


chat_service = WorkspaceChatService()

