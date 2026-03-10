"""Tests for workspace endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_workspaces_empty(client: AsyncClient, auth_headers: dict) -> None:
    """A new user should have no workspaces."""
    resp = await client.get("/api/v1/workspaces", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_workspace(client: AsyncClient, auth_headers: dict) -> None:
    """Creating a workspace returns 201 and the workspace object."""
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "My Workspace", "description": "A test workspace"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "My Workspace"
    assert body["description"] == "A test workspace"
    assert body["is_public"] is False
    assert "id" in body
    assert "owner_id" in body


@pytest.mark.asyncio
async def test_create_workspace_unauthenticated(client: AsyncClient) -> None:
    """Creating a workspace without auth should return 401."""
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "My Workspace"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_workspace(client: AsyncClient, auth_headers: dict) -> None:
    """GET /workspaces/{id} returns the workspace if accessible."""
    # Create first
    create_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Fetch Test", "description": None},
        headers=auth_headers,
    )
    ws_id = create_resp.json()["id"]

    # Fetch
    resp = await client.get(f"/api/v1/workspaces/{ws_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == ws_id


@pytest.mark.asyncio
async def test_get_workspace_not_found(client: AsyncClient, auth_headers: dict) -> None:
    """Fetching a non-existent workspace returns 404."""
    resp = await client.get(
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_workspace(client: AsyncClient, auth_headers: dict) -> None:
    """PATCH updates the workspace fields."""
    create_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Old Name"},
        headers=auth_headers,
    )
    ws_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/workspaces/{ws_id}",
        json={"name": "New Name", "is_public": True},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["name"] == "New Name"
    assert updated["is_public"] is True


@pytest.mark.asyncio
async def test_delete_workspace(client: AsyncClient, auth_headers: dict) -> None:
    """DELETE returns 204 and workspace is gone."""
    create_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "To Delete"},
        headers=auth_headers,
    )
    ws_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/v1/workspaces/{ws_id}", headers=auth_headers
    )
    assert del_resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/workspaces/{ws_id}", headers=auth_headers
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_list_workspace_members(client: AsyncClient, auth_headers: dict) -> None:
    """Listing members of an owner-only workspace returns empty list."""
    create_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Members Test"},
        headers=auth_headers,
    )
    ws_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/workspaces/{ws_id}/members", headers=auth_headers
    )
    assert resp.status_code == 200
    # Owner is not in workspace_members (different from member rows)
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_and_list_cells(client: AsyncClient, auth_headers: dict) -> None:
    """POST then GET cells in a workspace."""
    # Create workspace
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Cell Test"}, headers=auth_headers
    )
    ws_id = ws_resp.json()["id"]

    # Create a cell
    cell_resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/cells",
        json={
            "cell_type": "code",
            "language": "python",
            "content": "print('hello forge')",
            "position_x": 0,
            "position_y": 0,
        },
        headers=auth_headers,
    )
    assert cell_resp.status_code == 201, cell_resp.text
    cell = cell_resp.json()
    assert cell["content"] == "print('hello forge')"
    assert cell["language"] == "python"

    # List cells
    list_resp = await client.get(
        f"/api/v1/workspaces/{ws_id}/cells", headers=auth_headers
    )
    assert list_resp.status_code == 200
    cells = list_resp.json()
    assert len(cells) == 1
    assert cells[0]["id"] == cell["id"]
