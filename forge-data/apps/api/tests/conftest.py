"""pytest fixtures for FORGE Data API tests.

Test database strategy:
  - Uses the same PostgreSQL instance as development but with the ``forge_test`` database.
  - DATABASE_URL_TEST can be set in the environment to override.
  - Tables are dropped and recreated for each test session (not each test).
  - Each test gets its own transaction that is rolled back at the end (keeps tests isolated
    without re-creating schema on every test).
"""

import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Override settings before importing anything from app ──────────────────────
_TEST_DB_URL = os.getenv(
    "DATABASE_URL_TEST",
    "postgresql+asyncpg://forge:forge@localhost:5432/forge_test",
)
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ["APP_ENV"] = "test"
os.environ["JWT_SECRET"] = "test-secret-do-not-use-in-production-32chars!!"
os.environ["REDIS_URL"] = os.getenv("REDIS_URL", "redis://localhost:6379/1")

from app.database import Base  # noqa: E402
from app.main import app  # noqa: E402


# ── Engine & session factory ──────────────────────────────────────────────────

_test_engine = create_async_engine(_TEST_DB_URL, echo=False, pool_pre_ping=True)
_TestSessionLocal = async_sessionmaker(
    bind=_test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all tables once per test session, drop them when done."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _test_engine.dispose()


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an AsyncSession that is rolled back after each test.
    Uses savepoints so nested transactions work correctly.
    """
    async with _test_engine.connect() as conn:
        await conn.begin()
        await conn.begin_nested()
        session = AsyncSession(bind=conn, expire_on_commit=False)

        yield session

        await session.close()
        await conn.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an httpx AsyncClient pointed at the FastAPI test app.
    The app's get_db dependency is overridden to use the test session.
    """
    from app.dependencies import get_db

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Helper fixtures ────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    """Register a test user and return the response JSON."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "testuser@forge-data.test",
            "password": "SecurePass1",
            "full_name": "Test User",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, registered_user: dict) -> dict:
    """Log in and return Authorization headers."""
    resp = await client.post(
        "/api/v1/auth/token",
        data={
            "username": "testuser@forge-data.test",
            "password": "SecurePass1",
        },
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
