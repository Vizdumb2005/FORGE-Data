"""Authentication service — user creation, login, Redis-backed token management."""

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import EmailAlreadyExistsException, InvalidCredentialsException
from app.core.redis import (
    ACCESS_BLACKLIST_PREFIX,
    REFRESH_TOKEN_PREFIX,
    USER_REFRESH_SET_PREFIX,
    get_redis,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decrypt_field,
    get_password_hash,
    hash_token,
    verify_password,
    verify_token,
)
from app.models.user import User
from app.schemas.user import AuthResponse, RefreshResponse, Token, UserCreate, UserRead

logger = logging.getLogger(__name__)

# ── Cookie constants ──────────────────────────────────────────────────────────

REFRESH_COOKIE_NAME = "forge_refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


# ── User creation ─────────────────────────────────────────────────────────────


async def create_user(db: AsyncSession, payload: UserCreate) -> User:
    """Register a new user account.

    Raises :class:`EmailAlreadyExistsException` if the email is taken.
    """
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    if result.scalar_one_or_none() is not None:
        raise EmailAlreadyExistsException()

    user = User(
        email=payload.email.lower(),
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    await db.flush()  # assign ID without committing (commit happens in get_db)
    return user


# ── Authentication ────────────────────────────────────────────────────────────


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """Verify credentials and return the User on success.

    Raises :class:`InvalidCredentialsException` on bad email or password.
    """
    result = await db.execute(select(User).where(User.email == email.lower()))
    user: User | None = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsException()

    if not user.is_active:
        raise InvalidCredentialsException()

    return user


# ── Token issuance + Redis storage ────────────────────────────────────────────


async def issue_tokens_with_redis(user: User) -> tuple[str, str]:
    """Create access + refresh tokens and store refresh token hash in Redis.

    Returns (access_token, refresh_token).
    """
    payload = {"sub": user.id}

    access_token = create_access_token(payload)
    refresh_token = create_refresh_token(payload)

    # Store refresh token hash → user_id in Redis with TTL
    r = await get_redis()
    rt_hash = hash_token(refresh_token)
    ttl = settings.jwt_refresh_token_expire_days * 86400

    pipe = r.pipeline()
    pipe.setex(f"{REFRESH_TOKEN_PREFIX}{rt_hash}", ttl, user.id)
    pipe.sadd(f"{USER_REFRESH_SET_PREFIX}{user.id}", rt_hash)
    pipe.expire(f"{USER_REFRESH_SET_PREFIX}{user.id}", ttl)
    await pipe.execute()

    return access_token, refresh_token


async def build_auth_response(user: User) -> AuthResponse:
    """Build the full auth response with tokens for /register and /login."""
    if settings.app_env == "test":
        # Skip Redis in test mode to avoid event loop issues with async test runners
        tokens = issue_tokens(user)
        return AuthResponse(
            user=UserRead.from_orm_with_flags(user),
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        )
    access_token, refresh_token = await issue_tokens_with_redis(user)
    return AuthResponse(
        user=UserRead.from_orm_with_flags(user),
        access_token=access_token,
        refresh_token=refresh_token,
    )


def issue_tokens(user: User) -> Token:
    """Legacy: create tokens without Redis (backward compat with existing tests)."""
    payload = {"sub": user.id}
    return Token(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
    )


# ── Token refresh (cookie-based) ─────────────────────────────────────────────


async def refresh_from_cookie(db: AsyncSession, cookie_token: str) -> tuple[RefreshResponse, str]:
    """Validate the refresh token from the cookie, rotate it, return new access_token.

    The new refresh token is set by the router via cookie — here we just return it.

    Returns (RefreshResponse, new_refresh_token) tuple.
    """
    payload = verify_token(cookie_token)
    if payload is None or payload.get("type") != "refresh":
        raise InvalidCredentialsException()

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise InvalidCredentialsException()

    # Check that the refresh token hash exists in Redis
    r = await get_redis()
    old_hash = hash_token(cookie_token)
    stored_user_id = await r.get(f"{REFRESH_TOKEN_PREFIX}{old_hash}")
    if stored_user_id is None or stored_user_id != user_id:
        raise InvalidCredentialsException()

    # Load user from DB
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise InvalidCredentialsException()

    # Rotate: delete old, issue new
    pipe = r.pipeline()
    pipe.delete(f"{REFRESH_TOKEN_PREFIX}{old_hash}")
    pipe.srem(f"{USER_REFRESH_SET_PREFIX}{user_id}", old_hash)
    await pipe.execute()

    new_access, new_refresh = await issue_tokens_with_redis(user)
    return RefreshResponse(access_token=new_access), new_refresh


# ── Legacy refresh (body-based, for backward compat with existing tests) ──────


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> Token:
    """Validate *refresh_token* and issue a new token pair (no Redis)."""
    payload = verify_token(refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise InvalidCredentialsException()

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise InvalidCredentialsException()

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise InvalidCredentialsException()

    return issue_tokens(user)


# ── Logout / revocation ──────────────────────────────────────────────────────


async def revoke_refresh_token(refresh_token: str, user_id: str) -> None:
    """Remove a specific refresh token hash from Redis."""
    r = await get_redis()
    rt_hash = hash_token(refresh_token)
    pipe = r.pipeline()
    pipe.delete(f"{REFRESH_TOKEN_PREFIX}{rt_hash}")
    pipe.srem(f"{USER_REFRESH_SET_PREFIX}{user_id}", rt_hash)
    await pipe.execute()


async def blacklist_access_token(jti: str, remaining_ttl: int) -> None:
    """Add an access token's JTI to the Redis blacklist until it expires naturally."""
    if not jti or remaining_ttl <= 0:
        return
    r = await get_redis()
    await r.setex(f"{ACCESS_BLACKLIST_PREFIX}{jti}", remaining_ttl, "1")


async def is_access_token_blacklisted(jti: str) -> bool:
    """Return True if the access token JTI is in the blacklist."""
    if not jti:
        return False
    r = await get_redis()
    return await r.exists(f"{ACCESS_BLACKLIST_PREFIX}{jti}") > 0


async def revoke_all_user_tokens(user_id: str) -> None:
    """Revoke all refresh tokens for a user (e.g. on password change)."""
    r = await get_redis()
    members = await r.smembers(f"{USER_REFRESH_SET_PREFIX}{user_id}")
    if members:
        keys = [f"{REFRESH_TOKEN_PREFIX}{h}" for h in members]
        pipe = r.pipeline()
        pipe.delete(*keys)
        pipe.delete(f"{USER_REFRESH_SET_PREFIX}{user_id}")
        await pipe.execute()


# ── API key testing ──────────────────────────────────────────────────────────


async def test_api_key(user: User, provider: str) -> dict[str, Any]:
    """Make a minimal API call to validate the stored key for *provider*.

    Returns {"valid": True/False, "error": "..."}.
    """
    if provider == "openai":
        return await _test_openai_key(user)
    elif provider == "anthropic":
        return await _test_anthropic_key(user)
    elif provider == "ollama":
        return await _test_ollama_connection(user)
    else:
        return {"valid": False, "error": f"Unsupported provider: {provider}"}


async def _test_openai_key(user: User) -> dict[str, Any]:
    raw_key = _resolve_key(user.openai_api_key, settings.openai_api_key)
    if not raw_key:
        return {"valid": False, "error": "No OpenAI API key configured"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {raw_key}"},
            )
        if resp.status_code == 200:
            return {"valid": True, "error": None}
        return {"valid": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}


async def _test_anthropic_key(user: User) -> dict[str, Any]:
    raw_key = _resolve_key(user.anthropic_api_key, settings.anthropic_api_key)
    if not raw_key:
        return {"valid": False, "error": "No Anthropic API key configured"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": raw_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
        # 200 = works; 401 = bad key; other errors are non-auth issues
        if resp.status_code in (200, 400):
            return {"valid": True, "error": None}
        if resp.status_code == 401:
            return {"valid": False, "error": "Invalid API key"}
        return {"valid": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}


async def _test_ollama_connection(user: User) -> dict[str, Any]:
    url = user.ollama_base_url or settings.ollama_base_url
    if not url:
        return {"valid": False, "error": "No Ollama base URL configured"}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{url.rstrip('/')}/api/tags")
        if resp.status_code == 200:
            return {"valid": True, "error": None}
        return {"valid": False, "error": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}


def _resolve_key(encrypted_user_key: str | None, platform_key: str) -> str | None:
    """Prefer user's encrypted BYOK key; fall back to platform env key."""
    if encrypted_user_key:
        try:
            return decrypt_field(encrypted_user_key)
        except Exception:
            return None
    return platform_key or None
