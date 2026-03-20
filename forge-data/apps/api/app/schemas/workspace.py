"""Workspace Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.workspace import MemberRole

# ── Create / Update ──────────────────────────────────────────────────────────


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    is_public: bool = False


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_public: bool | None = None


# ── Member management ────────────────────────────────────────────────────────


class MemberAdd(BaseModel):
    """Body for POST /{workspace_id}/members — lookup by email."""

    email: EmailStr
    role: MemberRole = MemberRole.viewer


class MemberRoleUpdate(BaseModel):
    """Body for PATCH /{workspace_id}/members/{user_id}."""

    role: MemberRole


# ── Read schemas ─────────────────────────────────────────────────────────────


class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: str
    user_id: str
    role: str
    created_at: datetime


class MemberReadWithUser(MemberRead):
    """MemberRead enriched with user display info."""

    email: str
    full_name: str


class WorkspaceRead(BaseModel):
    """Standard workspace response for listing."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    is_public: bool
    owner_id: str
    created_at: datetime
    updated_at: datetime
    # Enriched fields computed at query time
    member_count: int = 0
    dataset_count: int = 0
    role: str | None = None  # current user's role in this workspace


class WorkspaceDetail(WorkspaceRead):
    """Extended workspace response for GET /{workspace_id} — includes members."""

    members: list[MemberReadWithUser] = []
