"""Shared FastAPI dependencies injected via Depends()."""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app import database as _db_module
from app.config import Settings, get_settings
from app.core.security import verify_token

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)
oauth2_scheme_required = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


# ── Database dependency ────────────────────────────────────────────────────────


async def get_db() -> AsyncSession:  # type: ignore[return]
    """Yield an async SQLAlchemy session, committing on success or rolling back on error."""
    async with _db_module.AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Settings dependency ────────────────────────────────────────────────────────


def get_app_settings() -> Settings:
    return get_settings()


# ── Auth dependencies ─────────────────────────────────────────────────────────


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme_required)],
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Decode the JWT bearer token, check the Redis blacklist, return the authenticated User."""
    from app.models.user import User  # local import to avoid circular deps

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    access_token = token or request.cookies.get("forge_access_token")
    if not access_token:
        raise credentials_exc

    payload = verify_token(access_token)
    if payload is None:
        raise credentials_exc

    user_id: str | None = payload.get("sub")
    token_type: str | None = payload.get("type")

    if not user_id or token_type != "access":
        raise credentials_exc

    # ── Redis blacklist check ─────────────────────────────────────────────
    jti: str | None = payload.get("jti")
    if jti:
        try:
            from app.services.auth_service import is_access_token_blacklisted

            if await is_access_token_blacklisted(jti):
                raise credentials_exc
        except ImportError:
            logger.error("Redis blacklist check module unavailable")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            ) from None
        except HTTPException:
            raise  # re-raise credentials_exc from blacklist check
        except Exception as exc:
            from app.config import settings as _s
            if _s.is_production:
                # Fail closed in production: Redis down = deny access
                # This prevents revoked tokens from being reused during outages.
                logger.error("Redis blacklist check failed (failing closed): %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service temporarily unavailable",
                ) from exc
            logger.error("Redis blacklist check failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            ) from exc

    user = await db.get(User, user_id)
    if user is None:
        raise credentials_exc

    return user


async def get_current_active_user(current_user=Depends(get_current_user)):
    """Raise 403 if the user is deactivated."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )
    return current_user


async def get_optional_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Like get_current_user but returns None when no token is present (public endpoints)."""
    access_token = token or request.cookies.get("forge_access_token")
    if not access_token:
        return None

    from app.models.user import User  # local import

    payload = verify_token(access_token)
    if payload is None:
        return None

    user_id: str | None = payload.get("sub")
    if not user_id:
        return None

    return await db.get(User, user_id)


# ── RBAC dependency factory ──────────────────────────────────────────────────


def require_workspace_role(*roles: str):
    """Return a FastAPI dependency that checks workspace membership and role.

    Usage::

        @router.patch("/{workspace_id}")
        async def update_workspace(
            data: WorkspaceUpdate,
            workspace: Workspace = Depends(require_workspace_role("editor", "admin")),
            ...
        ):

    The dependency:
    - Resolves ``workspace_id`` from the path parameter.
    - Verifies the current user is a member with one of the specified *roles*.
    - The workspace owner is always treated as ``admin``.
    - Returns the :class:`Workspace` ORM object on success.
    - Raises 404 if workspace not found, 403 if insufficient role.
    """

    async def _check(
        workspace_id: str,
        current_user=Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ):
        from app.services.workspace_service import check_workspace_role  # local import

        return await check_workspace_role(db, workspace_id, current_user.id, roles)

    return _check


# ── Query engine dependency ───────────────────────────────────────────────────


async def get_query_engine(request: Request):
    """Return the FederatedQueryEngine singleton from app state."""
    return request.app.state.query_engine


# ── Kernel manager dependency ────────────────────────────────────────────────


async def get_kernel_manager(request: Request):
    """Return the KernelManager singleton from app state."""
    return request.app.state.kernel_manager


# ── Convenience type aliases (for endpoint signatures) ─────────────────────────

DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[object, Depends(get_current_active_user)]
OptionalUser = Annotated[object | None, Depends(get_optional_user)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
QueryEngine = Annotated[object, Depends(get_query_engine)]
KernelMgr = Annotated[object, Depends(get_kernel_manager)]
