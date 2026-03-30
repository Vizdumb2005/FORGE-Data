"""Tests for Orion workflow endpoints."""

import asyncio

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_workspace(client: AsyncClient, auth_headers: dict, name: str = "Workflow Test WS") -> str:
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": name, "description": "workflow tests"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_workflow(
    client: AsyncClient,
    auth_headers: dict,
    workspace_id: str,
    trigger_type: str = "manual",
) -> str:
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        json={"name": "Test Workflow", "trigger_type": trigger_type, "trigger_config": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_templates_count(client: AsyncClient, auth_headers: dict) -> None:
    ws_id = await _create_workspace(client, auth_headers, "Template WS")
    resp = await client.get(f"/api/v1/workspaces/{ws_id}/workflows/templates", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    templates = resp.json()
    assert isinstance(templates, list)
    assert len(templates) == 4
    await client.delete(f"/api/v1/workspaces/{ws_id}", headers=auth_headers)


async def test_workflow_wait_node_run_success(client: AsyncClient, auth_headers: dict) -> None:
    ws_id = await _create_workspace(client, auth_headers, "Run WS")
    wf_id = await _create_workflow(client, auth_headers, ws_id, "manual")

    node_resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/workflows/{wf_id}/nodes",
        json={
            "node_type": "wait",
            "label": "Wait",
            "config": {"seconds": 1},
            "position_x": 100,
            "position_y": 100,
            "retry_count": 0,
            "timeout_seconds": 10,
        },
        headers=auth_headers,
    )
    assert node_resp.status_code == 201, node_resp.text
    node_id = node_resp.json()["id"]
    assert node_id

    trigger_resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/workflows/{wf_id}/trigger",
        json={"run_metadata": {}},
        headers=auth_headers,
    )
    assert trigger_resp.status_code == 201, trigger_resp.text
    run_id = trigger_resp.json()["id"]

    status = "pending"
    for _ in range(20):
        await asyncio.sleep(0.5)
        run_resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/workflows/{wf_id}/runs/{run_id}",
            headers=auth_headers,
        )
        assert run_resp.status_code == 200, run_resp.text
        body = run_resp.json()
        status = body["status"]
        if status in {"success", "failed", "cancelled"}:
            break

    assert status == "success"
    await client.delete(f"/api/v1/workspaces/{ws_id}", headers=auth_headers)


async def test_from_template_creates_workflow(client: AsyncClient, auth_headers: dict) -> None:
    ws_id = await _create_workspace(client, auth_headers, "From Template WS")
    create_resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/workflows/from-template",
        json={
            "template_key": "daily_dataset_refresh",
            "name": "Daily Refresh",
            "description": "from test",
            "config_overrides": {
                "dataset_id": "00000000-0000-0000-0000-000000000001",
                "refresh_sql": "SELECT 1 AS ok",
                "notify_email": "ops@example.com",
            },
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["name"] == "Daily Refresh"
    assert len(body["nodes"]) > 0
    assert len(body["edges"]) > 0
    await client.delete(f"/api/v1/workspaces/{ws_id}", headers=auth_headers)

