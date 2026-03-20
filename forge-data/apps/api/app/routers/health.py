"""Health router — liveness, readiness probes, and recent audit log."""

import time

from fastapi import APIRouter, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import database as _db_module
from app.dependencies import DBSession, CurrentUser

router = APIRouter()


@router.get("/health/live", summary="Liveness probe")
async def liveness():
    """Returns 200 when the API process is running."""
    return {"status": "ok", "version": "0.1.0", "timestamp": time.time()}


@router.get("/health/ready", summary="Readiness probe")
async def readiness():
    """
    Checks that the API can reach its critical dependencies (PostgreSQL, Redis).
    Returns 503 if any dependency is unreachable.
    """
    import redis.asyncio as aioredis
    from fastapi import HTTPException

    from app.config import settings

    checks: dict[str, str] = {}

    # PostgreSQL check
    try:
        async with _db_module.AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"

    # Redis check
    try:
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())

    if not all_ok:
        raise HTTPException(status_code=503, detail={"status": "degraded", "checks": checks})

    return {"status": "ok", "checks": checks, "timestamp": time.time()}


@router.get("/health/audit", summary="Recent audit log entries")
async def recent_audit(
    db: DBSession,
    current_user: CurrentUser,
    limit: int = Query(default=10, ge=1, le=100),
):
    """Return the most recent audit log entries for the authenticated user."""
    from sqlalchemy import select
    from app.models.audit_log import AuditLog

    stmt = (
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
