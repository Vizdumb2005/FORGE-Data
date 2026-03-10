"""Workspace service — CRUD, member management, RBAC helpers."""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.models.dataset import Dataset
from app.models.user import User
from app.models.workspace import MemberRole, Workspace, WorkspaceMember
from app.schemas.workspace import (
    MemberAdd,
    MemberReadWithUser,
    MemberRoleUpdate,
    WorkspaceCreate,
    WorkspaceDetail,
    WorkspaceRead,
    WorkspaceUpdate,
)

logger = logging.getLogger(__name__)

# Role ordering — higher index = more permissive
_ROLE_ORDER = [
    MemberRole.viewer,
    MemberRole.analyst,
    MemberRole.editor,
    MemberRole.admin,
]


def _role_gte(user_role: str, required_role: MemberRole) -> bool:
    """Return True if *user_role* is at least as powerful as *required_role*."""
    try:
        return _ROLE_ORDER.index(MemberRole(user_role)) >= _ROLE_ORDER.index(required_role)
    except ValueError:
        return False


# ── Soft-delete filter ───────────────────────────────────────────────────────

_NOT_DELETED = Workspace.deleted_at.is_(None)


# ── Read helpers ─────────────────────────────────────────────────────────────

async def _get_member_role(
    db: AsyncSession, workspace_id: str, user_id: str
) -> MemberRole | None:
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member:
        return MemberRole(member.role)
    return None


async def _resolve_role(
    workspace: Workspace, user_id: str, db: AsyncSession
) -> str | None:
    """Return the effective role string for user_id in workspace."""
    if workspace.owner_id == user_id:
        return "admin"
    role = await _get_member_role(db, workspace.id, user_id)
    return role.value if role else None


async def _count_members(db: AsyncSession, workspace_id: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id
        )
    )
    return result.scalar_one()


async def _count_datasets(db: AsyncSession, workspace_id: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(Dataset).where(
            Dataset.workspace_id == workspace_id
        )
    )
    return result.scalar_one()


# ── Workspace CRUD ───────────────────────────────────────────────────────────

async def get_workspace_or_404(
    db: AsyncSession,
    workspace_id: str,
) -> Workspace:
    """Return workspace by ID or raise 404. Does NOT check membership."""
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, _NOT_DELETED)
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise NotFoundException("Workspace", workspace_id)
    return workspace


async def get_workspace_for_user(
    db: AsyncSession,
    workspace_id: str,
    user_id: str,
) -> Workspace:
    """Return workspace if user has any access (owner, member, or public)."""
    workspace = await get_workspace_or_404(db, workspace_id)

    if workspace.owner_id == user_id:
        return workspace
    if workspace.is_public:
        return workspace

    member = await _get_member_role(db, workspace_id, user_id)
    if member is None:
        raise NotFoundException("Workspace", workspace_id)

    return workspace


async def list_workspaces(
    db: AsyncSession, user_id: str
) -> list[WorkspaceRead]:
    """Return all non-deleted workspaces accessible to *user_id* with counts and role."""
    # Owned workspaces
    owned_result = await db.execute(
        select(Workspace).where(Workspace.owner_id == user_id, _NOT_DELETED)
    )
    owned = list(owned_result.scalars().all())

    # Membership workspaces
    member_ws_ids_result = await db.execute(
        select(WorkspaceMember.workspace_id).where(
            WorkspaceMember.user_id == user_id
        )
    )
    member_ws_ids = [r[0] for r in member_ws_ids_result.all()]

    member_workspaces: list[Workspace] = []
    if member_ws_ids:
        result = await db.execute(
            select(Workspace).where(
                Workspace.id.in_(member_ws_ids), _NOT_DELETED
            )
        )
        member_workspaces = list(result.scalars().all())

    # Deduplicate
    seen: set[str] = set()
    combined: list[Workspace] = []
    for ws in owned + member_workspaces:
        if ws.id not in seen:
            seen.add(ws.id)
            combined.append(ws)

    # Enrich with counts and role
    results: list[WorkspaceRead] = []
    for ws in combined:
        role = await _resolve_role(ws, user_id, db)
        member_count = await _count_members(db, ws.id)
        dataset_count = await _count_datasets(db, ws.id)
        # Owner counts as a member for display (+1)
        results.append(WorkspaceRead(
            id=ws.id,
            name=ws.name,
            description=ws.description,
            is_public=ws.is_public,
            owner_id=ws.owner_id,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
            member_count=member_count + 1,  # +1 for owner
            dataset_count=dataset_count,
            role=role,
        ))
    return results


async def get_workspace_detail(
    db: AsyncSession,
    workspace_id: str,
    user_id: str,
) -> WorkspaceDetail:
    """Return workspace with members list, counts, and role for GET /{id}."""
    workspace = await get_workspace_for_user(db, workspace_id, user_id)

    # Load members with user info
    members_result = await db.execute(
        select(WorkspaceMember)
        .options(selectinload(WorkspaceMember.user))
        .where(WorkspaceMember.workspace_id == workspace_id)
    )
    members = list(members_result.scalars().all())

    member_reads = [
        MemberReadWithUser(
            workspace_id=m.workspace_id,
            user_id=m.user_id,
            role=m.role,
            created_at=m.created_at,
            email=m.user.email,
            full_name=m.user.full_name,
        )
        for m in members
    ]

    role = await _resolve_role(workspace, user_id, db)
    member_count = len(members) + 1  # +1 for owner
    dataset_count = await _count_datasets(db, workspace_id)

    return WorkspaceDetail(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        is_public=workspace.is_public,
        owner_id=workspace.owner_id,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        member_count=member_count,
        dataset_count=dataset_count,
        role=role,
        members=member_reads,
    )


