"""FORGE Data API — FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.config import settings
from app.core.exceptions import ForgeException
from app.core.experiment_tracker import ExperimentTracker
from app.core.kernel_manager import KernelManager
from app.core.middleware import AuditMiddleware, RequestLoggingMiddleware
from app.core.query_engine import FederatedQueryEngine
from app.core.redis import close_redis, ping_redis
from app.routers import (
    ai,
    audit,
    auth,
    cells,
    connectors,
    datasets,
    execute,
    experiments,
    health,
    publish,
    setup,
    users,
    workspaces,
)

logger = logging.getLogger(__name__)
_experiment_tracker = ExperimentTracker()

logging.basicConfig(
    level=logging.DEBUG if settings.is_development else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)


# ── Startup / shutdown ────────────────────────────────────────────────────────


async def _check_database() -> None:
    from app.database import engine

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection OK")
    except Exception as exc:
        logger.error("Database connection FAILED: %s", exc)


async def _ensure_minio_bucket() -> None:
    try:
        from minio import Minio
        from minio.error import S3Error  # noqa: F401

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_use_ssl,
        )
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
            logger.info("Created MinIO bucket: %s", settings.minio_bucket)
        else:
            logger.info("MinIO bucket present: %s", settings.minio_bucket)
    except Exception as exc:
        logger.warning("MinIO initialisation warning (non-fatal): %s", exc)


async def _check_redis() -> None:
    ok = await ping_redis()
    if ok:
        logger.info("Redis connection OK")
    else:
        logger.warning("Redis connection FAILED (rate limiting and token revocation may not work)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting FORGE Data API v%s", app.version)
    await _check_database()
    await _ensure_minio_bucket()
    await _check_redis()

    # Initialise the federated query engine
    query_engine = FederatedQueryEngine()
    app.state.query_engine = query_engine
    logger.info("DuckDB query engine initialised")

    # Initialise the kernel manager (Jupyter Kernel Gateway)
    kernel_manager = KernelManager()
    app.state.kernel_manager = kernel_manager
    logger.info("Kernel manager initialised")

    # Background task: evict idle DuckDB connections every 5 minutes
    async def _idle_cleanup_loop() -> None:
        while True:
            await asyncio.sleep(300)
            try:
                await query_engine.cleanup_idle()
            except Exception as exc:
                logger.warning("DuckDB idle cleanup error: %s", exc)

    # Background task: evict idle kernels every 10 minutes
    async def _kernel_cleanup_loop() -> None:
        while True:
            await asyncio.sleep(600)
            try:
                evicted = await kernel_manager.cleanup_idle()
                if evicted:
                    logger.info("Evicted %d idle kernel(s)", evicted)
            except Exception as exc:
                logger.warning("Kernel idle cleanup error: %s", exc)

    cleanup_task = asyncio.create_task(_idle_cleanup_loop())
    kernel_cleanup_task = asyncio.create_task(_kernel_cleanup_loop())

    yield

    # Shutdown
    cleanup_task.cancel()
    kernel_cleanup_task.cancel()
    await kernel_manager.shutdown_all()
    await query_engine.close_all()
    await close_redis()
    logger.info("FORGE Data API shutdown complete")


# ── Application factory ────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(
        title="FORGE Data API",
        description=(
            "Self-hosted data intelligence platform. "
            "Interactive data grids, conversational AI analysis, BYOK LLM support."
        ),
        version="0.1.0",
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None if settings.is_production else "/api/redoc",
        openapi_url=None if settings.is_production else "/api/openapi.json",
        lifespan=lifespan,
    )

    # ── Rate limiter (slowapi) ────────────────────────────────────────────
    app.state.limiter = auth.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── Middleware (order matters — outermost runs first on request) ───────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Accept"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
    )
    if settings.app_env != "test":
        app.add_middleware(RequestLoggingMiddleware)
        app.add_middleware(AuditMiddleware)

    # ── Exception handlers ─────────────────────────────────────────────────
    @app.exception_handler(ForgeException)
    async def forge_exception_handler(request: Request, exc: ForgeException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code},
        )

    # ── Top-level health endpoint (no auth required) ───────────────────────
    @app.get(
        "/api/health",
        tags=["health"],
        summary="API liveness probe",
        response_description="Returns 200 when the API process is alive",
    )
    async def root_health():
        return {"status": "ok", "version": app.version}

    @app.get(
        "/api/mlflow/experiments/list",
        tags=["experiments"],
        summary="MLflow experiments list compatibility endpoint",
    )
    async def mlflow_experiments_list_compat():
        experiments = _experiment_tracker._client.search_experiments(max_results=1000)
        return {
            "experiments": [
                {
                    "experiment_id": exp.experiment_id,
                    "name": exp.name,
                    "artifact_location": exp.artifact_location,
                    "lifecycle_stage": exp.lifecycle_stage,
                    "creation_time": exp.creation_time,
                    "last_update_time": exp.last_update_time,
                }
                for exp in experiments
            ]
        }

    # ── Routers ────────────────────────────────────────────────────────────
    v1 = "/api/v1"
    app.include_router(health.router, prefix=v1, tags=["health"])
    app.include_router(auth.router, prefix=f"{v1}/auth", tags=["auth"])
    app.include_router(users.router, prefix=f"{v1}/users", tags=["users"])
    app.include_router(workspaces.router, prefix=f"{v1}/workspaces", tags=["workspaces"])
    app.include_router(datasets.router, prefix=v1, tags=["datasets"])
    app.include_router(cells.router, prefix=f"{v1}/workspaces", tags=["cells"])
    app.include_router(execute.router, prefix=f"{v1}/workspaces", tags=["execute"])
    app.include_router(ai.router, prefix=f"{v1}/ai", tags=["ai"])
    app.include_router(connectors.router, prefix=f"{v1}/connectors", tags=["connectors"])
    app.include_router(experiments.router, prefix=f"{v1}/experiments", tags=["experiments"])
    app.include_router(publish.router, prefix=v1, tags=["publishing"])
    app.include_router(audit.router, prefix=f"{v1}/audit", tags=["audit"])
    app.include_router(setup.router, prefix=f"{v1}/setup", tags=["setup"])

    return app


app = create_app()
