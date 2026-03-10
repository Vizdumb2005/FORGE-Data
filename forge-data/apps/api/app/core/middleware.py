"""ASGI middleware — request logging and audit trail."""

import asyncio
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.security import verify_token

logger = logging.getLogger(__name__)

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_SKIP_AUDIT_PATHS = frozenset({"/api/health", "/api/v1/health", "/api/docs", "/api/redoc"})


def _get_client_ip(request: Request) -> str:
    """Extract client IP from X-Forwarded-For or fall back to direct connection."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _extract_user_id(request: Request) -> str | None:
    """Decode JWT from Authorization header without raising on failure."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.removeprefix("Bearer ").strip()
    payload = verify_token(token)
    if payload:
        return payload.get("sub")
    return None


# ── Request Logging Middleware ─────────────────────────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status code, and duration."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        # Attach request_id so route handlers can reference it
        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "[%s] %s %s → %d  (%.1f ms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration_ms:.1f}ms"
        return response


# ── Audit Logging Middleware ───────────────────────────────────────────────────

class AuditMiddleware(BaseHTTPMiddleware):
    """
    Capture every mutating request and write an AuditLog row.

    The DB write happens in a background task so it never delays the response.
    Failures in the background task are logged but not surfaced to the client.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if (
            request.method in _MUTATING_METHODS
            and request.url.path not in _SKIP_AUDIT_PATHS
            and not request.url.path.startswith("/api/docs")
        ):
            user_id = _extract_user_id(request)
            ip_address = _get_client_ip(request)
            action = f"{request.method.lower()}.{request.url.path.strip('/').replace('/', '.')}"

            asyncio.ensure_future(
                self._write_audit_log(
                    user_id=user_id,
                    action=action,
                    ip_address=ip_address,
                    method=request.method,
                    path=str(request.url.path),
                    status_code=response.status_code,
                )
            )

        return response

    @staticmethod
    async def _write_audit_log(
        *,
        user_id: str | None,
        action: str,
        ip_address: str,
        method: str,
        path: str,
        status_code: int,
    ) -> None:
        try:
            from app.database import AsyncSessionLocal
            from app.models.audit_log import AuditLog

            async with AsyncSessionLocal() as session:
                log = AuditLog(
                    user_id=user_id,
                    action=action,
                    ip_address=ip_address,
                    metadata={
                        "method": method,
                        "path": path,
                        "status_code": status_code,
                    },
                )
                session.add(log)
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to write audit log: %s", exc)