async def create_workspace(
    db: AsyncSession, payload: WorkspaceCreate, owner_id: str
) -> Workspace:
    """Create a workspace and add the creator as an admin member."""
    workspace = Workspace(
        name=payload.name,
        description=payload.description,
        is_public=payload.is_public,
        owner_id=owner_id,
    )
    db.add(workspace)
    await db.flush()

    # Add creator as admin member
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=owner_id,
        role=MemberRole.admin.value,
    )
    db.add(member)
    await db.flush()

    return workspace


async def update_workspace(
    db: AsyncSession,
    workspace: Workspace,
    payload: WorkspaceUpdate,
) -> Workspace:
    """Apply partial updates to a workspace (caller already verified RBAC)."""
    if payload.name is not None:
        workspace.name = payload.name
    if payload.description is not None:
        workspace.description = payload.description
    if payload.is_public is not None:
        workspace.is_public = payload.is_public

    await db.flush()
    return workspace


async def soft_delete_workspace(
    db: AsyncSession,
    workspace: Workspace,
) -> None:
    """Soft-delete a workspace by setting deleted_at (caller already verified RBAC)."""
    workspace.deleted_at = datetime.now(timezone.utc)
    await db.flush()


# ── Member management ────────────────────────────────────────────────────────

async def add_member_by_email(
    db: AsyncSession,
    workspace_id: str,
    payload: MemberAdd,
) -> WorkspaceMember:
    """Look up user by email and add to workspace. Caller already verified admin RBAC."""
    # Resolve user by email
    user_result = await db.execute(
        select(User).where(User.email == payload.email.lower())
    )
    user: User | None = user_result.scalar_one_or_none()
    if user is None:
        raise NotFoundException("User", str(payload.email))

    # Check not already a member
    existing = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictException("User is already a member of this workspace")

    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=user.id,
        role=payload.role.value,
    )
    db.add(member)
    await db.flush()

    logger.info(
        "INVITE NOTIFICATION (stub): would notify %s about workspace %s",
        payload.email,
        workspace_id,
    )

    return member


async def update_member_role(
    db: AsyncSession,
    workspace_id: str,
    target_user_id: str,
    payload: MemberRoleUpdate,
) -> WorkspaceMember:
    """Change a member's role. Caller already verified admin RBAC.

    Cannot downgrade the only admin in the workspace.
    """
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == target_user_id,
        )
    )
    member: WorkspaceMember | None = result.scalar_one_or_none()
    if member is None:
        raise NotFoundException("WorkspaceMember")

    # Guard: cannot downgrade the only admin
    if member.role == MemberRole.admin.value and payload.role != MemberRole.admin:
        admin_count_result = await db.execute(
            select(func.count()).select_from(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role == MemberRole.admin.value,
            )
        )
        admin_count = admin_count_result.scalar_one()
        if admin_count <= 1:
            raise ForbiddenException(
                "Cannot downgrade the only admin. Promote another member first."
            )

    member.role = payload.role.value
    await db.flush()
    return member


async def remove_member(
    db: AsyncSession,
    workspace_id: str,
    target_user_id: str,
    current_user_id: str,
) -> None:
    """Remove a member. Admins can remove anyone; non-admins can only remove themselves."""
    is_self = target_user_id == current_user_id

    if not is_self:
        # Must be admin (caller should have checked via RBAC dependency, but double-check)
        workspace = await get_workspace_or_404(db, workspace_id)
        if workspace.owner_id != current_user_id:
            role = await _get_member_role(db, workspace_id, current_user_id)
            if role is None or not _role_gte(role.value, MemberRole.admin):
                raise ForbiddenException(
                    "Only admins can remove other members"
                )

    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == target_user_id,
        )
    )
    member: WorkspaceMember | None = result.scalar_one_or_none()
    if member is None:
        raise NotFoundException("WorkspaceMember")

    # Guard: cannot remove the only admin (even self)
    if member.role == MemberRole.admin.value:
        admin_count_result = await db.execute(
            select(func.count()).select_from(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role == MemberRole.admin.value,
            )
        )
        if admin_count_result.scalar_one() <= 1:
            raise ForbiddenException(
                "Cannot remove the only admin. Promote another member first."
            )

    await db.delete(member)
    await db.flush()


# ── RBAC check (used by the require_workspace_role dependency) ───────────────

async def check_workspace_role(
    db: AsyncSession,
    workspace_id: str,
    user_id: str,
    allowed_roles: tuple[str, ...],
) -> Workspace:
    """Verify the user has one of the *allowed_roles* in the workspace.

    The workspace owner is always treated as having the ``admin`` role.

    Returns the :class:`Workspace` on success.
    Raises :class:`NotFoundException` (404) if the workspace doesn't exist.
    Raises :class:`ForbiddenException` (403) if the user lacks permission.
    """
    workspace = await get_workspace_or_404(db, workspace_id)

    # Owner always has full access (treated as admin)
    if workspace.owner_id == user_id:
        return workspace

    role = await _get_member_role(db, workspace_id, user_id)
    if role is None:
        raise NotFoundException("Workspace", workspace_id)

    if role.value not in allowed_roles:
        raise ForbiddenException(
            f"This action requires one of these roles: {', '.join(allowed_roles)}"
        )

    return workspace
