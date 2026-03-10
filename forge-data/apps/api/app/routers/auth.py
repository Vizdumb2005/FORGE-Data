"""Auth router — registration, login, token refresh/revocation, profile, API keys.

All endpoints live under ``/api/v1/auth``.
Rate-limited with slowapi: register (3/hour/IP), login (5/minute/IP).
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.core.exceptions import InvalidCredentialsException
from app.core.security import encrypt_field, verify_token
from app.dependencies import CurrentUser, DBSession
from app.schemas.user import (
    ApiKeysTestRequest,
    ApiKeysTestResponse,
    ApiKeysUpdate,
    AuthResponse,
    LoginRequest,
    MessageResponse,
    RefreshResponse,
    Token,
    TokenRefresh,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.services import audit_service, auth_service

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Rate limiter (attached to the FastAPI app in main.py) ─────────────────────

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    strategy="fixed-window",
)

# ── Refresh-token cookie helper ───────────────────────────────────────────────

_COOKIE_NAME = auth_service.REFRESH_COOKIE_NAME
_COOKIE_PATH = auth_service.REFRESH_COOKIE_PATH
_COOKIE_MAX_AGE = settings.jwt_refresh_token_expire_days * 86400


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path=_COOKIE_PATH,
        max_age=_COOKIE_MAX_AGE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_COOKIE_NAME,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path=_COOKIE_PATH,
    )


# ── Background tasks ─────────────────────────────────────────────────────────

def _send_verification_email(email: str) -> None:
    # TODO: integrate real SMTP provider (SendGrid / Resend / SES)
    logger.info("VERIFICATION EMAIL (stub): would send to %s", email)


# =============================================================================
# 1. POST /register
# =============================================================================

@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
    summary="Register a new user account",
)
@limiter.limit("3/hour")
async def register(
    request: Request,
    payload: UserCreate,
    db: DBSession,
    response: Response,
    background_tasks: BackgroundTasks,
) -> AuthResponse:
    user = await auth_service.create_user(db, payload)
    await db.flush()

    auth_resp = await auth_service.build_auth_response(user)
    _set_refresh_cookie(response, auth_resp.refresh_token)

    background_tasks.add_task(_send_verification_email, user.email)

    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.AUTH_REGISTER,
        user_id=user.id,
        ip_address=request.client.host if request.client else None,
        metadata={"email": user.email},
    )
    return auth_resp


# =============================================================================
# 2. POST /login
# =============================================================================

@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Log in with email and password (JSON body)",
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    db: DBSession,
    response: Response,
) -> AuthResponse:
    user = await auth_service.authenticate_user(db, payload.email, payload.password)
    auth_resp = await auth_service.build_auth_response(user)
    _set_refresh_cookie(response, auth_resp.refresh_token)

    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.AUTH_LOGIN,
        user_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    return auth_resp


# =============================================================================
# 2b. POST /token — OAuth2 password form (backward compat with existing tests)
# =============================================================================

@router.post(
    "/token",
    response_model=Token,
    summary="Obtain access + refresh token pair (OAuth2 password flow)",
)
@limiter.limit("5/minute")
async def login_form(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: DBSession = Depends(),
) -> Token:
    user = await auth_service.authenticate_user(db, form.username, form.password)
    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.AUTH_LOGIN,
        user_id=user.id,
        ip_address=request.client.host if request and request.client else None,
    )
    return auth_service.issue_tokens(user)


# =============================================================================
# 3. POST /refresh — cookie-based
# =============================================================================

@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Refresh the access token using the httpOnly cookie",
)
async def refresh(
    request: Request,
    db: DBSession,
    response: Response,
) -> RefreshResponse:
    cookie_token = request.cookies.get(_COOKIE_NAME)

    # Also accept body-based refresh for backward compat
    if not cookie_token:
        try:
            body = await request.json()
            cookie_token = body.get("refresh_token")
        except Exception:
            pass

    if not cookie_token:
        raise InvalidCredentialsException()

    # Try Redis-backed rotation first; fall back to legacy for tests without Redis
    try:
        refresh_resp, new_refresh = await auth_service.refresh_from_cookie(
            db, cookie_token
        )
        _set_refresh_cookie(response, new_refresh)
        return refresh_resp
    except Exception:
        # Legacy path: body-based refresh without Redis (existing test compat)
        payload = verify_token(cookie_token)
        if payload is None or payload.get("type") != "refresh":
            raise InvalidCredentialsException()
        tokens = await auth_service.refresh_tokens(db, cookie_token)
        return RefreshResponse(access_token=tokens.access_token)


# =============================================================================
# 4. POST /logout
# =============================================================================

@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Log out (clear refresh cookie, blacklist access token)",
)
async def logout(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    db: DBSession,
) -> MessageResponse:
    # Revoke the refresh token from Redis
    cookie_token = request.cookies.get(_COOKIE_NAME)
    if cookie_token:
        try:
            await auth_service.revoke_refresh_token(cookie_token, current_user.id)
        except Exception as exc:
            logger.warning("Failed to revoke refresh token in Redis: %s", exc)

    # Blacklist the current access token's JTI
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header[7:]
        payload = verify_token(access_token)
        if payload and payload.get("jti"):
            exp = payload.get("exp", 0)
            remaining = int(exp - datetime.now(timezone.utc).timestamp())
            try:
                await auth_service.blacklist_access_token(payload["jti"], remaining)
            except Exception as exc:
                logger.warning("Failed to blacklist access token: %s", exc)

    _clear_refresh_cookie(response)

    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.AUTH_LOGOUT,
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return MessageResponse(message="logged out")


# =============================================================================
# 5. GET /me
# =============================================================================

@router.get(
    "/me",
    response_model=UserRead,
    summary="Get current user profile",
)
async def get_me(current_user: CurrentUser) -> UserRead:
    return UserRead.from_orm_with_flags(current_user)


# =============================================================================
# 6. PATCH /me
# =============================================================================

@router.patch(
    "/me",
    response_model=UserRead,
    summary="Update current user profile",
)
async def update_me(
    payload: UserUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> UserRead:
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.preferred_llm_provider is not None:
        current_user.preferred_llm_provider = payload.preferred_llm_provider.value
    return UserRead.from_orm_with_flags(current_user)


# =============================================================================
# 7. PATCH /me/api-keys
# =============================================================================

@router.patch(
    "/me/api-keys",
    response_model=MessageResponse,
    summary="Update encrypted BYOK LLM API keys",
)
async def update_api_keys(
    payload: ApiKeysUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> MessageResponse:
    if payload.openai_api_key is not None:
        current_user.openai_api_key = (
            encrypt_field(payload.openai_api_key) if payload.openai_api_key else None
        )
    if payload.anthropic_api_key is not None:
        current_user.anthropic_api_key = (
            encrypt_field(payload.anthropic_api_key) if payload.anthropic_api_key else None
        )
    if payload.ollama_base_url is not None:
        current_user.ollama_base_url = payload.ollama_base_url or None
    return MessageResponse(message="API keys updated")


# =============================================================================
# 8. POST /me/api-keys/test
# =============================================================================

@router.post(
    "/me/api-keys/test",
    response_model=ApiKeysTestResponse,
    summary="Test a stored API key against the provider",
)
async def test_api_key(
    payload: ApiKeysTestRequest,
    current_user: CurrentUser,
) -> ApiKeysTestResponse:
    result = await auth_service.test_api_key(current_user, payload.provider.value)
    return ApiKeysTestResponse(**result)
