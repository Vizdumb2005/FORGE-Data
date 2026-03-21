from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, select

from app.dependencies import CurrentUser, DBSession
from app.models.audit_log import AuditLog as AuditLogModel

router = APIRouter()


class AuditLog(BaseModel):
    id: str
    action: str
    user_id: str | None
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    created_at: datetime
    meta: dict


@router.get("", response_model=list[AuditLog])
@router.get("/", include_in_schema=False)
async def list_audit_logs(
    current_user: CurrentUser,
    db: DBSession,
    limit: int = Query(default=100, ge=1, le=500),
    # Admin-only filters — ignored for non-admin users
    user_id: str | None = Query(default=None, description="Admin only: filter by user ID"),
    action: str | None = Query(default=None, description="Filter by action prefix"),
):
    is_admin = getattr(current_user, "is_admin", False)

    query = select(AuditLogModel).order_by(desc(AuditLogModel.created_at))

    if is_admin:
        # Admins can query all logs, optionally filtered by user_id or action
        if user_id:
            query = query.where(AuditLogModel.user_id == user_id)
        if action:
            query = query.where(AuditLogModel.action.startswith(action))
    else:
        # Non-admins can only see their own logs; ignore user_id filter
        if user_id and user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own audit logs",
            )
        query = query.where(AuditLogModel.user_id == current_user.id)

    query = query.limit(limit)
    result = await db.execute(query)
    rows = result.scalars().all()
    return [
        AuditLog(
            id=row.id,
            action=row.action,
            user_id=row.user_id,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            ip_address=row.ip_address,
            created_at=row.created_at,
            meta=row.meta or {},
        )
        for row in rows
    ]
