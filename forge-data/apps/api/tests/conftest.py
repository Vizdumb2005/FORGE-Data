"""pytest fixtures for FORGE Data API tests.

Test database strategy:
  - Uses the same PostgreSQL instance as development but with the ``forge_test`` database.
  - DATABASE_URL_TEST can be set in the environment to override.
  - Tables are dropped and recreated for each test session (not each test).
  - Tests share the same database state within a session — rely on unique emails per test.
"""

import os
from collections.abc import AsyncGenerator

import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Override settings before importing anything from app ──────────────────────
_PG_USER = os.getenv("POSTGRES_USER", "forge")
_PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "forge")
_PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
_PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
_TEST_DB_NAME = os.getenv("POSTGRES_TEST_DB", "forge_test")
_TEST_DB_URL = os.getenv(
    "DATABASE_URL_TEST",
    f"postgresql+asyncpg://{_PG_USER}:{_PG_PASSWORD}@{_PG_HOST}:{_PG_PORT}/{_TEST_DB_NAME}",
)
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ["APP_ENV"] = "test"
os.environ["JWT_SECRET"] = "test-secret-do-not-use-in-production-32chars!!"
os.environ["REDIS_URL"] = os.getenv("REDIS_URL", "redis://redis:6379/1")

import app.database as database_module  # noqa: E402
from app.database import Base  # noqa: E402
from app.main import app  # noqa: E402


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def _ensure_test_database() -> None:
    conn = await asyncpg.connect(
        host=_PG_HOST,
        port=_PG_PORT,
        user=_PG_USER,
        password=_PG_PASSWORD,
        database="postgres",
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            _TEST_DB_NAME,
        )
        if not exists:
            await conn.execute(
                f"CREATE DATABASE {_quote_ident(_TEST_DB_NAME)} OWNER {_quote_ident(_PG_USER)}"
            )
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope="session", autouse=True, loop_scope="session")
async def setup_database():
    """Re-create engine on the session event loop, create tables, then tear down."""
    await _ensure_test_database()
    engine = create_async_engine(
        _TEST_DB_URL,
        echo=False,
        pool_pre_ping=False,
        pool_size=5,
        max_overflow=10,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    # Patch the app's database module so all code paths use this engine
    database_module.engine = engine
    database_module.AsyncSessionLocal = session_factory

    # Also patch the Redis module to use a fresh connection on this loop
    # Patch Redis to use connection on this event loop
    try:
        import redis.asyncio as aioredis

        from app.core import redis as redis_module

        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/1")
        pool = aioredis.ConnectionPool.from_url(
            redis_url,
            max_connections=5,
            decode_responses=True,
        )
        redis_module._pool = pool
        redis_module._client = aioredis.Redis(connection_pool=pool)
    except Exception:
        pass

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an AsyncSession for direct DB operations in tests."""
    async with database_module.AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an httpx AsyncClient pointed at the FastAPI test app (session-scoped)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        yield ac


# ── Helper fixtures ────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def registered_user(client: AsyncClient) -> dict:
    """Register a test user once per session and return the response JSON."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "testuser@example.com",
            "password": "SecurePass12",
            "full_name": "Test User",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def auth_headers(client: AsyncClient, registered_user: dict) -> dict:
    """Log in once per session and return Authorization headers."""
    resp = await client.post(
        "/api/v1/auth/token",
        data={
            "username": "testuser@example.com",
            "password": "SecurePass12",
        },
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
