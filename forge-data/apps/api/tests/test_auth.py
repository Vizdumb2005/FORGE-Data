"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient) -> None:
    """Registering with valid data should return 201 and a user object."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@forge-data.test",
            "password": "SecurePass1",
            "full_name": "New User",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "newuser@forge-data.test"
    assert body["full_name"] == "New User"
    assert "id" in body
    assert "hashed_password" not in body


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    """Registering with an existing email should return 409."""
    payload = {
        "email": "duplicate@forge-data.test",
        "password": "SecurePass1",
        "full_name": "Dup User",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201

    resp2 = await client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "EMAIL_EXISTS"


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient) -> None:
    """Password without uppercase letter or digit should return 422."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@forge-data.test",
            "password": "onlylower",
            "full_name": "Weak User",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, registered_user: dict) -> None:
    """Valid credentials should return access + refresh tokens."""
    resp = await client.post(
        "/api/v1/auth/token",
        data={
            "username": "testuser@forge-data.test",
            "password": "SecurePass1",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, registered_user: dict) -> None:
    """Wrong password should return 401."""
    resp = await client.post(
        "/api/v1/auth/token",
        data={
            "username": "testuser@forge-data.test",
            "password": "WrongPass9",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(client: AsyncClient) -> None:
    """Unknown email should return 401 (not 404 — to prevent user enumeration)."""
    resp = await client.post(
        "/api/v1/auth/token",
        data={
            "username": "nobody@forge-data.test",
            "password": "Anything1",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, auth_headers: dict) -> None:
    """Authenticated GET /api/v1/users/me should return the current user."""
    resp = await client.get("/api/v1/users/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "testuser@forge-data.test"


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient) -> None:
    """GET /api/v1/users/me without a token should return 401."""
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_refresh(client: AsyncClient, registered_user: dict) -> None:
    """A valid refresh token should return a new token pair."""
    # Log in to get tokens
    login = await client.post(
        "/api/v1/auth/token",
        data={
            "username": "testuser@forge-data.test",
            "password": "SecurePass1",
        },
    )
    refresh_token = login.json()["refresh_token"]

    # Refresh
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


@pytest.mark.asyncio
async def test_token_refresh_with_access_token_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Using an access token as a refresh token should be rejected."""
    access_token = auth_headers["Authorization"].removeprefix("Bearer ")
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert resp.status_code == 401
