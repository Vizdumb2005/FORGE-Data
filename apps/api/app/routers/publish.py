"""Publishing router - dashboard publishing and report export APIs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.exceptions import ForbiddenException, ValidationError
from app.core.publisher import DashboardPublisher
from app.core.report_exporter import ReportExporter
from app.dependencies import CurrentUser, DBSession, OptionalUser
from app.models.publishing import ScheduledReport
from app.services import audit_service, workspace_service

router = APIRouter()


class PublishDashboardRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    cell_ids: list[UUID] = Field(min_length=1)
    is_public: bool = True
    password: str | None = None
    refresh_interval_minutes: int | None = Field(default=None, ge=1)


class ExportRequest(BaseModel):
    format: str = Field(pattern="^(jupyter|html|pdf)$")
    cell_ids: list[UUID] = Field(min_length=1)


class ScheduleReportRequest(BaseModel):
    cell_ids: list[UUID] = Field(min_length=1)
    format: str = Field(pattern="^(html|pdf)$")
    schedule: str = Field(min_length=1)
    delivery: dict[str, Any]


@router.post(
    "/workspaces/{workspace_id}/publish",
    summary="Publish workspace cells as a shareable dashboard",
)
async def publish_dashboard(
    workspace_id: UUID,
    payload: PublishDashboardRequest,
    current_user: CurrentUser,
    db: DBSession,
    request: Request,
) -> dict[str, Any]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    publisher = DashboardPublisher(db)
    dashboard = await publisher.publish_dashboard(
        workspace_id=workspace_id,
        user_id=UUID(current_user.id),
        title=payload.title,
        cell_ids=payload.cell_ids,
        is_public=payload.is_public,
        password=payload.password,
        refresh_interval_minutes=payload.refresh_interval_minutes,
    )
    await audit_service.log_event(
        db,
        action="publish.dashboard.create",
        user_id=current_user.id,
        workspace_id=str(workspace_id),
        resource_type="published_dashboard",
        resource_id=dashboard.id,
        ip_address=request.client.host if request.client else None,
        metadata={"slug": dashboard.slug, "cell_count": len(payload.cell_ids)},
    )
    return {
        "slug": dashboard.slug,
        "url": f"/d/{dashboard.slug}",
        "dashboard": {
            "id": dashboard.id,
            "title": dashboard.title,
            "workspace_id": dashboard.workspace_id,
            "is_public": dashboard.is_public,
            "refresh_interval_minutes": dashboard.refresh_interval_minutes,
            "created_at": dashboard.created_at,
        },
    }


@router.get(
    "/d/{slug}",
    summary="Public dashboard endpoint",
)
async def get_public_dashboard(
    slug: str,
    db: DBSession,
    current_user: OptionalUser = None,
    password: str | None = Query(default=None),
) -> dict[str, Any]:
    publisher = DashboardPublisher(db)
    dashboard = await publisher.get_dashboard(slug, password=password)
    if not dashboard.is_public and current_user is None and password is None:
        raise ForbiddenException("This dashboard is private")
    return {
        "id": dashboard.id,
        "slug": dashboard.slug,
        "title": dashboard.title,
        "workspace_id": dashboard.workspace_id,
        "snapshot": dashboard.snapshot,
        "last_refreshed_at": dashboard.last_refreshed_at,
    }


@router.post(
    "/workspaces/{workspace_id}/export",
    summary="Export selected workspace cells",
)
async def export_workspace(
    workspace_id: UUID,
    payload: ExportRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> Response:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    exporter = ReportExporter(db)
    fmt = payload.format.lower()
    if fmt == "jupyter":
        data = await exporter.export_jupyter(workspace_id, payload.cell_ids)
        filename = f"forge-{workspace_id}.ipynb"
        media_type = "application/x-ipynb+json"
    elif fmt == "html":
        data = await exporter.export_html(workspace_id, payload.cell_ids)
        filename = f"forge-{workspace_id}.html"
        media_type = "text/html; charset=utf-8"
    elif fmt == "pdf":
        data = await exporter.export_pdf(workspace_id, payload.cell_ids)
        filename = f"forge-{workspace_id}.pdf"
        media_type = "application/pdf"
    else:
        raise ValidationError("format must be one of: jupyter, html, pdf")

    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/workspaces/{workspace_id}/schedule-report",
    summary="Schedule recurring report delivery",
)
async def schedule_report(
    workspace_id: UUID,
    payload: ScheduleReportRequest,
    current_user: CurrentUser,
    db: DBSession,
    request: Request,
) -> dict[str, Any]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    exporter = ReportExporter(db)
    report = await exporter.schedule_report(
        workspace_id=workspace_id,
        created_by=UUID(current_user.id),
        cell_ids=payload.cell_ids,
        format=payload.format,
        schedule=payload.schedule,
        delivery=payload.delivery,
    )
    await audit_service.log_event(
        db,
        action="publish.report.schedule",
        user_id=current_user.id,
        workspace_id=str(workspace_id),
        resource_type="scheduled_report",
        resource_id=report.id,
        ip_address=request.client.host if request.client else None,
        metadata={"format": report.format, "schedule": report.cron_expression},
    )
    return {
        "id": report.id,
        "workspace_id": report.workspace_id,
        "format": report.format,
        "schedule": report.cron_expression,
        "delivery": report.delivery,
        "is_active": report.is_active,
    }


@router.get(
    "/workspaces/{workspace_id}/published",
    summary="List published dashboards and scheduled reports",
)
async def list_published(
    workspace_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
) -> dict[str, Any]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    publisher = DashboardPublisher(db)
    dashboards = await publisher.list_dashboards(workspace_id)
    report_result = await db.execute(
        select(ScheduledReport)
        .where(ScheduledReport.workspace_id == str(workspace_id))
        .order_by(ScheduledReport.created_at.desc())
    )
    reports = list(report_result.scalars().all())
    return {
        "dashboards": [
            {
                "id": d.id,
                "slug": d.slug,
                "title": d.title,
                "is_public": d.is_public,
                "refresh_interval_minutes": d.refresh_interval_minutes,
                "created_at": d.created_at,
            }
            for d in dashboards
        ],
        "scheduled_reports": [
            {
                "id": r.id,
                "format": r.format,
                "schedule": r.cron_expression,
                "delivery": r.delivery,
                "is_active": r.is_active,
                "created_at": r.created_at,
            }
            for r in reports
        ],
    }


@router.delete(
    "/workspaces/{workspace_id}/published/{dashboard_id}",
    status_code=200,
    summary="Unpublish dashboard",
)
async def unpublish_dashboard(
    workspace_id: UUID,
    dashboard_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
    request: Request,
) -> dict[str, str]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    publisher = DashboardPublisher(db)
    await publisher.unpublish(dashboard_id, UUID(current_user.id))
    await audit_service.log_event(
        db,
        action="publish.dashboard.delete",
        user_id=current_user.id,
        workspace_id=str(workspace_id),
        resource_type="published_dashboard",
        resource_id=str(dashboard_id),
        ip_address=request.client.host if request.client else None,
    )
    return {"status": "ok"}


@router.post("/internal/published/{dashboard_id}/refresh", include_in_schema=False)
async def internal_refresh_dashboard(dashboard_id: UUID, db: DBSession) -> dict[str, str]:
    publisher = DashboardPublisher(db)
    dashboard = await publisher.refresh_dashboard(dashboard_id)
    return {"status": "ok", "dashboard_id": dashboard.id}

