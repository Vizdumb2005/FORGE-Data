"""Workspace comments service with threaded tree retrieval."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ForbiddenException, NotFoundException, ValidationError
from app.core.ws import ws_manager
from app.models.collaboration import WorkspaceComment
from app.models.user import User


class CommentService:
    async def create_comment(
        self,
        db: AsyncSession,
        workspace_id: str,
        author: User,
        content: str,
        cell_id: str | None = None,
        parent_id: str | None = None,
        pos_x: int | None = None,
        pos_y: int | None = None,
    ) -> WorkspaceComment:
        value = content.strip()
        if not value:
            raise ValidationError("Comment content is required")
        if parent_id:
            parent = await db.get(WorkspaceComment, parent_id)
            if parent is None or parent.workspace_id != workspace_id:
                raise NotFoundException("WorkspaceComment", parent_id)
        comment = WorkspaceComment(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            cell_id=cell_id,
            parent_comment_id=parent_id,
            author_id=author.id,
            content=value,
            position_x=pos_x,
            position_y=pos_y,
        )
        db.add(comment)
        await db.flush()
        await db.refresh(comment)
        payload = self.serialize_comment(comment, author_name=author.full_name)
        await ws_manager.broadcast_to_workspace(
            workspace_id,
            {"type": "comment_added", "data": payload},
        )
        return comment

    async def resolve_comment(
        self,
        db: AsyncSession,
        comment_id: str,
        resolver: User,
    ) -> WorkspaceComment:
        comment = await db.get(WorkspaceComment, comment_id)
        if comment is None:
            raise NotFoundException("WorkspaceComment", comment_id)
        comment.resolved = True
        comment.resolved_by = resolver.id
        comment.resolved_at = datetime.now(UTC)
        await db.flush()
        await db.refresh(comment)
        await ws_manager.broadcast_to_workspace(
            comment.workspace_id,
            {
                "type": "comment_resolved",
                "data": {
                    "id": comment.id,
                    "workspace_id": comment.workspace_id,
                    "resolved": True,
                    "resolved_by": resolver.id,
                    "resolved_at": comment.resolved_at.isoformat() if comment.resolved_at else None,
                },
            },
        )
        return comment

    async def get_workspace_comments(
        self,
        db: AsyncSession,
        workspace_id: str,
        include_resolved: bool = False,
    ) -> list[WorkspaceComment]:
        stmt = (
            select(WorkspaceComment)
            .options(
                selectinload(WorkspaceComment.author),
                selectinload(WorkspaceComment.replies).selectinload(WorkspaceComment.author),
            )
            .where(WorkspaceComment.workspace_id == workspace_id)
            .order_by(WorkspaceComment.created_at.asc())
        )
        if not include_resolved:
            stmt = stmt.where(WorkspaceComment.resolved.is_(False))
        result = await db.execute(stmt)
        all_comments = list(result.scalars().all())
        by_parent: dict[str | None, list[WorkspaceComment]] = {}
        for comment in all_comments:
            by_parent.setdefault(comment.parent_comment_id, []).append(comment)
        for children in by_parent.values():
            children.sort(key=lambda c: c.created_at)
        roots = by_parent.get(None, [])
        for root in roots:
            root.replies = by_parent.get(root.id, [])
        return roots

    async def delete_comment(self, db: AsyncSession, workspace_id: str, comment_id: str, user: User) -> None:
        comment = await db.get(WorkspaceComment, comment_id)
        if comment is None or comment.workspace_id != workspace_id:
            raise NotFoundException("WorkspaceComment", comment_id)
        if comment.author_id != user.id:
            raise ForbiddenException("Only the comment author can delete this comment")
        await db.delete(comment)
        await ws_manager.broadcast_to_workspace(
            workspace_id,
            {"type": "comment_deleted", "data": {"id": comment_id, "workspace_id": workspace_id}},
        )

    def serialize_comment(self, comment: WorkspaceComment, author_name: str | None = None) -> dict:
        return {
            "id": comment.id,
            "workspace_id": comment.workspace_id,
            "cell_id": comment.cell_id,
            "parent_comment_id": comment.parent_comment_id,
            "author_id": comment.author_id,
            "author_name": author_name or (comment.author.full_name if getattr(comment, "author", None) else None),
            "content": comment.content,
            "resolved": comment.resolved,
            "resolved_by": comment.resolved_by,
            "resolved_at": comment.resolved_at.isoformat() if comment.resolved_at else None,
            "position_x": comment.position_x,
            "position_y": comment.position_y,
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
            "updated_at": comment.updated_at.isoformat() if comment.updated_at else None,
            "replies": [
                self.serialize_comment(reply) for reply in sorted(comment.replies, key=lambda r: r.created_at)
            ],
        }


comment_service = CommentService()

