"""Execute router — run code/SQL/R cells via Jupyter Kernel Gateway with SSE streaming."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.core.exceptions import NotFoundException
from app.core.query_engine import QueryError
from app.dependencies import CurrentUser, DBSession, KernelMgr, QueryEngine
from app.models.cell import Cell
from app.services import audit_service, workspace_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ═════════════════════════════════════════════════════════════════════════════
# POST /workspaces/{wid}/cells/{cid}/run — Execute a cell (SSE)
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/{workspace_id}/cells/{cell_id}/run",
    summary="Execute a cell and stream output via SSE",
)
async def run_cell(
    workspace_id: str,
    cell_id: str,
    current_user: CurrentUser,
    db: DBSession,
    kernel_mgr: KernelMgr,
    query_engine: QueryEngine,
    request: Request,
):
    """
    Execute a workspace cell.  For SQL cells the query is routed to the
    FederatedQueryEngine for immediate results.  For Python/R cells the code
    runs in a shared Jupyter kernel and output is streamed as Server-Sent Events.

    SSE event types:
      ``stream``   — stdout/stderr text
      ``result``   — execute_result (text/html, text/plain, …)
      ``image``    — display_data containing image/png
      ``error``    — execution error (ename, evalue, traceback)
      ``complete`` — final summary with execution_time_ms and status
    """
    await workspace_service.get_workspace(db, workspace_id, current_user.id)

    result = await db.execute(
        select(Cell).where(Cell.id == cell_id, Cell.workspace_id == workspace_id)
    )
    cell: Cell | None = result.scalar_one_or_none()
    if cell is None:
        raise NotFoundException("Cell", cell_id)

    code = cell.content
    language = cell.language or "python"

    # ── SQL path — route to FederatedQueryEngine ──────────────────────────
    if language == "sql":
        return await _execute_sql(
            db=db,
            cell=cell,
            code=code,
            workspace_id=workspace_id,
            user=current_user,
            engine=query_engine,
            request=request,
        )

    # ── Python / R path — stream via Jupyter kernel (SSE) ────────────────
    async def event_generator():
        try:
            # Ensure kernel exists and inject context on first use
            kernel_id = await kernel_mgr.get_or_create_kernel(workspace_id)

            # Inject FORGE helpers if this is the first execution
            if not cell.kernel_id or cell.kernel_id != kernel_id:
                try:
                    await kernel_mgr.inject_context(workspace_id)
                except Exception as exc:
                    logger.warning("Context injection failed: %s", exc)

            collected: list[dict[str, Any]] = []

            async def on_output(event: dict[str, Any]) -> None:
                collected.append(event)

            exec_result = await kernel_mgr.execute_code(
                workspace_id,
                code,
                on_output=on_output,
            )

            # Stream collected outputs as SSE events
            for event in collected:
                yield {"event": event.get("type", "stream"), "data": json.dumps(event)}

            # Build final output for DB persistence
            output_json: dict[str, Any] = {
                "outputs": exec_result.outputs,
                "execution_count": exec_result.execution_count,
                "execution_time_ms": exec_result.execution_time_ms,
                "status": exec_result.status,
            }

            # Persist to cell
            cell.output = output_json
            cell.kernel_id = kernel_id
            cell.last_executed_at = datetime.now(UTC)

            # Send complete event
            yield {
                "event": "complete",
                "data": json.dumps(
                    {
                        "type": "complete",
                        "status": exec_result.status,
                        "execution_time_ms": exec_result.execution_time_ms,
                        "execution_count": exec_result.execution_count,
                    }
                ),
            }

        except Exception as exc:
            logger.error("Cell execution failed: %s", exc)
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "type": "error",
                        "ename": type(exc).__name__,
                        "evalue": str(exc),
                        "traceback": [],
                    }
                ),
            }
            yield {
                "event": "complete",
                "data": json.dumps(
                    {
                        "type": "complete",
                        "status": "error",
                        "execution_time_ms": 0,
                    }
                ),
            }

    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.CELL_EXECUTE,
        user_id=current_user.id,
        workspace_id=workspace_id,
        resource_type="cell",
        resource_id=cell_id,
        ip_address=request.client.host if request.client else None,
        metadata={"language": language, "code_length": len(code)},
    )

    return EventSourceResponse(event_generator())


# ═════════════════════════════════════════════════════════════════════════════
# Kernel management endpoints
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/{workspace_id}/kernel/restart",
    summary="Restart the workspace kernel",
)
async def restart_kernel(
    workspace_id: str,
    current_user: CurrentUser,
    db: DBSession,
    kernel_mgr: KernelMgr,
) -> dict[str, str]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    await kernel_mgr.restart_kernel(workspace_id)
    return {"status": "restarted"}


@router.post(
    "/{workspace_id}/kernel/interrupt",
    summary="Interrupt the running execution",
)
async def interrupt_kernel(
    workspace_id: str,
    current_user: CurrentUser,
    db: DBSession,
    kernel_mgr: KernelMgr,
) -> dict[str, str]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    await kernel_mgr.interrupt_kernel(workspace_id)
    return {"status": "interrupted"}


@router.get(
    "/{workspace_id}/kernel/status",
    summary="Get kernel status",
)
async def kernel_status(
    workspace_id: str,
    current_user: CurrentUser,
    db: DBSession,
    kernel_mgr: KernelMgr,
) -> dict[str, Any]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    return await kernel_mgr.get_kernel_status(workspace_id)


# ═════════════════════════════════════════════════════════════════════════════
# Private helpers
# ═════════════════════════════════════════════════════════════════════════════


async def _execute_sql(
    *,
    db: Any,
    cell: Cell,
    code: str,
    workspace_id: str,
    user: Any,
    engine: Any,
    request: Request,
) -> dict[str, Any]:
    """Execute SQL via the FederatedQueryEngine and return the result immediately."""
    import time

    start = time.perf_counter()
    try:
        query_result = await engine.execute_query(user.id, code)
    except QueryError as exc:
        output: dict[str, Any] = {
            "outputs": [
                {
                    "type": "error",
                    "ename": "QueryError",
                    "evalue": exc.error,
                    "traceback": [],
                }
            ],
            "execution_count": None,
            "execution_time_ms": exc.execution_time_ms or 0,
            "status": "error",
        }
        cell.output = output
        cell.last_executed_at = datetime.now(UTC)
        return output

    elapsed = round((time.perf_counter() - start) * 1000, 1)
    output = {
        "outputs": [
            {
                "type": "execute_result",
                "data": {
                    "text/plain": f"{query_result['row_count']} rows x {len(query_result['columns'])} columns",
                    "application/json": {
                        "columns": query_result["columns"],
                        "rows": query_result["rows"],
                        "row_count": query_result["row_count"],
                    },
                },
            }
        ],
        "execution_count": None,
        "execution_time_ms": query_result.get("execution_time_ms", elapsed),
        "status": "ok",
    }
    cell.output = output
    cell.last_executed_at = datetime.now(UTC)

    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.QUERY_EXECUTE,
        user_id=user.id,
        workspace_id=workspace_id,
        resource_type="cell",
        resource_id=cell.id,
        ip_address=request.client.host if request.client else None,
        metadata={"sql": code[:500], "row_count": query_result["row_count"]},
    )

    return output
