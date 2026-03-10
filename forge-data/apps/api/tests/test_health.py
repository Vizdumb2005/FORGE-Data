"""Tests for the health endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_health(client: AsyncClient) -> None:
    """GET /api/health should return 200 with status ok."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.asyncio
async def test_liveness_probe(client: AsyncClient) -> None:
    """GET /api/v1/health/live should return 200."""
    resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "timestamp" in body
    assert "version" in body


@pytest.mark.asyncio
async def test_openapi_schema_available(client: AsyncClient) -> None:
    """OpenAPI JSON schema should be accessible at /api/openapi.json."""
    resp = await client.get("/api/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "FORGE Data API"
    assert schema["info"]["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_all_router_prefixes_registered(client: AsyncClient) -> None:
    """Verify all major API paths appear in the OpenAPI spec."""
    resp = await client.get("/api/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]

    expected_prefixes = [
        "/api/health",
        "/api/v1/auth/register",
        "/api/v1/auth/token",
        "/api/v1/users/me",
        "/api/v1/workspaces",
        "/api/v1/ai/chat",
        "/api/v1/ai/providers",
        "/api/v1/connectors/test",
        "/api/v1/experiments",
    ]
    for prefix in expected_prefixes:
        assert any(p.startswith(prefix) for p in paths), (
            f"Expected a path starting with {prefix!r} in OpenAPI spec"
        )
