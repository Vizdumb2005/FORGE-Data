"""Execute router — run code/SQL cells via Jupyter Kernel Gateway."""

import json
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.config import settings
from app.core.exceptions import JupyterUnavailableException, NotFoundException
from app.dependencies import CurrentUser, DBSession
from app.models.cell import Cell
from app.schemas.cell import CellOutput, ExecuteRequest, ExecuteResponse
from app.services import workspace_service

router = APIRouter()

_JUPYTER_TIMEOUT = 120  # seconds


@router.post(
    "/{workspace_id}/cells/{cell_id}/execute",
    response_model=ExecuteResponse,
    summary="Execute a cell and return the output",
)
async def execute_cell(
    workspace_id: str,
    cell_id: str,
    payload: ExecuteRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> ExecuteResponse:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)

    result = await db.execute(
        select(Cell).where(Cell.id == cell_id, Cell.workspace_id == workspace_id)
    )
    cell: Cell | None = result.scalar_one_or_none()
    if cell is None:
        raise NotFoundException("Cell", cell_id)

    source = payload.source if payload.source is not None else cell.content
    kernel_id = payload.kernel_id or cell.kernel_id

    # Obtain or create a Jupyter kernel
    kernel_id = await _ensure_kernel(kernel_id)

    # Execute code via Jupyter REST + WebSocket protocol
    output = await _execute_code(kernel_id, source)

    # Persist result back to the cell
    cell.output = output.model_dump()
    cell.kernel_id = kernel_id
    cell.last_executed_at = datetime.now(timezone.utc)
    await db.flush()

    return ExecuteResponse(cell_id=cell_id, output=output, kernel_id=kernel_id)


@router.delete(
    "/{workspace_id}/kernels/{kernel_id}",
    status_code=204,
    summary="Shut down a Jupyter kernel",
)
async def shutdown_kernel(
    workspace_id: str,
    kernel_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> None:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    await _delete_kernel(kernel_id)


# ── Jupyter Kernel Gateway helpers ────────────────────────────────────────────

async def _ensure_kernel(kernel_id: str | None) -> str:
    """Return *kernel_id* if alive, or start a new Python 3 kernel."""
    if kernel_id:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"{settings.jupyter_gateway_url}/api/kernels/{kernel_id}"
                )
            if r.status_code == 200:
                return kernel_id
        except Exception:
            pass  # fall through to create a new kernel

    # Create a new kernel
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            headers = {}
            if settings.jupyter_token:
                headers["Authorization"] = f"token {settings.jupyter_token}"
            r = await client.post(
                f"{settings.jupyter_gateway_url}/api/kernels",
                json={"name": "python3"},
                headers=headers,
            )
            r.raise_for_status()
            return r.json()["id"]
    except Exception as exc:
        raise JupyterUnavailableException() from exc


async def _execute_code(kernel_id: str, code: str) -> CellOutput:
    """
    Send *code* to the Jupyter kernel over its WebSocket channel and collect output.

    Implements a minimal subset of the Jupyter messaging protocol (v5.x):
      https://jupyter-client.readthedocs.io/en/stable/messaging.html
    """
    import websockets

    ws_url = (
        settings.jupyter_gateway_url.replace("http://", "ws://")
        .replace("https://", "wss://")
        + f"/api/kernels/{kernel_id}/channels"
    )
    if settings.jupyter_token:
        ws_url += f"?token={settings.jupyter_token}"

    msg_id = str(uuid.uuid4())
    execute_msg = {
        "header": {
            "msg_id": msg_id,
            "username": "forge",
            "session": str(uuid.uuid4()),
            "msg_type": "execute_request",
            "version": "5.3",
        },
        "parent_header": {},
        "metadata": {},
        "content": {
            "code": code,
            "silent": False,
            "store_history": True,
            "user_expressions": {},
            "allow_stdin": False,
        },
    }

    collected_text: list[str] = []
    collected_data: dict = {}
    status = "ok"
    error_name: str | None = None
    error_value: str | None = None
    traceback: list[str] | None = None
    execution_count: int | None = None

    try:
        async with websockets.connect(ws_url, open_timeout=10) as ws:
            await ws.send(json.dumps(execute_msg))

            # Read messages until we receive execute_reply
            deadline = _JUPYTER_TIMEOUT
            while deadline > 0:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                deadline -= 5
                msg = json.loads(raw)

                if msg.get("parent_header", {}).get("msg_id") != msg_id:
                    continue

                msg_type = msg.get("msg_type")
                content = msg.get("content", {})

                if msg_type == "stream":
                    collected_text.append(content.get("text", ""))

                elif msg_type in ("display_data", "execute_result"):
                    collected_data = content.get("data", {})
                    execution_count = content.get("execution_count")

                elif msg_type == "error":
                    status = "error"
                    error_name = content.get("ename", "Error")
                    error_value = content.get("evalue", "")
                    traceback = content.get("traceback", [])

                elif msg_type == "execute_reply":
                    if content.get("status") == "error":
                        status = "error"
                    break

    except Exception as exc:
        raise JupyterUnavailableException() from exc

    return CellOutput(
        status=status,
        output_type=(
            "error" if status == "error"
            else ("execute_result" if collected_data else "stream")
        ),
        text="".join(collected_text) or None,
        data=collected_data or None,
        ename=error_name,
        evalue=error_value,
        traceback=traceback,
        execution_count=execution_count,
    )


async def _delete_kernel(kernel_id: str) -> None:
    try:
        headers = {}
        if settings.jupyter_token:
            headers["Authorization"] = f"token {settings.jupyter_token}"
        async with httpx.AsyncClient(timeout=5) as client:
            await client.delete(
                f"{settings.jupyter_gateway_url}/api/kernels/{kernel_id}",
                headers=headers,
            )
    except Exception:
        pass  # best-effort — kernel may already be dead


# Add missing import
import asyncio  # noqa: E402
