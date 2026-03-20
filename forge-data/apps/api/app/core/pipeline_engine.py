"""LangGraph-backed agentic pipeline engine."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.code_generator import CodeGenerator, WorkspaceContext
from app.core.exceptions import NotFoundException
from app.models.pipeline import Pipeline, PipelineRun, PipelineStatus, ScheduledPipeline
from app.models.user import User


class PipelineState(TypedDict, total=False):
    goal: str
    workspace_id: str
    steps: list[str]
    current_step_index: int
    current_code: str
    current_output: dict[str, Any]
    retry_count: int
    max_retries: int
    execution_status: str
    report: str
    step_results: list[dict[str, Any]]


class AgenticPipelineEngine:
    """
    LangGraph-powered multi-step analysis pipelines.
    Users describe a goal, the agent breaks it into steps and executes them.
    Pipelines can be scheduled (via Celery beat).
    """

    def __init__(self, db: AsyncSession, kernel_mgr: Any, code_generator: CodeGenerator) -> None:
        self.db = db
        self.kernel_mgr = kernel_mgr
        self.code_generator = code_generator

    def build_analysis_graph(self, workspace_context: dict) -> StateGraph:
        graph = StateGraph(PipelineState)

        async def planner(state: PipelineState) -> PipelineState:
            goal = state["goal"]
            steps_prompt = (
                "Break this analysis goal into 3-7 concrete actionable steps. "
                "Return as newline list without markdown.\n\n"
                f"Goal: {goal}"
            )
            chunks: list[str] = []
            async for chunk in self.code_generator.explain_output(
                user=workspace_context["user"],
                code="",
                output=steps_prompt,
                language="python",
            ):
                chunks.append(chunk)
            text = "".join(chunks)
            steps = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
            if not steps:
                steps = [f"Analyze goal: {goal}", "Validate findings", "Summarize results"]
            return {
                **state,
                "steps": steps[:7],
                "current_step_index": 0,
                "retry_count": 0,
                "max_retries": 3,
                "step_results": [],
            }

        async def code_writer(state: PipelineState) -> PipelineState:
            idx = state["current_step_index"]
            step_text = state["steps"][idx]
            context = WorkspaceContext(
                workspace_id=workspace_context["workspace_id"],
                db=self.db,
                metadata={"task": "pipeline_code_writer", "step": step_text},
            )
            chunks: list[str] = []
            async for chunk in self.code_generator.generate_code(
                user=workspace_context["user"],
                prompt=step_text,
                language="python",
                workspace_context=context,
                history=[],
            ):
                chunks.append(chunk)
            return {**state, "current_code": "".join(chunks)}

        async def executor(state: PipelineState) -> PipelineState:
            output_events: list[dict[str, Any]] = []

            async def on_output(event: dict[str, Any]) -> None:
                output_events.append(event)

            result = await self.kernel_mgr.execute_code(
                workspace_context["workspace_id"],
                state.get("current_code", ""),
                on_output=on_output,
            )
            return {
                **state,
                "current_output": {
                    "status": result.status,
                    "outputs": result.outputs,
                    "execution_time_ms": result.execution_time_ms,
                },
                "execution_status": "success" if result.status == "ok" else "error",
            }

        async def evaluator(state: PipelineState) -> PipelineState:
            step_results = [*state.get("step_results", [])]
            idx = state["current_step_index"]
            step_results.append(
                {
                    "step_name": state["steps"][idx],
                    "code": state.get("current_code", ""),
                    "output": state.get("current_output", {}),
                    "status": "complete",
                }
            )
            is_done = idx + 1 >= len(state["steps"])
            return {
                **state,
                "step_results": step_results,
                "current_step_index": idx + (0 if is_done else 1),
                "execution_status": "done" if is_done else "next_step",
                "retry_count": 0,
            }

        async def error_handler(state: PipelineState) -> PipelineState:
            retry = state.get("retry_count", 0) + 1
            if retry > state.get("max_retries", 3):
                return {**state, "execution_status": "give_up"}
            fixed_chunks: list[str] = []
            context = WorkspaceContext(
                workspace_id=workspace_context["workspace_id"],
                db=self.db,
                metadata={"task": "pipeline_error_handler"},
            )
            async for chunk in self.code_generator.fix_error(
                user=workspace_context["user"],
                original_code=state.get("current_code", ""),
                error_output=str(state.get("current_output", {})),
                language="python",
                workspace_context=context,
            ):
                fixed_chunks.append(chunk)
            return {
                **state,
                "current_code": "".join(fixed_chunks),
                "retry_count": retry,
                "execution_status": "retry",
            }

        async def reporter(state: PipelineState) -> PipelineState:
            summary_lines = ["Pipeline findings summary:"]
            for item in state.get("step_results", []):
                summary_lines.append(f"- {item['step_name']}: {item['status']}")
            return {**state, "report": "\n".join(summary_lines)}

        def route_after_executor(state: PipelineState) -> str:
            return "evaluator" if state.get("execution_status") == "success" else "error_handler"

        def route_after_error_handler(state: PipelineState) -> str:
            return "code_writer" if state.get("execution_status") == "retry" else "reporter"

        def route_after_evaluator(state: PipelineState) -> str:
            return "reporter" if state.get("execution_status") == "done" else "code_writer"

        graph.add_node("planner", planner)
        graph.add_node("code_writer", code_writer)
        graph.add_node("executor", executor)
        graph.add_node("evaluator", evaluator)
        graph.add_node("error_handler", error_handler)
        graph.add_node("reporter", reporter)

        graph.add_edge(START, "planner")
        graph.add_edge("planner", "code_writer")
        graph.add_edge("code_writer", "executor")
        graph.add_conditional_edges(
            "executor",
            route_after_executor,
            {"evaluator": "evaluator", "error_handler": "error_handler"},
        )
        graph.add_conditional_edges(
            "error_handler",
            route_after_error_handler,
            {"code_writer": "code_writer", "reporter": "reporter"},
        )
        graph.add_conditional_edges(
            "evaluator",
            route_after_evaluator,
            {"code_writer": "code_writer", "reporter": "reporter"},
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
        graph = self.build_analysis_graph(workspace_context).compile()
        state: PipelineState = {"goal": goal, "workspace_id": workspace_id}

        try:
            async for event in graph.astream_events(state, version="v1"):
                event_type = event.get("event")
                node_name = event.get("name", "")
                data = event.get("data", {})
                if event_type == "on_chain_start":
                    await stream_updates(
                        {
                            "type": "step_start",
                            "step_name": node_name,
                            "description": f"Entering {node_name}",
                        }
                    )
                if event_type == "on_chain_end":
                    output = data.get("output", {})
                    if node_name == "code_writer":
                        await stream_updates(
                            {
                                "type": "code",
                                "code": output.get("current_code", ""),
                                "language": "python",
                            }
                        )
                    if node_name == "executor":
                        await stream_updates(
                            {"type": "output", "output": output.get("current_output", {})}
                        )
                    if node_name == "evaluator":
                        await stream_updates(
                            {
                                "type": "step_complete",
                                "step_name": "evaluator",
                                "summary": output.get("execution_status", "done"),
                            }
                        )
                    state = output or state

            full_report = state.get("report", "Pipeline completed.")
            await stream_updates({"type": "complete", "full_report": full_report})

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
