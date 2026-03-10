import time

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    timestamp: float
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness probe — returns 200 when the API is up."""
    return HealthResponse(
        status="ok",
        timestamp=time.time(),
        version="0.1.0",
    )


@router.get("/health/ready", response_model=HealthResponse)
async def readiness_check() -> HealthResponse:
    """Readiness probe — checks dependent services."""
    # TODO: add DB and Redis ping checks
    return HealthResponse(
        status="ok",
        timestamp=time.time(),
        version="0.1.0",
    )
