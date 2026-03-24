import csv
import io
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, or_, select

from app.dependencies import CurrentUser, DBSession
from app.models.audit_log import AuditLog as AuditLogModel
from app.models.user import User
from app.services import workspace_service

router = APIRouter()


class AuditLogRead(BaseModel):
    id: str
    action: str
    user_id: str | None
    user_name: str | None
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    created_at: datetime
    metadata: dict


class AuditPage(BaseModel):
    items: list[AuditLogRead]
    total: int
    page: int
    limit: int


@router.get("/audit", response_model=list[AuditLogRead])
@router.get("/audit/", include_in_schema=False)
async def list_my_audit_logs(
    current_user: CurrentUser,
    db: DBSession,
    limit: int = Query(default=100, ge=1, le=500),
):
    query = (
        select(AuditLogModel, User.full_name, User.email)
        .select_from(AuditLogModel)
        .outerjoin(User, User.id == AuditLogModel.user_id)
        .where(
            or_(
                AuditLogModel.user_id == current_user.id,
                AuditLogModel.user_id.is_(None),
            )
        )
        .order_by(desc(AuditLogModel.created_at))
        .limit(limit)
    )
    rows = (await db.execute(query)).all()
    return [
        AuditLogRead(
            id=row.id,
            action=row.action,
            user_id=row.user_id,
            user_name=full_name or email,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            ip_address=row.ip_address,
            created_at=row.created_at,
            metadata=row.meta or {},
        )
        for row, full_name, email in rows
    ]


def _apply_audit_filters(
    query,
    *,
    workspace_id: str,
    user_id: str | None,
    action: str | None,
    resource_type: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
):
    filters = [AuditLogModel.workspace_id == workspace_id]
    if user_id:
        filters.append(AuditLogModel.user_id == user_id)
    if action:
        filters.append(AuditLogModel.action.ilike(f"%{action}%"))
    if resource_type:
        filters.append(AuditLogModel.resource_type == resource_type)
    if start_date:
        filters.append(AuditLogModel.created_at >= start_date)
    if end_date:
        filters.append(AuditLogModel.created_at <= end_date)
    return query.where(and_(*filters))


@router.get("/workspaces/{workspace_id}/audit", response_model=AuditPage)
async def list_audit_logs(
    workspace_id: str,
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    user_id: str | None = Query(default=None, description="Admin only: filter by user ID"),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
):
    await workspace_service.check_workspace_role(db, workspace_id, current_user.id, ("admin",))

    rows_q = (
        select(AuditLogModel, User.full_name, User.email)
        .select_from(AuditLogModel)
        .outerjoin(User, User.id == AuditLogModel.user_id)
    )
    rows_q = _apply_audit_filters(
        rows_q,
        workspace_id=workspace_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        start_date=start_date,
        end_date=end_date,
    ).order_by(desc(AuditLogModel.created_at))

    total_q = select(func.count()).select_from(AuditLogModel)
    total_q = _apply_audit_filters(
        total_q,
        workspace_id=workspace_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        start_date=start_date,
        end_date=end_date,
    )

    offset = (page - 1) * limit
    rows_result = await db.execute(rows_q.offset(offset).limit(limit))
    total = (await db.execute(total_q)).scalar_one()

    items: list[AuditLogRead] = []
    for row, full_name, email in rows_result.all():
        items.append(
            AuditLogRead(
                id=row.id,
                action=row.action,
                user_id=row.user_id,
                user_name=full_name or email,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                ip_address=row.ip_address,
                created_at=row.created_at,
                metadata=row.meta or {},
            )
        )
    return AuditPage(items=items, total=total, page=page, limit=limit)


@router.get("/workspaces/{workspace_id}/audit/export")
async def export_audit_logs_csv(
    workspace_id: str,
    current_user: CurrentUser,
    db: DBSession,
    user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
):
    await workspace_service.check_workspace_role(db, workspace_id, current_user.id, ("admin",))

    query = (
        select(AuditLogModel, User.full_name, User.email)
        .select_from(AuditLogModel)
        .outerjoin(User, User.id == AuditLogModel.user_id)
    )
    query = _apply_audit_filters(
        query,
        workspace_id=workspace_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        start_date=start_date,
        end_date=end_date,
    ).order_by(desc(AuditLogModel.created_at))
    rows = (await db.execute(query)).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "created_at",
            "action",
            "workspace_id",
            "user_id",
            "user_name",
            "resource_type",
            "resource_id",
            "ip_address",
            "metadata",
        ]
    )
    for row, full_name, email in rows:
        writer.writerow(
            [
                row.id,
                row.created_at.isoformat() if row.created_at else "",
                row.action,
                row.workspace_id,
                row.user_id,
                full_name or email or "",
                row.resource_type or "",
                row.resource_id or "",
                row.ip_address or "",
                (row.meta or {}),
            ]
        )
    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="audit_{workspace_id}.csv"'}
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers=headers)
