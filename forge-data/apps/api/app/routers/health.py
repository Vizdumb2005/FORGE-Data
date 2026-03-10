"""Health router — liveness and readiness probes."""

import time

from fastapi import APIRouter
from sqlalchemy import text

from app.database import AsyncSessionLocal

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
    from fastapi import HTTPException
    import redis.asyncio as aioredis
    from app.config import settings

    checks: dict[str, str] = {}

    # PostgreSQL check
    try:
        async with AsyncSessionLocal() as session:
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
