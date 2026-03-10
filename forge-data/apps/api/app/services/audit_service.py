"""Audit service — programmatic creation of AuditLog entries."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log_event(
    db: AsyncSession,
    *,
    action: str,
    user_id: str | None = None,
    workspace_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    ip_address: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """
    Write a single audit log entry.

    Intended for use inside route handlers when domain-level detail is available
    (e.g. after creating a workspace we know its ID).

    For generic HTTP-level auditing see :class:`app.core.middleware.AuditMiddleware`.
    """
    entry = AuditLog(
        action=action,
        user_id=user_id,
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        metadata=metadata or {},
    )
    db.add(entry)
    # Do not commit here — the surrounding request transaction will commit.
    return entry


# ── Pre-built action constants ─────────────────────────────────────────────────
# Centralised strings prevent typos and make searching audit logs predictable.

class AuditAction:
    # Auth
    AUTH_REGISTER = "auth.register"
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_REFRESH = "auth.token.refresh"
    AUTH_PASSWORD_CHANGE = "auth.password.change"

    # Workspace
    WORKSPACE_CREATE = "workspace.create"
    WORKSPACE_UPDATE = "workspace.update"
    WORKSPACE_DELETE = "workspace.delete"
    WORKSPACE_MEMBER_ADD = "workspace.member.add"
    WORKSPACE_MEMBER_UPDATE = "workspace.member.update"
    WORKSPACE_MEMBER_REMOVE = "workspace.member.remove"

    # Dataset
    DATASET_CREATE = "dataset.create"
    DATASET_UPLOAD = "dataset.upload"
    DATASET_UPDATE = "dataset.update"
    DATASET_DELETE = "dataset.delete"

    # Cell
    CELL_CREATE = "cell.create"
    CELL_UPDATE = "cell.update"
    CELL_DELETE = "cell.delete"
    CELL_EXECUTE = "cell.execute"

    # AI
    AI_CHAT = "ai.chat"

    # Connector
    CONNECTOR_TEST = "connector.test"
