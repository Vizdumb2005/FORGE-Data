"""Dashboard publishing service."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, NotFoundException, ValidationError
from app.models.cell import Cell
from app.models.publishing import PublishedDashboard
from app.workers.celery_app import celery_app


class DashboardPublisher:
    """
    Publishes workspace cells as shareable, live dashboards.
    Published dashboards have a public URL with optional password protection.
    Charts re-query data on each visit if connected to a live source.
    """

    @staticmethod
    def _slug() -> str:
        return secrets.token_urlsafe(5).replace("-", "").replace("_", "")[:6].lower()

    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    async def publish_dashboard(
        self,
        workspace_id: UUID,
        user_id: UUID,
        title: str,
        cell_ids: list[UUID],
        is_public: bool = True,
        password: str | None = None,
        refresh_interval_minutes: int | None = None,
    ) -> PublishedDashboard:
        if not cell_ids:
            raise ValidationError("cell_ids must include at least one cell")
        if refresh_interval_minutes is not None and refresh_interval_minutes < 1:
            raise ValidationError("refresh_interval_minutes must be >= 1")

        result = await self._db.execute(
            select(Cell).where(
                Cell.workspace_id == str(workspace_id),
                Cell.id.in_([str(cell_id) for cell_id in cell_ids]),
            )
        )
        cells = list(result.scalars().all())
        if len(cells) != len(cell_ids):
            raise NotFoundException("Cell")

        snapshot = [
            {
                "id": cell.id,
                "cell_type": cell.cell_type,
                "language": cell.language,
                "content": cell.content,
                "output": cell.output,
                "position_x": cell.position_x,
                "position_y": cell.position_y,
                "width": cell.width,
                "height": cell.height,
                "updated_at": cell.updated_at.isoformat() if cell.updated_at else None,
            }
            for cell in cells
        ]

        slug = self._slug()
        while True:
            existing = await self._db.execute(
                select(PublishedDashboard).where(PublishedDashboard.slug == slug)
            )
            if existing.scalar_one_or_none() is None:
                break
            slug = self._slug()

        dashboard = PublishedDashboard(
            workspace_id=str(workspace_id),
            created_by=str(user_id),
            title=title,
            slug=slug,
            cell_ids=[str(cell_id) for cell_id in cell_ids],
            snapshot=snapshot,
            is_public=is_public,
            password_hash=self._hash_password(password) if password else None,
            refresh_interval_minutes=refresh_interval_minutes,
            last_refreshed_at=datetime.now(UTC),
        )
        self._db.add(dashboard)
        await self._db.flush()

        if refresh_interval_minutes is not None:
            celery_app.send_task(
                "app.workers.publish.refresh_dashboard",
                args=[dashboard.id],
            )
        return dashboard

    async def refresh_dashboard(self, dashboard_id: UUID) -> PublishedDashboard:
        dashboard = await self._db.get(PublishedDashboard, str(dashboard_id))
        if dashboard is None:
            raise NotFoundException("PublishedDashboard", str(dashboard_id))

        result = await self._db.execute(
            select(Cell).where(
                Cell.workspace_id == dashboard.workspace_id,
                Cell.id.in_(dashboard.cell_ids),
            )
        )
        cells = list(result.scalars().all())
        dashboard.snapshot = [
            {
                "id": cell.id,
                "cell_type": cell.cell_type,
                "language": cell.language,
                "content": cell.content,
                "output": cell.output,
                "position_x": cell.position_x,
                "position_y": cell.position_y,
                "width": cell.width,
                "height": cell.height,
                "updated_at": cell.updated_at.isoformat() if cell.updated_at else None,
            }
            for cell in cells
        ]
        dashboard.last_refreshed_at = datetime.now(UTC)
        await self._db.flush()
        return dashboard

    async def get_dashboard(
        self,
        slug: str,
        password: str | None = None,
    ) -> PublishedDashboard:
        result = await self._db.execute(
            select(PublishedDashboard).where(PublishedDashboard.slug == slug)
        )
        dashboard = result.scalar_one_or_none()
        if dashboard is None:
            raise NotFoundException("PublishedDashboard", slug)
        if (
            not dashboard.is_public
            and (not password or dashboard.password_hash != self._hash_password(password))
        ):
            raise ForbiddenException("Dashboard password required or invalid")
        if dashboard.password_hash and password is None:
            raise ForbiddenException("Dashboard password required")
        if (
            dashboard.password_hash
            and password is not None
            and dashboard.password_hash != self._hash_password(password)
        ):
            raise ForbiddenException("Dashboard password required or invalid")
        return dashboard

    async def unpublish(self, dashboard_id: UUID, user_id: UUID) -> None:
        dashboard = await self._db.get(PublishedDashboard, str(dashboard_id))
        if dashboard is None:
            raise NotFoundException("PublishedDashboard", str(dashboard_id))
        if dashboard.created_by and dashboard.created_by != str(user_id):
            raise ForbiddenException("Only the dashboard publisher can unpublish")
        await self._db.delete(dashboard)
        await self._db.flush()

    async def list_dashboards(self, workspace_id: UUID) -> list[PublishedDashboard]:
        result = await self._db.execute(
            select(PublishedDashboard)
            .where(PublishedDashboard.workspace_id == str(workspace_id))
            .order_by(PublishedDashboard.created_at.desc())
        )
        return list(result.scalars().all())

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
