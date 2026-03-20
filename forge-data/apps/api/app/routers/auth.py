"""Auth router — registration, login, token refresh/revocation, profile, API keys.

All endpoints live under ``/api/v1/auth``.
Rate-limited with slowapi: register (3/hour/IP), login (5/minute/IP).
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.core.exceptions import InvalidCredentialsException
from app.core.llm_provider import ProviderRegistry
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
    RegisterResponse,
    Token,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.services import audit_service, auth_service

logger = logging.getLogger(__name__)

router = APIRouter()
provider_registry = ProviderRegistry()

# ── Rate limiter (attached to the FastAPI app in main.py) ─────────────────────

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    strategy="fixed-window",
    enabled=settings.app_env != "test",
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
    response_model=RegisterResponse,
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
) -> RegisterResponse:
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

    # Convert AuthResponse to RegisterResponse (flattened structure)
    user_read = UserRead.from_orm_with_flags(user)
    return RegisterResponse(
        **user_read.model_dump(),
        access_token=auth_resp.access_token,
        refresh_token=auth_resp.refresh_token,
    )


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
    db: DBSession = ...,
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

    # Validate the token is actually a refresh token before proceeding
    pre_payload = verify_token(cookie_token)
    if pre_payload is None or pre_payload.get("type") != "refresh":
        raise InvalidCredentialsException()

    # Try Redis-backed rotation first; fall back to legacy for tests without Redis
    try:
        refresh_resp, new_refresh = await auth_service.refresh_from_cookie(db, cookie_token)
        _set_refresh_cookie(response, new_refresh)
        return RefreshResponse(
            access_token=refresh_resp.access_token,
            refresh_token=new_refresh,
        )
    except Exception:
        # Legacy path: body-based refresh without Redis (existing test compat)
        tokens = await auth_service.refresh_tokens(db, cookie_token)
        return RefreshResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        )


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
            remaining = int(exp - datetime.now(UTC).timestamp())
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
        selected = payload.preferred_llm_provider.lower()
        if selected not in provider_registry.providers:
            selected = provider_registry.default_provider
        current_user.preferred_llm_provider = selected
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
    if payload.provider_api_keys is not None:
        existing = current_user.llm_api_keys or {}
        for provider_id, raw_key in payload.provider_api_keys.items():
            key = provider_id.lower()
            if key not in provider_registry.providers:
                continue
            if raw_key:
                existing[key] = encrypt_field(raw_key)
            else:
                existing.pop(key, None)
        current_user.llm_api_keys = existing
    if payload.provider_settings is not None:
        existing_settings = current_user.llm_provider_config or {}
        for provider_id, provider_config in payload.provider_settings.items():
            key = provider_id.lower()
            if key not in provider_registry.providers:
                continue
            if not isinstance(provider_config, dict):
                continue
            merged = dict(existing_settings.get(key, {}))
            merged.update(provider_config)
            existing_settings[key] = merged
        current_user.llm_provider_config = existing_settings
    if payload.provider_settings and payload.provider_settings.get("ollama", {}).get("base_url"):
        current_user.ollama_base_url = payload.provider_settings["ollama"]["base_url"] or None
    return MessageResponse(message="API keys updated")


@router.get(
    "/me/provider-config",
    summary="Get universal provider JSON configuration for editing",
)
async def get_provider_config(current_user: CurrentUser) -> dict:
    providers = provider_registry.list_for_user(current_user)
    provider_keys = current_user.llm_api_keys or {}
    provider_settings = current_user.llm_provider_config or {}
    global_settings = (
        provider_settings.get("__settings__", {})
        if isinstance(provider_settings, dict)
        else {}
    )
    if not isinstance(global_settings, dict):
        global_settings = {}

    config_payload: dict[str, dict] = {}
    for provider in providers:
        provider_id = provider["id"]
        p_settings = (
            provider_settings.get(provider_id, {})
            if isinstance(provider_settings, dict)
            else {}
        )
        if not isinstance(p_settings, dict):
            p_settings = {}
        config_payload[provider_id] = {
            "api_key": "[[ENCRYPTED_EXISTS]]" if provider_keys.get(provider_id) else "",
            "default_model": p_settings.get("default_model", provider["default_model"]),
            "base_url": p_settings.get("base_url", ""),
            "model_path": p_settings.get("model_path", ""),
            "params": p_settings.get("runtime_options", {}),
        }

    local_candidate = "ollama" if "ollama" in config_payload else ""
    return {
        "providers": config_payload,
        "settings": {
            "active_provider": current_user.preferred_llm_provider or local_candidate,
            "fallback_order": global_settings.get(
                "fallback_order",
                [p["id"] for p in providers if p.get("local")]
                + [p["id"] for p in providers if not p.get("local")],
            ),
            "timeout": int(global_settings.get("timeout", 30)),
            "retry_attempts": int(global_settings.get("retry_attempts", 3)),
        },
    }


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
    result = await auth_service.test_api_key(current_user, payload.provider)
    return ApiKeysTestResponse(**result)
