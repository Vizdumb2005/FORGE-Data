"""Async Redis client for token storage, blacklisting, and rate limiting."""

import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

# ── Connection pool (initialised once at import time) ─────────────────────────

_pool: aioredis.ConnectionPool | None = None
_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared async Redis client, creating it lazily on first call."""
    global _pool, _client  # noqa: PLW0603
    if _client is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=20,
            decode_responses=True,
        )
        _client = aioredis.Redis(connection_pool=_pool)
    return _client


async def close_redis() -> None:
    """Shut down the Redis connection pool (call during app shutdown)."""
    global _pool, _client  # noqa: PLW0603
    if _client is not None:
        await _client.aclose()
        _client = None
    if _pool is not None:
        await _pool.disconnect()
        _pool = None


async def ping_redis() -> bool:
    """Return True if Redis responds to PING."""
    try:
        r = await get_redis()
        return await r.ping()
    except Exception as exc:
        logger.warning("Redis ping failed: %s", exc)
        return False


# ── Key prefixes ──────────────────────────────────────────────────────────────
# Centralised so every module uses consistent keys.

REFRESH_TOKEN_PREFIX = "forge:rt:"          # forge:rt:{sha256} → user_id
USER_REFRESH_SET_PREFIX = "forge:user_rts:" # forge:user_rts:{user_id} → set of hashes
ACCESS_BLACKLIST_PREFIX = "forge:bl:"       # forge:bl:{jti} → "1"
