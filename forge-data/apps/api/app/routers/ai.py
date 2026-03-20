"""AI router — NL-to-code pipeline, stat advisor, and conversational chat with SSE."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.code_generator import CodeGenerator, WorkspaceContext
from app.core.exceptions import NotFoundException
from app.core.llm_provider import LLMProvider
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
code_generator = CodeGenerator(llm_provider=llm_provider)
stat_advisor = StatisticalAdvisor(llm_provider=llm_provider)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    language: Literal["python", "sql", "r"] = "python"
    cell_id: str | None = None
    history: list[dict[str, str]] = Field(default_factory=list)


class FixErrorRequest(BaseModel):
    code: str = Field(min_length=1)
    error_output: str = Field(min_length=1)
    language: Literal["python", "sql", "r"] = "python"
    cell_id: str | None = None


class ExplainRequest(BaseModel):
    code: str = Field(min_length=1)
    output: str = Field(min_length=1)
    language: Literal["python", "sql", "r"] = "python"


class SuggestRequest(BaseModel):
    history: list[dict[str, str]] = Field(default_factory=list)


class StatAdvisorRequest(BaseModel):
    dataset_id: str
    question: str = Field(min_length=1)


class ChatRequest(BaseModel):
    workspace_id: str
    message: str = Field(min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)


class MetricCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    definition: str = Field(min_length=1)
    formula_sql: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)


class PipelineRunRequest(BaseModel):
    goal: str = Field(min_length=1)


@router.post("/workspaces/{workspace_id}/generate", summary="Generate code from natural language")
async def generate_code(
    workspace_id: str,
    payload: GenerateRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> StreamingResponse:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    context = WorkspaceContext(workspace_id=workspace_id, db=db, metadata={"task": "generate_code"})

    async def stream() -> AsyncIterator[str]:
        full_chunks: list[str] = []
        async for chunk in code_generator.generate_code(
            user=current_user,
            prompt=payload.prompt,
            language=payload.language,
            workspace_context=context,
            history=payload.history,
        ):
            full_chunks.append(chunk)
            yield _sse({"type": "token", "text": chunk})

        full_code = "".join(full_chunks)
        if payload.cell_id:
            await _update_cell_content(db, workspace_id, payload.cell_id, full_code)
        yield _sse({"type": "complete", "full_code": full_code})

    return _sse_response(stream())


@router.post("/workspaces/{workspace_id}/fix-error", summary="Fix generated code based on runtime error")
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
        async for chunk in code_generator.fix_error(
            user=current_user,
            original_code=payload.code,
            error_output=payload.error_output,
            language=payload.language,
            workspace_context=context,
        ):
            full_chunks.append(chunk)
            yield _sse({"type": "token", "text": chunk})

        full_code = "".join(full_chunks)
        if payload.cell_id:
            await _update_cell_content(db, workspace_id, payload.cell_id, full_code)
        yield _sse({"type": "complete", "full_code": full_code})

    return _sse_response(stream())


@router.post("/workspaces/{workspace_id}/explain", summary="Explain execution output in plain English")
async def explain_output(
    workspace_id: str,
    payload: ExplainRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> StreamingResponse:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)

    async def stream() -> AsyncIterator[str]:
        full_chunks: list[str] = []
        async for chunk in code_generator.explain_output(
            user=current_user,
            code=payload.code,
            output=payload.output,
            language=payload.language,
        ):
            full_chunks.append(chunk)
            yield _sse({"type": "token", "text": chunk})
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
        "You are FORGE Data's conversational analytics assistant. "
        "Answer data questions clearly and concisely.\n\n"
        f"Workspace datasets:\n{dataset_schemas}"
    )

    async def stream() -> AsyncIterator[str]:
        messages = [*payload.history, {"role": "user", "content": payload.message}]
        response = await llm_provider.complete(
            user=current_user,
            messages=messages,
            system=system_prompt,
            stream=True,
            max_tokens=1500,
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

    return _sse_response(stream())


@router.post(
    "/workspaces/{workspace_id}/semantic-layer/metrics",
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
    status_code=204,
    summary="Delete semantic metric",
)
async def delete_metric(
    workspace_id: str,
    metric_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> None:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    layer = SemanticLayer(db)
    await layer.delete_metric(workspace_id, metric_id)


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
        async def push(event: dict[str, Any]) -> None:
            nonlocal queue
            queue.append(event)

        queue: list[dict[str, Any]] = []
        run = await engine.run_pipeline(
            user=current_user,
            workspace_id=workspace_id,
            goal=payload.goal,
            stream_updates=push,
        )
        for event in queue:
            yield _sse(event)
        if not any(item.get("type") == "complete" for item in queue):
            yield _sse({"type": "complete", "full_report": run.full_report or ""})

    return _sse_response(stream())


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


@router.get("/workspaces/{workspace_id}/pipelines/{run_id}", summary="Get full pipeline run details")
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


def _sse_response(content: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        content=content,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _update_cell_content(db: DBSession, workspace_id: str, cell_id: str, content: str) -> None:
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
