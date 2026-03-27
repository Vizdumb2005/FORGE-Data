"""Workspace chat API."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, DBSession
from app.services.chat_service import chat_service
from app.services.workspace_service import check_workspace_role

router = APIRouter()


@router.get("/api/v1/workspaces/{workspace_id}/chat/messages", response_model=list[dict])
async def get_messages(
    workspace_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before_id: str | None = None,
    current_user: CurrentUser = ...,
    db: DBSession = ...,
) -> list[dict]:
    await check_workspace_role(db, workspace_id, current_user.id, ("viewer", "analyst", "editor", "admin"))
    messages = await chat_service.get_messages(db, workspace_id=workspace_id, limit=limit, before_id=before_id)
    return [chat_service.serialize_message(message) for message in messages]

