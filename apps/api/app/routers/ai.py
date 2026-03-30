"""AI router — NL-to-code pipeline, stat advisor, and conversational chat with SSE."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import uuid as _uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.code_generator import CodeGenerator, WorkspaceContext
from app.core.exceptions import NotFoundException
from app.core.llm_provider import LLMProvider, ProviderRegistry, _normalise_base_url
from app.core.pipeline_engine import AgenticPipelineEngine
from app.core.semantic_layer import SemanticLayer
from app.core.stat_advisor import StatisticalAdvisor
from app.dependencies import CurrentUser, DBSession, KernelMgr
from app.models.cell import Cell
from app.models.dataset import Dataset
from app.models.pipeline import PipelineRun
from app.services import dataset_service, workspace_service

router = APIRouter()

llm_provider = LLMProvider()
provider_registry = ProviderRegistry()
code_generator = CodeGenerator(llm_provider=llm_provider)
stat_advisor = StatisticalAdvisor(llm_provider=llm_provider)
_CONNECTIVITY_ERROR_MARKERS = (
    "all connection attempts failed",
    "connection refused",
    "name or service not known",
    "temporary failure in name resolution",
    "timed out",
)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    language: Literal["python", "sql", "r"] = "python"
    cell_id: str | None = None
    history: list[dict[str, str]] = Field(default_factory=list)
    max_tokens: int = Field(default=2048, ge=64, le=8192)
    # If True the backend creates a new cell and streams code directly into it
    auto_cell: bool = False


class FixErrorRequest(BaseModel):
    code: str = Field(min_length=1)
    error_output: str = Field(min_length=1)
    language: Literal["python", "sql", "r"] = "python"
    cell_id: str | None = None
    max_tokens: int = Field(default=2048, ge=64, le=8192)


class PatchRequest(BaseModel):
    """Surgical in-place edit of an existing cell."""
    cell_id: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    error_output: str | None = None
    language: Literal["python", "sql", "r"] = "python"


class ExplainRequest(BaseModel):
    code: str = Field(min_length=1)
    output: str = Field(min_length=1)
    language: Literal["python", "sql", "r"] = "python"
    max_tokens: int = Field(default=1200, ge=64, le=8192)


class SuggestRequest(BaseModel):
    history: list[dict[str, str]] = Field(default_factory=list)


class StatAdvisorRequest(BaseModel):
    dataset_id: str
    question: str = Field(min_length=1)


class ChatRequest(BaseModel):
    workspace_id: str
    message: str = Field(min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    max_tokens: int = Field(default=1500, ge=64, le=8192)


class MetricCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    definition: str = Field(min_length=1)
    formula_sql: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)


class PipelineRunRequest(BaseModel):
    goal: str = Field(min_length=1)


@router.get("/providers", summary="List available AI model providers")
async def list_providers(current_user: CurrentUser) -> list[dict[str, Any]]:
    return provider_registry.list_for_user(current_user)


@router.get("/providers/{provider_id}/models", summary="Fetch live model list from a local provider")
async def list_provider_models(provider_id: str, current_user: CurrentUser) -> dict[str, Any]:
    """
    Query a running local provider daemon for its installed/loaded models.

    - ollama      → GET /api/tags
    - openai_compatible (llama_cpp, gpt4all, vllm) → GET /v1/models
    """
    spec = provider_registry.providers.get(provider_id)
    if spec is None:
        return {"models": [], "error": f"Unknown provider '{provider_id}'"}
    if not spec.local:
        return {"models": [], "error": f"'{provider_id}' is not a local provider"}

    settings = provider_registry.resolve_provider_settings(current_user, spec)
    base_url = provider_registry.resolve_base_url(current_user, spec, settings)

    # Last-resort: fall back to env var then static default
    if not base_url and spec.base_url_env:
        raw = os.getenv(spec.base_url_env)
        if raw:
            base_url = _normalise_base_url(raw)
    if not base_url and spec.base_url:
        base_url = _normalise_base_url(spec.base_url)

    if not base_url:
        return {"models": [], "error": f"No base URL configured for '{provider_id}'"}

    base_url = base_url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            if spec.protocol == "ollama":
                resp = await http.get(f"{base_url}/api/tags")
                resp.raise_for_status()
                model_names = [m["name"] for m in resp.json().get("models", [])]
            else:
                # OpenAI-compatible: llama.cpp, GPT4All, vLLM all expose /v1/models
                resp = await http.get(f"{base_url}/v1/models")
                resp.raise_for_status()
                model_names = [m["id"] for m in resp.json().get("data", [])]

            return {"models": model_names, "base_url": base_url}
    except Exception as exc:
        return {"models": [], "error": str(exc), "base_url": base_url}


@router.post("/workspaces/{workspace_id}/generate", summary="Generate code from natural language")
async def generate_code(
    workspace_id: str,
    payload: GenerateRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> StreamingResponse:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    context = WorkspaceContext(workspace_id=workspace_id, db=db, metadata={"task": "generate_code"})

    # Determine target cell — create one immediately if auto_cell is set
    target_cell_id = payload.cell_id
    if payload.auto_cell and not target_cell_id:
        new_cell = Cell(
            id=str(_uuid.uuid4()),
            workspace_id=workspace_id,
            cell_type="code" if payload.language != "sql" else "sql",
            language=payload.language,
            content="",
            position_x=60,
            position_y=9_999_999,
            width=600,
            height=320,
            created_by=current_user.id,
        )
        db.add(new_cell)
        await db.flush()
        target_cell_id = new_cell.id

    async def stream() -> AsyncIterator[str]:
        full_chunks: list[str] = []

        # Emit cell_created immediately so the frontend can scroll to it
        if target_cell_id and payload.auto_cell:
            yield _sse({"type": "cell_created", "cell_id": target_cell_id, "language": payload.language})

        try:
            async for chunk in code_generator.generate_code(
                user=current_user,
                prompt=payload.prompt,
                language=payload.language,
                workspace_context=context,
                history=payload.history,
                max_tokens=payload.max_tokens,
            ):
                full_chunks.append(chunk)
                yield _sse({"type": "token", "text": chunk})

            full_code = "".join(full_chunks)
            if target_cell_id:
                await _update_cell_content(db, workspace_id, target_cell_id, full_code)

            # Generate a brief summary of what was written
            summary = ""
            with contextlib.suppress(Exception):
                summary = await code_generator.summarise_code(
                    user=current_user,
                    code=full_code,
                    prompt=payload.prompt,
                    language=payload.language,
                )

            yield _sse({
                "type": "complete",
                "full_code": full_code,
                "cell_id": target_cell_id,
                "summary": summary,
            })
        except Exception as exc:
            if _looks_like_provider_connectivity_issue(str(exc)):
                fallback_code = _fallback_generated_code(payload.prompt, payload.language)
                full_chunks.append(fallback_code)
                yield _sse({"type": "token", "text": fallback_code})
                if target_cell_id:
                    await _update_cell_content(db, workspace_id, target_cell_id, fallback_code)
                yield _sse({"type": "complete", "full_code": fallback_code, "cell_id": target_cell_id, "summary": ""})
                return
            yield _sse({"type": "error", "text": str(exc)})
            yield _sse({"type": "complete", "full_code": "".join(full_chunks), "cell_id": target_cell_id, "summary": ""})

    return _sse_response(stream())


@router.post(
    "/workspaces/{workspace_id}/fix-error", summary="Fix generated code based on runtime error"
)
async def fix_error(
    workspace_id: str,
    payload: FixErrorRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> StreamingResponse:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    context = WorkspaceContext(workspace_id=workspace_id, db=db, metadata={"task": "fix_error"})

    async def stream() -> AsyncIterator[str]:
        full_chunks: list[str] = []
        try:
            async for chunk in code_generator.fix_error(
                user=current_user,
                original_code=payload.code,
                error_output=payload.error_output,
                language=payload.language,
                workspace_context=context,
                max_tokens=payload.max_tokens,
            ):
                full_chunks.append(chunk)
                yield _sse({"type": "token", "text": chunk})

            full_code = "".join(full_chunks)
            if payload.cell_id:
                await _update_cell_content(db, workspace_id, payload.cell_id, full_code)
            yield _sse({"type": "complete", "full_code": full_code})
        except Exception as exc:
            yield _sse({"type": "error", "text": str(exc)})
            yield _sse({"type": "complete", "full_code": "".join(full_chunks)})

    return _sse_response(stream())


@router.post(
    "/workspaces/{workspace_id}/patch", summary="Surgically patch an existing cell in-place"
)
async def patch_cell(
    workspace_id: str,
    payload: PatchRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> StreamingResponse:
    """
    Reads the current cell content, asks the model to apply a minimal targeted
    change, streams the corrected code back into the same cell, and emits a
    summary of what changed.
    """
    await workspace_service.get_workspace(db, workspace_id, current_user.id)

    # Load the current cell content
    result = await db.execute(
        select(Cell).where(Cell.id == payload.cell_id, Cell.workspace_id == workspace_id)
    )
    cell = result.scalar_one_or_none()
    if cell is None:
        raise NotFoundException("Cell", payload.cell_id)

    original_code = cell.content or ""
    context = WorkspaceContext(workspace_id=workspace_id, db=db, metadata={"task": "patch"})

    async def stream() -> AsyncIterator[str]:
        full_chunks: list[str] = []
        summary = ""
        try:
            async for chunk in code_generator.patch_code(
                user=current_user,
                original_code=original_code,
                instruction=payload.instruction,
                error_output=payload.error_output,
                language=payload.language,
                workspace_context=context,
            ):
                full_chunks.append(chunk)
                yield _sse({"type": "token", "text": chunk})

            full_text = "".join(full_chunks)

            # Split off the trailing "# SUMMARY: ..." line the model appends
            patched_code = full_text
            for line in reversed(full_text.splitlines()):
                stripped = line.strip()
                if stripped.startswith("# SUMMARY:"):
                    summary = stripped[len("# SUMMARY:"):].strip()
                    patched_code = full_text[: full_text.rfind(line)].rstrip()
                    break

            await _update_cell_content(db, workspace_id, payload.cell_id, patched_code)
            yield _sse({
                "type": "complete",
                "full_code": patched_code,
                "cell_id": payload.cell_id,
                "summary": summary or f"Applied: {payload.instruction}",
            })
        except Exception as exc:
            yield _sse({"type": "error", "text": str(exc)})
            yield _sse({"type": "complete", "full_code": "".join(full_chunks), "cell_id": payload.cell_id, "summary": ""})

    return _sse_response(stream())


@router.post(
    "/workspaces/{workspace_id}/explain", summary="Explain execution output in plain English"
)
async def explain_output(
    workspace_id: str,
    payload: ExplainRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> StreamingResponse:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)

    async def stream() -> AsyncIterator[str]:
        full_chunks: list[str] = []
        try:
            async for chunk in code_generator.explain_output(
                user=current_user,
                code=payload.code,
                output=payload.output,
                language=payload.language,
                max_tokens=payload.max_tokens,
            ):
                full_chunks.append(chunk)
                yield _sse({"type": "token", "text": chunk})
            yield _sse({"type": "complete", "full_text": "".join(full_chunks)})
        except Exception as exc:
            yield _sse({"type": "error", "text": str(exc)})
            yield _sse({"type": "complete", "full_text": "".join(full_chunks)})

    return _sse_response(stream())


@router.post("/workspaces/{workspace_id}/suggest", summary="Suggest next analysis steps")
async def suggest_next_steps(
    workspace_id: str,
    payload: SuggestRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> list[str]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    context = WorkspaceContext(workspace_id=workspace_id, db=db, metadata={"task": "suggest"})
    return await code_generator.suggest_next_steps(
        user=current_user,
        analysis_history=payload.history,
        workspace_context=context,
    )


@router.post("/workspaces/{workspace_id}/stat-advisor", summary="Recommend statistical test")
async def recommend_stat_test(
    workspace_id: str,
    payload: StatAdvisorRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> dict[str, Any]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    dataset = await dataset_service.get_dataset(db, workspace_id, payload.dataset_id)
    dataset_profile = {
        "id": dataset.id,
        "name": dataset.name,
        "schema": dataset.schema_snapshot or [],
        "profile_data": dataset.profile_data or {},
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
    }
    return await stat_advisor.recommend_test(
        user=current_user,
        dataset_profile=dataset_profile,
        question=payload.question,
    )


@router.post("/chat", summary="General conversational AI chat")
async def chat(
    payload: ChatRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> StreamingResponse:
    await workspace_service.get_workspace(db, payload.workspace_id, current_user.id)
    context = WorkspaceContext(
        workspace_id=payload.workspace_id,
        db=db,
        metadata={"task": "chat"},
    )
    dataset_schemas = await _dataset_summaries(context)
    system_prompt = (
        "You are FORGE Data's conversational analytics assistant.\n"
        "You are running INSIDE a full data science IDE with:\n"
        "- Code cells (Python, SQL, R) that execute via Jupyter kernels\n"
        "- Dataset ingestion, profiling, and preview\n"
        "- An autonomous AI agent that can write code, run it, see errors, fix them, and loop\n"
        "- Data connectors, experiment tracking, and publishing\n\n"
        "IMPORTANT: If the user asks you to create code, run analysis, build a dashboard, "
        "visualize data, or any task that requires CODE EXECUTION — tell them to use the "
        "agent by rephrasing as a goal like 'Do a full analysis of this dataset'. "
        "DO NOT say you cannot generate or run code. The platform CAN do everything.\n\n"
        "For pure knowledge questions (what is a p-value, explain this output), answer clearly.\n\n"
        f"Workspace datasets:\n{dataset_schemas}"
    )

    async def stream() -> AsyncIterator[str]:
        try:
            messages = [*payload.history, {"role": "user", "content": payload.message}]
            response = await llm_provider.complete(
                user=current_user,
                messages=messages,
                system=system_prompt,
                stream=True,
                max_tokens=payload.max_tokens,
                provider=payload.provider,
                model=payload.model,
            )
            full_chunks: list[str] = []
            if isinstance(response, str):
                full_chunks.append(response)
                yield _sse({"type": "token", "text": response})
            else:
                async for chunk in response:
                    full_chunks.append(chunk)
                    yield _sse({"type": "token", "text": chunk})
            yield _sse({"type": "complete", "full_text": "".join(full_chunks)})
        except Exception as e:
            error_msg = str(e)
            if "API key" in error_msg or "api_key" in error_msg.lower():
                error_msg = "No API key configured. Please add your API key in Settings."
            yield _sse({"type": "error", "message": error_msg})

    return _sse_response(stream())


@router.post(
    "/workspaces/{workspace_id}/semantic-layer/metrics",
    status_code=201,
    summary="Create semantic metric definition",
)
async def create_metric(
    workspace_id: str,
    payload: MetricCreateRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> dict[str, Any]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    layer = SemanticLayer(db)
    metric = await layer.define_metric(
        workspace_id=workspace_id,
        user_id=current_user.id,
        name=payload.name,
        definition=payload.definition,
        formula_sql=payload.formula_sql,
        depends_on=payload.depends_on,
    )
    return {
        "id": metric.id,
        "workspace_id": metric.workspace_id,
        "name": metric.name,
        "definition": metric.definition,
        "formula_sql": metric.formula_sql,
        "depends_on": metric.depends_on or [],
        "created_by": metric.created_by,
        "created_at": metric.created_at.isoformat(),
    }


@router.get(
    "/workspaces/{workspace_id}/semantic-layer/metrics",
    summary="List semantic metrics",
)
async def list_metrics(
    workspace_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> list[dict[str, Any]]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    layer = SemanticLayer(db)
    metrics = await layer.list_metrics(workspace_id)
    return [
        {
            "id": metric.id,
            "workspace_id": metric.workspace_id,
            "name": metric.name,
            "definition": metric.definition,
            "formula_sql": metric.formula_sql,
            "depends_on": metric.depends_on or [],
            "created_by": metric.created_by,
            "created_at": metric.created_at.isoformat(),
        }
        for metric in metrics
    ]


@router.delete(
    "/workspaces/{workspace_id}/semantic-layer/metrics/{metric_id}",
    status_code=200,
    response_model=None,
    response_class=Response,
    summary="Delete semantic metric",
)
async def delete_metric(
    workspace_id: str,
    metric_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> Response:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    layer = SemanticLayer(db)
    await layer.delete_metric(workspace_id, metric_id)
    return Response(status_code=200)


@router.post(
    "/workspaces/{workspace_id}/pipelines/run",
    summary="Run agentic pipeline and stream updates",
)
async def run_pipeline(
    workspace_id: str,
    payload: PipelineRunRequest,
    current_user: CurrentUser,
    db: DBSession,
    kernel_mgr: KernelMgr,
) -> StreamingResponse:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    engine = AgenticPipelineEngine(db=db, kernel_mgr=kernel_mgr, code_generator=code_generator)

    async def stream() -> AsyncIterator[str]:
        # Use a real async queue so events are yielded as they arrive,
        # rather than buffered until run_pipeline() fully completes.
        event_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def push(event: dict[str, Any]) -> None:
            await event_queue.put(event)

        async def _run() -> None:
            try:
                await engine.run_pipeline(
                    user=current_user,
                    workspace_id=workspace_id,
                    goal=payload.goal,
                    stream_updates=push,
                )
            finally:
                # Sentinel to signal the consumer that we are done
                await event_queue.put(None)

        task = asyncio.create_task(_run())
        try:
            emitted_complete = False
            while True:
                event = await event_queue.get()
                if event is None:
                    break
                event_type = event.get("type")
                # For the final report, also emit a token so SSE consumers
                # (e.g. collect_sse) can capture the report text.
                if event_type == "complete":
                    report_text = event.get("full_report", "")
                    if report_text:
                        yield _sse({"type": "token", "text": report_text})
                    yield _sse(event)
                    emitted_complete = True
                else:
                    yield _sse(event)
            if not emitted_complete:
                yield _sse({"type": "complete", "full_report": ""})
        except Exception:
            task.cancel()
            raise

    return _sse_response(stream())


# Global engine for the workspace (singleton for simplicity in this demo)
_agent_engine: AgenticPipelineEngine | None = None


def get_agent_engine(db: AsyncSession, kernel_mgr: Any) -> AgenticPipelineEngine:
    global _agent_engine
    if _agent_engine is None:
        _agent_engine = AgenticPipelineEngine(db=db, kernel_mgr=kernel_mgr, code_generator=code_generator)
    else:
        # Update references if they changed
        _agent_engine.db = db
        _agent_engine.kernel_mgr = kernel_mgr
    return _agent_engine


# --- API Agent Endpoints ---
# POST /ai/workspaces/{wid}/agent - Autonomous AI agent (cell-aware loop)
# ---


class AgentRunRequest(BaseModel):
    goal: str
    max_steps: int = 5
    provider: str | None = None
    model: str | None = None


@router.post(
    "/workspaces/{workspace_id}/agent",
    summary="Run autonomous AI agent - creates cells, executes, fixes errors in a loop",
)
async def run_agent(
    workspace_id: str,
    payload: AgentRunRequest,
    current_user: CurrentUser,
    db: DBSession,
    kernel_mgr: KernelMgr,
) -> StreamingResponse:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    engine = get_agent_engine(db, kernel_mgr)

    async def stream() -> AsyncIterator[str]:
        event_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def push(event: dict[str, Any]) -> None:
            await event_queue.put(event)

        async def _run() -> None:
            try:
                await engine.run_pipeline(
                    user=current_user,
                    workspace_id=workspace_id,
                    goal=payload.goal,
                    stream_updates=push,
                )
            finally:
                await event_queue.put(None)

        task = asyncio.create_task(_run())
        try:
            while True:
                event = await event_queue.get()
                if event is None:
                    break
                event_type = event.get("type")
                # Also emit token for legacy SSE consumers
                if event_type == "complete":
                    report_text = event.get("full_report", "")
                    if report_text:
                        yield _sse({"type": "token", "text": report_text})
                yield _sse(event)
        except Exception:
            task.cancel()
            raise

    return _sse_response(stream())


class AgentApprovalRequest(BaseModel):
    approved: bool


@router.post(
    "/workspaces/{workspace_id}/agent/approve",
    summary="Approve or deny a pending agent action (human-in-the-loop)",
)
async def approve_agent_action(
    workspace_id: str,
    payload: AgentApprovalRequest,
    current_user: CurrentUser,
    db: DBSession,
    kernel_mgr: KernelMgr,
) -> dict[str, Any]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    engine = get_agent_engine(db, kernel_mgr)

    queue = engine._approval_queues.get(workspace_id)
    if not queue:
        raise NotFoundException("PendingApproval", workspace_id)

    await queue.put(payload.approved)
    return {"status": "ok", "workspace_id": workspace_id, "approved": payload.approved}


@router.get("/workspaces/{workspace_id}/pipelines", summary="List pipeline runs")
async def list_pipeline_runs(
    workspace_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> list[dict[str, Any]]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.workspace_id == workspace_id)
        .order_by(PipelineRun.created_at.desc())
    )
    runs = result.scalars().all()
    return [
        {
            "id": run.id,
            "pipeline_id": run.pipeline_id,
            "status": run.status,
            "goal": run.goal,
            "goal_summary": (run.full_report or "")[:240],
            "created_at": run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
        for run in runs
    ]


@router.get(
    "/workspaces/{workspace_id}/pipelines/{run_id}", summary="Get full pipeline run details"
)
async def get_pipeline_run(
    workspace_id: str,
    run_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> dict[str, Any]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    run = await db.get(PipelineRun, run_id)
    if run is None or run.workspace_id != workspace_id:
        raise NotFoundException("PipelineRun", run_id)
    return {
        "id": run.id,
        "pipeline_id": run.pipeline_id,
        "workspace_id": run.workspace_id,
        "goal": run.goal,
        "status": run.status,
        "full_report": run.full_report,
        "steps": run.steps or [],
        "outputs": run.outputs or [],
        "retry_count": run.retry_count,
        "created_by": run.created_by,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _looks_like_provider_connectivity_issue(error_text: str) -> bool:
    lowered = error_text.lower()
    return any(marker in lowered for marker in _CONNECTIVITY_ERROR_MARKERS)


def _fallback_generated_code(prompt: str, language: str) -> str:
    if language == "sql":
        return "SELECT * FROM sales_data LIMIT 1000;"
    if language == "r":
        return (
            "library(dplyr)\n"
            "df <- forge_query(\"SELECT * FROM sales_data\")\n"
            "print(head(df))\n"
        )
    if "month-over-month" in prompt.lower() or "growth" in prompt.lower():
        return (
            "df = forge_query(\"\"\"\n"
            "SELECT date, SUM(revenue) AS revenue\n"
            "FROM sales_data\n"
            "GROUP BY date\n"
            "ORDER BY date\n"
            "\"\"\")\n"
            "df[\"mom_growth_rate\"] = df[\"revenue\"].pct_change()\n"
            "print(df)\n"
        )
    return (
        "df = forge_query(\"SELECT * FROM sales_data LIMIT 100\")\n"
        "print(df.head())\n"
    )


def _sse_response(content: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        content=content,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _update_cell_content(
    db: DBSession, workspace_id: str, cell_id: str, content: str
) -> None:
    result = await db.execute(
        select(Cell).where(
            Cell.id == cell_id,
            Cell.workspace_id == workspace_id,
        )
    )
    cell = result.scalar_one_or_none()
    if cell is None:
        raise NotFoundException("Cell", cell_id)
    cell.content = content
    await db.flush()


async def _dataset_summaries(workspace_context: WorkspaceContext) -> str:
    result = await workspace_context.db.execute(
        select(Dataset).where(Dataset.workspace_id == workspace_context.workspace_id)
    )
    datasets = result.scalars().all()
    if not datasets:
        return "No datasets currently registered."

    lines: list[str] = []
    for dataset in datasets:
        columns = dataset.schema_snapshot or []
        if not columns:
            lines.append(f"- {dataset.name}: schema unavailable")
            continue
        col_names = ", ".join(str(col.get("name", "")) for col in columns)
        lines.append(f"- {dataset.name}: {col_names}")
    return "\n".join(lines)

