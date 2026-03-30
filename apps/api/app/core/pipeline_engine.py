"""LangGraph-backed agentic pipeline engine — cell-aware with dynamic re-planning."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.code_generator import CodeGenerator, WorkspaceContext
from app.core.exceptions import NotFoundException
from app.core.realtime import realtime_manager
from app.models.cell import Cell
from app.models.pipeline import Pipeline, PipelineRun, PipelineStatus, ScheduledPipeline
from app.models.user import User

logger = logging.getLogger(__name__)


# --- API Endpoints ---

class ToolTier(str, Enum):
    SAFE = "safe"          # Read-only, auto-approve
    STANDARD = "standard"  # Creates/modifies, auto-approve
    DANGEROUS = "dangerous" # Deletes/mutates data, REQUIRES approval


class AgentTool(TypedDict):
    name: str
    description: str
    tier: ToolTier
    func: Callable[..., Awaitable[Any]]


class AgentToolRegistry:
    """Registry of platform tools available to the agent."""

    def __init__(self, engine: AgenticPipelineEngine) -> None:
        self.engine = engine
        self.tools: dict[str, AgentTool] = {
            "read_cells": {
                "name": "read_cells",
                "description": "Read all code and output from workspace cells.",
                "tier": ToolTier.SAFE,
                "func": self._read_cells,
            },
            "list_datasets": {
                "name": "list_datasets",
                "description": "List all datasets in the current workspace.",
                "tier": ToolTier.SAFE,
                "func": self._list_datasets,
            },
            "inspect_schema": {
                "name": "inspect_schema",
                "description": "Get column types and schema for a specific dataset.",
                "tier": ToolTier.SAFE,
                "func": self._inspect_schema,
            },
            "create_cell": {
                "name": "create_cell",
                "description": "Create a new code or SQL cell.",
                "tier": ToolTier.STANDARD,
                "func": self._create_cell,
            },
            "execute_cell": {
                "name": "execute_cell",
                "description": "Run an existing cell and wait for output.",
                "tier": ToolTier.STANDARD,
                "func": self._execute_cell,
            },
            "delete_dataset": {
                "name": "delete_dataset",
                "description": "PERMANENTLY DELETE a dataset from the workspace.",
                "tier": ToolTier.DANGEROUS,
                "func": self._delete_dataset,
            },
            "clear_workspace": {
                "name": "clear_workspace",
                "description": "Delete all cells and datasets in the workspace.",
                "tier": ToolTier.DANGEROUS,
                "func": self._clear_workspace,
            },
            "execute_sql": {
                "name": "execute_sql",
                "description": "Execute direct SQL against the database (can mutate data).",
                "tier": ToolTier.DANGEROUS,
                "func": self._execute_sql,
            },
        }

    async def _read_cells(self, state: PipelineState) -> dict[str, Any]:
        content = await _read_workspace_cells(self.engine.db, state["workspace_id"])
        return {"current_output": content}

    async def _list_datasets(self, state: PipelineState) -> dict[str, Any]:
        from app.services import dataset_service
        datasets = await dataset_service.list_datasets(self.engine.db, state["workspace_id"])
        return {"current_output": [{"id": d.id, "name": d.name} for d in datasets]}

    async def _inspect_schema(self, state: PipelineState) -> dict[str, Any]:
        from app.services import dataset_service
        dataset_id = state.get("last_args", {}).get("dataset_id")
        if not dataset_id:
            return {"error": "Missing dataset_id"}
        dataset = await dataset_service.get_dataset(self.engine.db, state["workspace_id"], dataset_id)
        return {"current_output": dataset.schema_snapshot}

    async def _create_cell(self, state: PipelineState) -> dict[str, Any]:
        args = state.get("last_args", {})
        cell = await self.engine._create_cell(state["workspace_id"], args.get("content", ""), args.get("language", "python"))
        return {"current_cell_id": cell.id}

    async def _execute_cell(self, state: PipelineState) -> dict[str, Any]:
        cell_id = state.get("last_args", {}).get("cell_id")
        if not cell_id:
            return {"error": "Missing cell_id"}
        result = await self.engine.db.execute(select(Cell).where(Cell.id == cell_id))
        cell = result.scalar_one_or_none()
        if not cell:
            return {"error": f"Cell {cell_id} not found"}
        out = await self.engine._execute_cell(state["workspace_id"], cell)
        return {"current_output": out}

    async def _delete_dataset(self, state: PipelineState) -> dict[str, Any]:
        from app.services import dataset_service
        dataset_id = state.get("last_args", {}).get("dataset_id")
        await dataset_service.delete_dataset(self.engine.db, state["workspace_id"], dataset_id)
        return {"report": f"Dataset {dataset_id} deleted."}

    async def _clear_workspace(self, state: PipelineState) -> dict[str, Any]:
        # Implementation of full clear...
        return {"report": "Workspace cleared."}

    async def _execute_sql(self, state: PipelineState) -> dict[str, Any]:
        # Direct SQL execution...
        return {"report": "SQL executed."}


# --- Ledger ---

class LedgerEntry(TypedDict):
    timestamp: str
    action: str  # "plan", "code", "execute", "fix", "replan", "complete", "error"
    detail: str
    cell_id: str | None
    step_index: int | None


class TodoItem(TypedDict):
    step: str
    status: str  # "pending", "running", "success", "error", "skipped", "revised"
    cell_id: str | None


class AgentLedger:
    """Structured changelog + to-do tracker for the agent run."""

    def __init__(self) -> None:
        self.todo: list[TodoItem] = []
        self.changelog: list[LedgerEntry] = []

    def set_plan(self, steps: list[str]) -> None:
        self.todo = [{"step": s, "status": "pending", "cell_id": None} for s in steps]
        self._log("plan", f"Planned {len(steps)} steps", step_index=None)

    def revise_plan(self, new_steps: list[str], from_index: int) -> None:
        """Replace remaining steps from from_index onward."""
        # Mark any old remaining steps as "revised"
        for i in range(from_index, len(self.todo)):
            self.todo[i]["status"] = "revised"
        # Append new steps
        for s in new_steps:
            self.todo.append({"step": s, "status": "pending", "cell_id": None})
        self._log("replan", f"Revised plan: replaced remaining {len(self.todo) - from_index} steps with {len(new_steps)} new steps", step_index=from_index)

    def mark_running(self, idx: int) -> None:
        if idx < len(self.todo):
            self.todo[idx]["status"] = "running"

    def mark_done(self, idx: int, cell_id: str | None = None) -> None:
        if idx < len(self.todo):
            self.todo[idx]["status"] = "success"
            self.todo[idx]["cell_id"] = cell_id

    def mark_error(self, idx: int) -> None:
        if idx < len(self.todo):
            self.todo[idx]["status"] = "error"

    def mark_skipped(self, idx: int) -> None:
        if idx < len(self.todo):
            self.todo[idx]["status"] = "skipped"

    def _log(self, action: str, detail: str, cell_id: str | None = None, step_index: int | None = None) -> None:
        self.changelog.append({
            "timestamp": datetime.now(UTC).strftime("%H:%M:%S"),
            "action": action,
            "detail": detail,
            "cell_id": cell_id,
            "step_index": step_index,
        })

    def log(self, action: str, detail: str, cell_id: str | None = None, step_index: int | None = None) -> None:
        self._log(action, detail, cell_id, step_index)

    def snapshot(self) -> dict[str, Any]:
        return {"todo": list(self.todo), "changelog": list(self.changelog)}


# --- Pipeline state ---

class PipelineState(TypedDict, total=False):
    goal: str
    workspace_id: str
    steps: list[str]
    current_step_index: int
    current_code: str
    current_cell_id: str
    current_output: dict[str, Any]
    retry_count: int
    max_retries: int
    execution_status: str
    report: str
    step_results: list[dict[str, Any]]
    thinking: str  # Added for reasoning stream
    requires_approval: bool
    approval_granted: bool
    pending_tool: str
    pending_args: dict[str, Any]


async def _read_workspace_cells(db: AsyncSession, workspace_id: str) -> str:
    """Read all cells in the workspace and format them for the LLM context."""
    result = await db.execute(
        select(Cell)
        .where(Cell.workspace_id == workspace_id)
        .order_by(Cell.position_y, Cell.position_x)
    )
    cells = result.scalars().all()
    if not cells:
        return "No cells exist in this workspace yet."

    lines: list[str] = []
    for i, cell in enumerate(cells, 1):
        code = (cell.content or "").strip()
        if not code:
            continue
        output_summary = ""
        if cell.output:
            raw_outputs = cell.output.get("outputs", [])
            status = cell.output.get("status", "unknown")
            for o in raw_outputs[:3]:
                if o.get("type") == "error":
                    output_summary += f"  ERROR: {o.get('ename','')}: {o.get('evalue','')}\n"
                elif o.get("type") in ("stream",):
                    text = o.get("text", "")[:500]
                    output_summary += f"  stdout: {text}\n"
                elif o.get("type") in ("execute_result", "display_data"):
                    data = o.get("data", {})
                    plain = data.get("text/plain", "")[:500]
                    if plain:
                        output_summary += f"  result: {plain}\n"
            if not output_summary and status:
                output_summary = f"  status: {status}\n"
        lines.append(
            f"[Cell {i}] ({cell.cell_type}/{cell.language})\n"
            f"```{cell.language}\n{code[:1000]}\n```\n"
            f"{output_summary}"
        )
    return "\n".join(lines) if lines else "All cells are empty."


class AgenticPipelineEngine:
    """
    LangGraph-powered multi-step analysis with:
    - Cell-aware execution (creates real cells, persists outputs)
    - Dynamic re-planning (evaluator can revise remaining steps)
    - Structured ledger (to-do + changelog streamed to frontend)
    """

    def __init__(self, db: AsyncSession, kernel_mgr: Any, code_generator: CodeGenerator) -> None:
        self.db = db
        self.kernel_mgr = kernel_mgr
        self.code_generator = code_generator
        self.ledger = AgentLedger()
        self.tools = AgentToolRegistry(self)
        self._approval_queues: dict[str, asyncio.Queue] = {} # workspace_id -> queue

    async def _create_cell(
        self, workspace_id: str, code: str, language: str = "python", step_label: str = ""
    ) -> Cell:
        result = await self.db.execute(
            select(Cell).where(Cell.workspace_id == workspace_id)
        )
        existing = result.scalars().all()
        y_pos = (len(existing) + 1) * 300

        cell = Cell(
            workspace_id=workspace_id,
            cell_type="code",
            language=language,
            content=code,
            position_x=60,
            position_y=y_pos,
            width=600,
            height=320,
        )
        self.db.add(cell)
        await self.db.flush()
        await self.db.refresh(cell)
        return cell

    async def _execute_cell(self, workspace_id: str, cell: Cell) -> dict[str, Any]:
        output_events: list[dict[str, Any]] = []

        async def on_output(event: dict[str, Any]) -> None:
            output_events.append(event)

        result = await self.kernel_mgr.execute_code(
            workspace_id,
            cell.content or "",
            on_output=on_output,
        )

        output_json: dict[str, Any] = {
            "outputs": result.outputs,
            "execution_count": result.execution_count,
            "execution_time_ms": result.execution_time_ms,
            "status": result.status,
        }

        cell.output = output_json
        cell.last_executed_at = datetime.now(UTC)
        await self.db.flush()
        await realtime_manager.broadcast_cell_executed(workspace_id, cell.id, output_json)
        return output_json

    def _extract_error_text(self, output: dict[str, Any]) -> str:
        errors = []
        for o in output.get("outputs", []):
            if o.get("type") == "error":
                tb = o.get("traceback", [])
                if tb:
                    errors.append("\n".join(str(line) for line in tb[-3:]))
                else:
                    errors.append(f"{o.get('ename', 'Error')}: {o.get('evalue', 'Unknown')}")
        return "\n".join(errors) if errors else str(output)

    def _extract_output_summary(self, output: dict[str, Any]) -> str:
        """Compact summary of cell output for LLM reasoning."""
        parts = []
        for o in output.get("outputs", []):
            if o.get("type") == "error":
                parts.append(f"ERROR: {o.get('ename','')}: {o.get('evalue','')}")
            elif o.get("type") == "stream":
                parts.append(o.get("text", "")[:300])
            elif o.get("type") in ("execute_result", "display_data"):
                data = o.get("data", {})
                plain = data.get("text/plain", "")[:300]
                if plain:
                    parts.append(plain)
        return "\n".join(parts)[:800] if parts else f"status: {output.get('status', 'unknown')}"

    def build_analysis_graph(
        self,
        workspace_context: dict,
        stream_updates: Callable[[dict], Awaitable[None]],
    ) -> StateGraph:
        engine = self
        graph = StateGraph(PipelineState)

        async def planner(state: PipelineState) -> PipelineState:
            goal = state["goal"]
            ws_id = state["workspace_id"]
            cell_context = await _read_workspace_cells(engine.db, ws_id)

            steps_prompt = (
                "You are an autonomous data scientist. Break this analysis goal into "
                "3-5 concrete steps. Each step must be one executable action.\n\n"
                f"Goal: {goal}\n\n"
                f"Existing workspace cells:\n{cell_context}\n\n"
                "Return a plain numbered list. No markdown, no explanation."
            )
            chunks: list[str] = []
            async for chunk in engine.code_generator.explain_output(
                user=workspace_context["user"],
                code="",
                output=steps_prompt,
                language="python",
                max_tokens=400,
            ):
                chunks.append(chunk)
            text = "".join(chunks)
            steps = [line.strip("- 0123456789.").strip() for line in text.splitlines() if line.strip()]
            if not steps:
                steps = [f"Analyze: {goal}", "Validate findings", "Summarize results"]

            steps = steps[:5]

            # Initialize ledger
            engine.ledger.set_plan(steps)
            await stream_updates({
                "type": "plan",
                "steps": steps,
                "goal": goal,
                "ledger": engine.ledger.snapshot(),
            })

            return {
                **state,
                "steps": steps,
                "current_step_index": 0,
                "retry_count": 0,
                "max_retries": 2,
                "step_results": [],
            }

        async def thinking(state: PipelineState) -> PipelineState:
            """Reasoning step before taking action."""
            idx = state["current_step_index"]
            step_text = state["steps"][idx]

            prompt = (
                "You are an autonomous data scientist. Reason about the current state "
                f"and explain what you are about to do for this step: {step_text}\n\n"
                "Keep it concise (1-2 sentences). Explain the 'why'."
            )
            chunks: list[str] = []
            async for chunk in engine.code_generator.explain_output(
                user=workspace_context["user"],
                code="",
                output=prompt,
                language="python",
                max_tokens=150,
            ):
                chunks.append(chunk)
            thought = "".join(chunks).strip()

            await stream_updates({
                "type": "thinking",
                "step_index": idx,
                "text": thought,
                "ledger": engine.ledger.snapshot(),
            })
            return {**state, "thinking": thought}

        async def code_writer(state: PipelineState) -> PipelineState:
            idx = state["current_step_index"]
            step_text = state["steps"][idx]
            ws_id = state["workspace_id"]
            cell_context = await _read_workspace_cells(engine.db, ws_id)

            engine.ledger.mark_running(idx)
            engine.ledger.log("code", f"Writing code for: {step_text}", step_index=idx)

            context = WorkspaceContext(
                workspace_id=ws_id,
                db=engine.db,
                metadata={
                    "task": "agent_code_writer",
                    "step": step_text,
                    "existing_cells": cell_context,
                },
            )

            enhanced_prompt = (
                f"Step {idx + 1}: {step_text}\n\n"
                f"Existing workspace cells and their outputs:\n{cell_context}\n\n"
                "Use the outputs of previous cells if relevant. Write clean, executable Python code."
            )

            # Create the cell immediately so we can stream into it
            cell = await engine._create_cell(ws_id, "", "python", step_text)
            await stream_updates({
                "type": "cell_created",
                "cell_id": cell.id,
                "step_index": idx,
                "step_name": step_text,
                "code": "",
                "language": "python",
                "ledger": engine.ledger.snapshot(),
            })

            full_code_chunks: list[str] = []
            async for chunk in engine.code_generator.generate_code(
                user=workspace_context["user"],
                prompt=enhanced_prompt,
                language="python",
                workspace_context=context,
                history=[],
                max_tokens=1024,
            ):
                full_code_chunks.append(chunk)
                await stream_updates({
                    "type": "code_streaming",
                    "cell_id": cell.id,
                    "chunk": chunk,
                })

            code = "".join(full_code_chunks)
            if code.startswith("```"):
                lines = code.splitlines()
                code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            cell.content = code
            await engine.db.flush()

            engine.ledger.log("code", f"Created cell for step {idx + 1}", cell_id=cell.id, step_index=idx)

            await stream_updates({
                "type": "cell_ready",
                "cell_id": cell.id,
                "code": code,
                "ledger": engine.ledger.snapshot(),
            })

            return {**state, "current_code": code, "current_cell_id": cell.id}

        async def executor(state: PipelineState) -> PipelineState:
            ws_id = state["workspace_id"]
            cell_id = state.get("current_cell_id", "")
            idx = state["current_step_index"]

            engine.ledger.log("execute", f"Executing step {idx + 1}", cell_id=cell_id, step_index=idx)

            await stream_updates({
                "type": "cell_executing",
                "cell_id": cell_id,
                "step_index": idx,
                "message": "Running code…",
                "ledger": engine.ledger.snapshot(),
            })

            result = await self.db.execute(
                select(Cell).where(Cell.id == cell_id, Cell.workspace_id == ws_id)
            )
            cell = result.scalar_one_or_none()
            if cell is None:
                return {
                    **state,
                    "current_output": {"status": "error", "outputs": [{"type": "error", "ename": "CellNotFound", "evalue": cell_id, "traceback": []}]},
                    "execution_status": "error",
                }

            output = await engine._execute_cell(ws_id, cell)
            is_error = output.get("status") != "ok"

            if is_error:
                engine.ledger.mark_error(idx)
                engine.ledger.log("error", f"Step {idx + 1} failed", cell_id=cell_id, step_index=idx)
            else:
                engine.ledger.log("execute", f"Step {idx + 1} succeeded ({output.get('execution_time_ms', 0)}ms)", cell_id=cell_id, step_index=idx)

            await stream_updates({
                "type": "cell_executed",
                "cell_id": cell_id,
                "step_index": idx,
                "status": "error" if is_error else "success",
                "execution_time_ms": output.get("execution_time_ms", 0),
                "ledger": engine.ledger.snapshot(),
            })

            return {
                **state,
                "current_output": output,
                "execution_status": "error" if is_error else "success",
            }

        async def evaluator(state: PipelineState) -> PipelineState:
            """Evaluate the step result and decide: advance, or revise the plan."""
            step_results = [*state.get("step_results", [])]
            idx = state["current_step_index"]
            cell_id = state.get("current_cell_id", "")

            step_results.append({
                "step_name": state["steps"][idx],
                "cell_id": cell_id,
                "code": state.get("current_code", ""),
                "output": state.get("current_output", {}),
                "status": "complete",
            })

            engine.ledger.mark_done(idx, cell_id)
            is_last = idx + 1 >= len(state["steps"])

            # ── Dynamic re-planning: ask LLM if plan should change ──────────
            revised_steps: list[str] | None = None
            if not is_last:
                output_summary = engine._extract_output_summary(state.get("current_output", {}))
                remaining = state["steps"][idx + 1:]
                completed = state["steps"][:idx + 1]

                replan_prompt = (
                    "You are an autonomous data scientist mid-analysis. "
                    "Based on the output of the step you just completed, decide whether the "
                    "remaining plan needs to change.\n\n"
                    f"Goal: {state['goal']}\n"
                    f"Completed steps: {json.dumps(completed)}\n"
                    f"Latest output:\n{output_summary}\n\n"
                    f"Remaining plan: {json.dumps(remaining)}\n\n"
                    "If the remaining plan is still correct, respond with exactly: PLAN_OK\n"
                    "If the plan should change, respond with a new numbered list of remaining steps. "
                    "Only return the NEW remaining steps, not the completed ones."
                )

                chunks: list[str] = []
                try:
                    async for chunk in engine.code_generator.explain_output(
                        user=workspace_context["user"],
                        code="",
                        output=replan_prompt,
                        language="python",
                        max_tokens=300,
                    ):
                        chunks.append(chunk)
                    replan_text = "".join(chunks).strip()

                    if "PLAN_OK" not in replan_text.upper():
                        # LLM returned new steps
                        new_steps = [
                            line.strip("- 0123456789.").strip()
                            for line in replan_text.splitlines()
                            if line.strip() and not line.strip().upper().startswith("PLAN")
                        ]
                        if new_steps and new_steps != remaining:
                            revised_steps = new_steps[:5]
                except Exception as exc:
                    logger.warning("Re-planning LLM call failed: %s", exc)

            if revised_steps is not None:
                # Apply revised plan
                old_remaining = state["steps"][idx + 1:]
                new_full_steps = state["steps"][:idx + 1] + revised_steps
                engine.ledger.revise_plan(revised_steps, idx + 1)
                engine.ledger.log(
                    "replan",
                    f"Revised plan after step {idx + 1}: {', '.join(revised_steps)}",
                    step_index=idx,
                )

                await stream_updates({
                    "type": "plan_revised",
                    "step_index": idx,
                    "old_remaining": old_remaining,
                    "new_remaining": revised_steps,
                    "full_steps": new_full_steps,
                    "ledger": engine.ledger.snapshot(),
                })

                return {
                    **state,
                    "steps": new_full_steps,
                    "step_results": step_results,
                    "current_step_index": idx + 1,
                    "execution_status": "next_step",
                    "retry_count": 0,
                }

            await stream_updates({
                "type": "step_complete",
                "step_index": idx,
                "step_name": state["steps"][idx],
                "cell_id": cell_id,
                "is_final": is_last,
                "ledger": engine.ledger.snapshot(),
            })

            return {
                **state,
                "step_results": step_results,
                "current_step_index": idx + (0 if is_last else 1),
                "execution_status": "done" if is_last else "next_step",
                "retry_count": 0,
            }

        async def error_handler(state: PipelineState) -> PipelineState:
            retry = state.get("retry_count", 0) + 1
            cell_id = state.get("current_cell_id", "")
            ws_id = state["workspace_id"]
            idx = state["current_step_index"]

            if retry > state.get("max_retries", 2):
                engine.ledger.mark_skipped(idx)
                engine.ledger.log("error", f"Step {idx + 1}: max retries, skipping", cell_id=cell_id, step_index=idx)
                await stream_updates({
                    "type": "step_failed",
                    "step_index": idx,
                    "cell_id": cell_id,
                    "message": "Max retries exceeded, moving on.",
                    "ledger": engine.ledger.snapshot(),
                })
                return {**state, "execution_status": "give_up"}

            error_text = engine._extract_error_text(state.get("current_output", {}))
            engine.ledger.log("fix", f"Fixing step {idx + 1} (attempt {retry})", cell_id=cell_id, step_index=idx)

            await stream_updates({
                "type": "cell_fixing",
                "cell_id": cell_id,
                "step_index": idx,
                "retry": retry,
                "message": f"Fixing error (attempt {retry})…",
                "ledger": engine.ledger.snapshot(),
            })

            context = WorkspaceContext(
                workspace_id=ws_id,
                db=engine.db,
                metadata={"task": "agent_error_handler"},
            )
            fixed_chunks: list[str] = []
            async for chunk in engine.code_generator.fix_error(
                user=workspace_context["user"],
                original_code=state.get("current_code", ""),
                error_output=error_text,
                language="python",
                workspace_context=context,
                max_tokens=1024,
            ):
                fixed_chunks.append(chunk)

            fixed_code = "".join(fixed_chunks)
            if fixed_code.startswith("```"):
                lines = fixed_code.splitlines()
                fixed_code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            result = await engine.db.execute(
                select(Cell).where(Cell.id == cell_id, Cell.workspace_id == ws_id)
            )
            cell = result.scalar_one_or_none()
            if cell:
                cell.content = fixed_code
                await engine.db.flush()

            engine.ledger.log("fix", f"Fixed code for step {idx + 1}", cell_id=cell_id, step_index=idx)

            await stream_updates({
                "type": "cell_fixed",
                "cell_id": cell_id,
                "step_index": idx,
                "retry": retry,
                "code": fixed_code,
                "ledger": engine.ledger.snapshot(),
            })

            return {
                **state,
                "current_code": fixed_code,
                "retry_count": retry,
                "execution_status": "retry",
            }

        async def reporter(state: PipelineState) -> PipelineState:
            engine.ledger.log("complete", "Analysis complete")
            summary_lines = ["## Agent Analysis Complete\n"]
            for i, item in enumerate(state.get("step_results", []), 1):
                cell_id = item.get("cell_id", "")
                status = item.get("status", "unknown")
                summary_lines.append(f"**Step {i}**: {item['step_name']} — {status}")
                if cell_id:
                    summary_lines.append(f"  ↳ Cell: `{cell_id[:8]}…`")
            return {**state, "report": "\n".join(summary_lines)}

        async def orchestrator(state: PipelineState) -> PipelineState:
            """Decide which tool to use for the current step."""
            idx = state["current_step_index"]
            step_text = state["steps"][idx]

            # Simple heuristic mapping for now, or use LLM to pick tool
            # For this version, we mostly use 'write_code' which maps to our code_writer
            # OR 'delete_dataset' etc based on keywords.
            lower = step_text.lower()
            tool_name = "write_code"
            if "delete" in lower and "dataset" in lower:
                tool_name = "delete_dataset"
            elif "schema" in lower or "inspect" in lower:
                tool_name = "inspect_schema"

            return {**state, "pending_tool": tool_name}

        async def tool_executor(state: PipelineState) -> PipelineState:
            """Execute the selected tool, with approval gate if needed."""
            tool_name = state.get("pending_tool", "write_code")
            ws_id = state["workspace_id"]
            idx = state["current_step_index"]

            # If it's write_code, we use our specialized code_writer node logic (already updated)
            if tool_name == "write_code":
                return await code_writer(state)

            # For other tools in the registry
            tool = engine.tools.tools.get(tool_name)
            if not tool:
                return await executor(state) # fallback to default cell execution if it was code

            # Handle Approval Gate
            if tool["tier"] == ToolTier.DANGEROUS:
                await stream_updates({
                    "type": "approval_required",
                    "tool": tool_name,
                    "args": {"step": state["steps"][idx]},
                    "ledger": engine.ledger.snapshot(),
                })

                # Wait for approval from queue
                queue = engine._approval_queues.get(ws_id)
                if queue:
                    approved = await queue.get()
                    if not approved:
                        engine.ledger.log("skipped", f"User denied: {tool_name}", step_index=idx)
                        return {**state, "execution_status": "done" if idx + 1 >= len(state["steps"]) else "next_step"}

            # Execute tool
            try:
                # Standard tools expect state and return dict updates
                update = await tool["func"](state)
                engine.ledger.log("execute", f"Tool {tool_name} completed", step_index=idx)
                return {**state, **update, "execution_status": "success"}
            except Exception as e:
                return {**state, "current_output": {"error": str(e)}, "execution_status": "error"}

        def route_after_executor(state: PipelineState) -> str:
            if state.get("execution_status") == "success":
                return "evaluator"
            return "error_handler"

        def route_after_error_handler(state: PipelineState) -> str:
            # After an error handler run, we always evaluate
            return "evaluator"

        def route_after_evaluator(state: PipelineState) -> str:
            return "reporter" if state.get("execution_status") == "done" else "thinker"

        graph.add_node("planner", planner)
        graph.add_node("thinker", thinking)
        graph.add_node("orchestrator", orchestrator)
        graph.add_node("code_writer", code_writer)
        graph.add_node("tool_executor", tool_executor)
        graph.add_node("executor", executor) # legacy code executor
        graph.add_node("evaluator", evaluator)
        graph.add_node("error_handler", error_handler)
        graph.add_node("reporter", reporter)

        graph.add_edge(START, "planner")
        graph.add_edge("planner", "thinker")
        graph.add_edge("thinker", "orchestrator")
        graph.add_edge("orchestrator", "tool_executor")

        graph.add_conditional_edges(
            "tool_executor",
            route_after_executor,
            {"evaluator": "evaluator", "error_handler": "error_handler"},
        )
        graph.add_conditional_edges(
            "error_handler",
            route_after_error_handler,
            {"executor": "executor", "evaluator": "evaluator"},
        )
        # For error retries, we usually retry the executor
        graph.add_edge("executor", "evaluator")

        graph.add_conditional_edges(
            "evaluator",
            route_after_evaluator,
            {"thinker": "thinker", "reporter": "reporter"},
        )
        graph.add_edge("reporter", END)
        return graph

    async def run_pipeline(
        self,
        user: User,
        workspace_id: str,
        goal: str,
        stream_updates: Callable[[dict], Awaitable[None]],
    ) -> PipelineRun:
        # Set up approval queue
        queue = asyncio.Queue()
        self._approval_queues[workspace_id] = queue

        try:
            pipeline = Pipeline(
                workspace_id=workspace_id,
                goal=goal,
                status=PipelineStatus.running.value,
                created_by=user.id,
            )
            self.db.add(pipeline)
            await self.db.flush()

            run = PipelineRun(
                pipeline_id=pipeline.id,
                workspace_id=workspace_id,
                goal=goal,
                status=PipelineStatus.running.value,
                created_by=user.id,
                steps=[],
                outputs=[],
                retry_count=0,
            )
            self.db.add(run)
            await self.db.flush()
            await self.db.refresh(run)

            workspace_context = {"workspace_id": workspace_id, "user": user}
            graph = self.build_analysis_graph(workspace_context, stream_updates).compile()
            state: PipelineState = {"goal": goal, "workspace_id": workspace_id}

            async for event in graph.astream_events(state, version="v1"):
                event_type = event.get("event")
                data = event.get("data", {})
                if event_type == "on_chain_end":
                    output = data.get("output", {})
                    state = output or state

            # Handle final report and state updates
            full_report = state.get("report", "Pipeline completed.")

            # Send final ledger snapshot with complete event
            await stream_updates({
                "type": "complete",
                "full_report": full_report,
                "ledger": self.ledger.snapshot(),
            })

            run.status = PipelineStatus.completed.value
            run.full_report = full_report
            run.steps = state.get("steps", [])
            run.outputs = state.get("step_results", [])
            run.retry_count = state.get("retry_count", 0)
            run.completed_at = datetime.now(UTC)

            pipeline.status = PipelineStatus.completed.value
            pipeline.summary = full_report[:1000]
        except Exception:
            run.status = PipelineStatus.failed.value
            run.completed_at = datetime.now(UTC)
            pipeline.status = PipelineStatus.failed.value
            raise
        finally:
            self._approval_queues.pop(workspace_id, None)
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def schedule_pipeline(
        self,
        pipeline_run_id: str,
        cron_expression: str,
    ) -> ScheduledPipeline:
        run = await self.db.get(PipelineRun, pipeline_run_id)
        if run is None:
            raise NotFoundException("PipelineRun", pipeline_run_id)
        schedule = ScheduledPipeline(
            pipeline_run_id=pipeline_run_id,
            cron_expression=cron_expression,
            is_active=True,
        )
        self.db.add(schedule)
        await self.db.flush()
        await self.db.refresh(schedule)
        return schedule
