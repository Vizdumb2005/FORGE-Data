"""Workspaces router — CRUD, member management, RBAC-protected.

All endpoints live under ``/api/v1/workspaces``.
"""

import logging

from fastapi import APIRouter, Depends, Request

from app.dependencies import CurrentUser, DBSession, require_workspace_role
from app.models.workspace import Workspace
from app.schemas.workspace import (
    MemberAdd,
    MemberRead,
    MemberRoleUpdate,
    WorkspaceCreate,
    WorkspaceDetail,
    WorkspaceRead,
    WorkspaceUpdate,
)
from app.services import audit_service, workspace_service

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# 1. POST / — Create a workspace
# =============================================================================

@router.post(
    "/",
    response_model=WorkspaceRead,
    status_code=201,
    summary="Create a workspace",
)
async def create_workspace(
    payload: WorkspaceCreate,
    current_user: CurrentUser,
    db: DBSession,
    request: Request,
) -> WorkspaceRead:
    ws = await workspace_service.create_workspace(db, payload, current_user.id)
    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.WORKSPACE_CREATE,
        user_id=current_user.id,
        workspace_id=ws.id,
        resource_type="workspace",
        resource_id=ws.id,
        ip_address=request.client.host if request.client else None,
        metadata={"name": ws.name},
    )
    # Return enriched response
    return WorkspaceRead(
        id=ws.id,
        name=ws.name,
        description=ws.description,
        is_public=ws.is_public,
        owner_id=ws.owner_id,
        created_at=ws.created_at,
        updated_at=ws.updated_at,
        member_count=1,
        dataset_count=0,
        role="admin",
    )


# =============================================================================
# 2. GET / — List accessible workspaces
# =============================================================================

@router.get(
    "/",
    response_model=list[WorkspaceRead],
    summary="List accessible workspaces",
)
async def list_workspaces(
    current_user: CurrentUser,
    db: DBSession,
) -> list[WorkspaceRead]:
    return await workspace_service.list_workspaces(db, current_user.id)


# =============================================================================
# 3. GET /{workspace_id} — Get workspace detail
# =============================================================================

@router.get(
    "/{workspace_id}",
    response_model=WorkspaceDetail,
    summary="Get workspace with members list",
)
async def get_workspace(
    workspace: Workspace = Depends(require_workspace_role("viewer", "analyst", "editor", "admin")),
    current_user: CurrentUser = ...,
    db: DBSession = ...,
) -> WorkspaceDetail:
    return await workspace_service.get_workspace_detail(db, workspace.id, current_user.id)


# =============================================================================
# 4. PATCH /{workspace_id} — Update workspace
# =============================================================================

@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceRead,
    summary="Update a workspace",
)
async def update_workspace(
    payload: WorkspaceUpdate,
    request: Request,
    workspace: Workspace = Depends(require_workspace_role("editor", "admin")),
    current_user: CurrentUser = ...,
    db: DBSession = ...,
) -> WorkspaceRead:
    updated = await workspace_service.update_workspace(db, workspace, payload)
    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.WORKSPACE_UPDATE,
        user_id=current_user.id,
        workspace_id=workspace.id,
        resource_type="workspace",
        resource_id=workspace.id,
        ip_address=request.client.host if request.client else None,
        metadata=payload.model_dump(exclude_unset=True),
    )
    role = await workspace_service._resolve_role(updated, current_user.id, db)
    member_count = await workspace_service._count_members(db, updated.id) + 1
    dataset_count = await workspace_service._count_datasets(db, updated.id)
    return WorkspaceRead(
        id=updated.id,
        name=updated.name,
        description=updated.description,
        is_public=updated.is_public,
        owner_id=updated.owner_id,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
        member_count=member_count,
        dataset_count=dataset_count,
        role=role,
    )


# =============================================================================
# 5. DELETE /{workspace_id} — Soft delete workspace
# =============================================================================

@router.delete(
    "/{workspace_id}",
    status_code=204,
    summary="Soft-delete a workspace",
)
async def delete_workspace(
    request: Request,
    workspace: Workspace = Depends(require_workspace_role("admin")),
    current_user: CurrentUser = ...,
    db: DBSession = ...,
) -> None:
    await workspace_service.soft_delete_workspace(db, workspace)
    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.WORKSPACE_DELETE,
        user_id=current_user.id,
        workspace_id=workspace.id,
        resource_type="workspace",
        resource_id=workspace.id,
        ip_address=request.client.host if request.client else None,
    )


# =============================================================================
# 6. POST /{workspace_id}/members — Add member by email
# =============================================================================

@router.post(
    "/{workspace_id}/members",
    response_model=MemberRead,
    status_code=201,
    summary="Add a member to a workspace (by email)",
)
async def add_member(
    payload: MemberAdd,
    request: Request,
    workspace: Workspace = Depends(require_workspace_role("admin")),
    current_user: CurrentUser = ...,
    db: DBSession = ...,
) -> MemberRead:
    member = await workspace_service.add_member_by_email(db, workspace.id, payload)
    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.WORKSPACE_MEMBER_ADD,
        user_id=current_user.id,
        workspace_id=workspace.id,
        resource_type="workspace_member",
        resource_id=member.user_id,
        ip_address=request.client.host if request.client else None,
        metadata={"email": payload.email, "role": payload.role.value},
    )
    return MemberRead.model_validate(member)


# =============================================================================
# 7. PATCH /{workspace_id}/members/{user_id} — Change member role
# =============================================================================

@router.patch(
    "/{workspace_id}/members/{user_id}",
    response_model=MemberRead,
    summary="Change a member's role",
)
async def update_member_role(
    user_id: str,
    payload: MemberRoleUpdate,
    request: Request,
    workspace: Workspace = Depends(require_workspace_role("admin")),
    current_user: CurrentUser = ...,
    db: DBSession = ...,
) -> MemberRead:
    member = await workspace_service.update_member_role(
        db, workspace.id, user_id, payload
    )
    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.WORKSPACE_MEMBER_UPDATE,
        user_id=current_user.id,
        workspace_id=workspace.id,
        resource_type="workspace_member",
        resource_id=user_id,
        ip_address=request.client.host if request.client else None,
        metadata={"new_role": payload.role.value},
    )
    return MemberRead.model_validate(member)


# =============================================================================
# 8. DELETE /{workspace_id}/members/{user_id} — Remove member
# =============================================================================

@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=204,
    summary="Remove a member from a workspace",
)
async def remove_member(
    workspace_id: str,
    user_id: str,
    request: Request,
    current_user: CurrentUser = ...,
    db: DBSession = ...,
) -> None:
    # Self-removal is allowed without admin role; admin removal is checked inside the service
    await workspace_service.remove_member(db, workspace_id, user_id, current_user.id)
    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.WORKSPACE_MEMBER_REMOVE,
        user_id=current_user.id,
        workspace_id=workspace_id,
        resource_type="workspace_member",
        resource_id=user_id,
        ip_address=request.client.host if request.client else None,
        metadata={"self_removal": user_id == current_user.id},
    )
