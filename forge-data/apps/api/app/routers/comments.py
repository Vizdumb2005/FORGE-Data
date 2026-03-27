"""Workspace comments API."""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import CurrentUser, DBSession
from app.schemas.collaboration import WorkspaceCommentCreate
from app.services.comment_service import comment_service
from app.services.workspace_service import check_workspace_role

router = APIRouter()


@router.post(
    "/api/v1/workspaces/{workspace_id}/comments",
    response_model=dict,
    status_code=201,
)
async def create_comment(
    workspace_id: str,
    payload: WorkspaceCommentCreate,
    current_user: CurrentUser,
    db: DBSession,
) -> dict:
    await check_workspace_role(db, workspace_id, current_user.id, ("editor", "admin", "analyst"))
    comment = await comment_service.create_comment(
        db,
        workspace_id=workspace_id,
        author=current_user,
        content=payload.content,
        cell_id=payload.cell_id,
        parent_id=payload.parent_comment_id,
        pos_x=payload.position_x,
        pos_y=payload.position_y,
    )
    await db.commit()
    return comment_service.serialize_comment(comment, author_name=current_user.full_name)


@router.get("/api/v1/workspaces/{workspace_id}/comments", response_model=list[dict])
async def list_comments(
    workspace_id: str,
    include_resolved: bool = False,
    current_user: CurrentUser = ...,
    db: DBSession = ...,
) -> list[dict]:
    await check_workspace_role(db, workspace_id, current_user.id, ("viewer", "analyst", "editor", "admin"))
    comments = await comment_service.get_workspace_comments(db, workspace_id, include_resolved=include_resolved)
    return [comment_service.serialize_comment(comment) for comment in comments]


@router.patch("/api/v1/workspaces/{workspace_id}/comments/{comment_id}/resolve", response_model=dict)
async def resolve_comment(
    workspace_id: str,
    comment_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> dict:
    await check_workspace_role(db, workspace_id, current_user.id, ("editor", "admin", "analyst"))
    comment = await comment_service.resolve_comment(db, comment_id=comment_id, resolver=current_user)
    await db.commit()
    return comment_service.serialize_comment(comment)


@router.delete("/api/v1/workspaces/{workspace_id}/comments/{comment_id}", status_code=200)
async def delete_comment(
    workspace_id: str,
    comment_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> None:
    await check_workspace_role(db, workspace_id, current_user.id, ("editor", "admin", "analyst"))
    await comment_service.delete_comment(db, workspace_id, comment_id, current_user)
    await db.commit()

