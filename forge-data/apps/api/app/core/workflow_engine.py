"""Orion workflow execution engine."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx
from jinja2 import Template
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.experiment_tracker import ExperimentTracker
from app.core.query_engine import FederatedQueryEngine
from app.core.security import create_kernel_token
from app.core.ws import ws_manager
from app.database import AsyncSessionLocal
from app.services.chat_service import chat_service
from app.models.cell import Cell
from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion
from app.models.publishing import PublishedDashboard
from app.models.workflow import (
    Workflow,
    WorkflowEdge,
    WorkflowEdgeCondition,
    WorkflowNode,
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowNodeType,
    WorkflowRun,
    WorkflowRunStatus,
)

logger = logging.getLogger(__name__)


def _send_orion_execute_node(workflow_run_id: str, node_id: str, run_context: dict[str, Any]) -> None:
    if settings.app_env == "test":
        try:
            asyncio.get_running_loop().create_task(
                OrionEngine().execute_node(workflow_run_id, node_id, run_context)
            )
            return
        except RuntimeError:
            asyncio.run(OrionEngine().execute_node(workflow_run_id, node_id, run_context))
            return

    from app.workers.celery_app import celery_app

    celery_app.send_task(
        "orion.execute_node",
        args=[workflow_run_id, node_id, run_context],
        headers={"workflow_run_id": workflow_run_id},
    )


class OrionEngine:
    async def start_run(
        self,
        workflow_id: str,
        triggered_by: str,
        triggered_by_user_id: str | None,
        run_metadata: dict[str, Any] | None = None,
        trigger_payload: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        metadata = run_metadata or {}
        payload = trigger_payload or {}
        async with AsyncSessionLocal() as db:
            workflow = await self._load_workflow(db, workflow_id)
            if not workflow.nodes:
                raise ValueError("Workflow has no nodes")

            self._detect_cycle(workflow.nodes, workflow.edges)

            run = WorkflowRun(
                workflow_id=workflow.id,
                triggered_by=triggered_by,
                triggered_by_user_id=triggered_by_user_id,
                status=WorkflowRunStatus.pending.value,
                run_metadata=metadata,
            )
            db.add(run)
            await db.flush()

            for node in workflow.nodes:
                db.add(
                    WorkflowNodeRun(
                        workflow_run_id=run.id,
                        node_id=node.id,
                        status=WorkflowNodeRunStatus.pending.value,
                    )
                )
            await db.flush()

            entry_nodes = self._entry_nodes(workflow.nodes, workflow.edges)
            run.status = WorkflowRunStatus.running.value
            run.started_at = datetime.now(UTC)
            await db.flush()
            await db.commit()
            await db.refresh(run)

        dispatch_context = {
            "workflow_id": workflow_id,
            "run_id": run.id,
            "triggered_by": triggered_by,
            "trigger_payload": payload,
            "workspace_id": workflow.workspace_id,
            "outputs": {},
            "workflow_run_id": run.id,
            "triggered_by_user_id": triggered_by_user_id,
            "run_metadata": metadata,
        }
        await self._broadcast_workflow_event(
            workflow.workspace_id,
            {
                "type": "workflow_run_started",
                "data": {
                    "workflow_id": workflow_id,
                    "run_id": run.id,
                    "triggered_by": triggered_by,
                },
            },
        )
        for entry in entry_nodes:
            _send_orion_execute_node(run.id, entry.id, dispatch_context)
        return run

    async def execute_node(
        self,
        workflow_run_id: str,
        node_id: str,
        run_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        ctx = run_context or {}
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise ValueError(f"WorkflowRun {workflow_run_id} not found")
            if run.status in {WorkflowRunStatus.cancelled.value, WorkflowRunStatus.failed.value}:
                return {"status": "skipped", "reason": "run_terminal"}

            node = await db.get(WorkflowNode, node_id)
            if node is None:
                raise ValueError(f"WorkflowNode {node_id} not found")

            node_run = await self._get_or_create_node_run(db, workflow_run_id, node_id)
            if node_run.status in {
                WorkflowNodeRunStatus.success.value,
                WorkflowNodeRunStatus.skipped.value,
                WorkflowNodeRunStatus.running.value,
            }:
                return {"status": node_run.status}

            node_run.status = WorkflowNodeRunStatus.running.value
            node_run.started_at = datetime.now(UTC)
            await db.flush()
            await db.commit()

        workspace_id = str(ctx.get("workspace_id") or "")
        if workspace_id:
            await self._broadcast_workflow_event(
                workspace_id,
                {
                    "type": "node_status_change",
                    "data": {
                        "workflow_id": ctx.get("workflow_id"),
                        "run_id": workflow_run_id,
                        "node_id": node_id,
                        "status": WorkflowNodeRunStatus.running.value,
                    },
                },
            )
        return await self._execute_with_retries(workflow_run_id, node_id, ctx)

    async def _execute_with_retries(
        self,
        workflow_run_id: str,
        node_id: str,
        run_context: dict[str, Any],
    ) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            node = await db.get(WorkflowNode, node_id)
            if node is None:
                raise ValueError(f"WorkflowNode {node_id} not found")
            node_run = await self._get_or_create_node_run(db, workflow_run_id, node_id)
            retry_count = max(0, node.retry_count)
            timeout_seconds = max(1, node.timeout_seconds)

        last_exc: Exception | None = None
        for attempt in range(retry_count + 1):
            try:
                start = time.perf_counter()
                result = await asyncio.wait_for(
                    self._dispatch_node_execution(workflow_run_id, node_id, run_context),
                    timeout=timeout_seconds,
                )
                elapsed_ms = round((time.perf_counter() - start) * 1000, 1)

                async with AsyncSessionLocal() as db:
                    node_run = await self._get_or_create_node_run(db, workflow_run_id, node_id)
                    node_run.status = WorkflowNodeRunStatus.success.value
                    node_run.finished_at = datetime.now(UTC)
                    node_run.output = result
                    node_run.logs = f"Execution completed in {elapsed_ms}ms"
                    await db.flush()
                    await db.commit()

                await self._broadcast_node_status(
                    run_context,
                    workflow_run_id,
                    node_id,
                    WorkflowNodeRunStatus.success.value,
                    output=result,
                )
                await self._dispatch_successors(workflow_run_id, node_id, run_context)
                await self._finalize_run_if_complete(workflow_run_id)
                return {"status": "success", "output": result}
            except Exception as exc:
                last_exc = exc
                if attempt < retry_count:
                    async with AsyncSessionLocal() as db:
                        node = await db.get(WorkflowNode, node_id)
                        delay = node.retry_delay_seconds if node else 60
                    await asyncio.sleep(max(0, delay))
                    continue
                break

        error_message = str(last_exc) if last_exc else "Unknown execution error"
        async with AsyncSessionLocal() as db:
            node = await db.get(WorkflowNode, node_id)
            node_run = await self._get_or_create_node_run(db, workflow_run_id, node_id)
            node_run.status = WorkflowNodeRunStatus.failed.value
            node_run.finished_at = datetime.now(UTC)
            node_run.error_message = error_message

            if node and node.on_failure_node_id:
                _send_orion_execute_node(workflow_run_id, node.on_failure_node_id, run_context)
            else:
                run = await db.get(WorkflowRun, workflow_run_id)
                if run:
                    run.status = WorkflowRunStatus.failed.value
                    run.finished_at = datetime.now(UTC)
                    run.error_message = error_message
            await db.flush()
            await db.commit()

        await self._broadcast_node_status(
            run_context,
            workflow_run_id,
            node_id,
            WorkflowNodeRunStatus.failed.value,
            error=error_message,
        )
        await self._finalize_run_if_complete(workflow_run_id)
        return {"status": "failed", "error": error_message}

    async def _dispatch_node_execution(
        self,
        workflow_run_id: str,
        node_id: str,
        ctx: dict[str, Any],
    ) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            node = await db.get(WorkflowNode, node_id)
            if node is None:
                raise ValueError(f"WorkflowNode {node_id} not found")

            dispatch = {
                WorkflowNodeType.code_cell.value: self._execute_code_cell,
                WorkflowNodeType.sql_query.value: self._execute_sql_query,
                WorkflowNodeType.api_call.value: self._execute_api_call,
                WorkflowNodeType.email_notify.value: self._execute_email_notify,
                WorkflowNodeType.dataset_upload.value: self._execute_dataset_upload,
                WorkflowNodeType.model_retrain.value: self._execute_model_retrain,
                WorkflowNodeType.dashboard_publish.value: self._execute_dashboard_publish,
                WorkflowNodeType.conditional.value: self._execute_conditional,
                WorkflowNodeType.wait.value: self._execute_wait,
            }.get(node.node_type)
            if dispatch is None:
                raise ValueError(f"Unsupported node_type '{node.node_type}'")

            result = await dispatch(node, ctx)
            outputs = ctx.setdefault("outputs", {})
            outputs[str(node.id)] = result
            return result

    async def _execute_code_cell(self, node: WorkflowNode, ctx: dict[str, Any]) -> dict[str, Any]:
        cell_id = str(node.config.get("cell_id", "")).strip()
        if not cell_id:
            raise ValueError("code_cell requires config.cell_id")

        async with AsyncSessionLocal() as db:
            cell = await db.get(Cell, cell_id)
            if cell is None:
                raise ValueError(f"Cell {cell_id} not found")
            workspace_id = cell.workspace_id
            code = cell.content or ""

        gateway_url = str(ctx.get("jupyter_gateway_url") or "").rstrip("/")
        token = str(ctx.get("jupyter_token") or "")
        start = time.perf_counter()
        if not gateway_url:
            return {
                "output": [],
                "logs": "Jupyter gateway not configured; execution mocked",
                "execution_time_ms": round((time.perf_counter() - start) * 1000, 1),
            }

        headers = {}
        if token:
            headers["Authorization"] = f"token {token}"
        kernel_token = create_kernel_token(workspace_id)
        payload = {"workspace_id": workspace_id, "cell_id": cell_id, "code": code, "token": kernel_token}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{gateway_url}/forge/execute", headers=headers, json=payload)
            if response.status_code >= 400:
                raise ValueError(f"Kernel gateway error: {response.status_code}")
            body = response.json()
        return {
            "output": body.get("output", body),
            "logs": body.get("logs", ""),
            "execution_time_ms": round((time.perf_counter() - start) * 1000, 1),
        }

    async def _execute_sql_query(self, node: WorkflowNode, ctx: dict[str, Any]) -> dict[str, Any]:
        sql = str(node.config.get("sql", "")).strip()
        if not sql:
            raise ValueError("sql_query requires config.sql")
        dataset_id = str(node.config.get("dataset_id", "")).strip()
        output_name = str(node.config.get("output_table_name", "")).strip() or f"orion_{node.id[:8]}"
        user_id = str(ctx.get("triggered_by_user_id") or "system")
        workspace_id = str(ctx.get("workspace_id") or "")

        engine = FederatedQueryEngine()
        if dataset_id:
            async with AsyncSessionLocal() as db:
                dataset = await db.get(Dataset, dataset_id)
                if dataset is None:
                    raise ValueError(f"Dataset {dataset_id} not found")
                source_type = dataset.source_type
                source_config = (dataset.connection_config or {}).copy()
                source_config["type"] = source_type
                if dataset.storage_path and "file_path" not in source_config:
                    source_config["file_path"] = dataset.storage_path
            with contextlib.suppress(Exception):
                await engine.register_source(user_id, f"dataset_{dataset_id}", source_config)

        result = await engine.execute_query(user_id=user_id, sql=sql)
        output_dataset_id = None
        if workspace_id and result.get("rows"):
            async with AsyncSessionLocal() as db:
                created = Dataset(
                    workspace_id=workspace_id,
                    created_by=ctx.get("triggered_by_user_id"),
                    name=output_name,
                    description="Generated by Orion sql_query node",
                    source_type="sql",
                    row_count=result.get("row_count"),
                    column_count=len(result.get("columns", [])),
                    schema_snapshot=[
                        {"name": col, "type": "unknown", "nullable": True}
                        for col in result.get("columns", [])
                    ],
                    metadata_info={"generated_by_workflow_node": node.id},
                )
                db.add(created)
                await db.flush()
                output_dataset_id = created.id
                await db.commit()

        return {
            "row_count": result.get("row_count", 0),
            "execution_time_ms": result.get("execution_time_ms", 0),
            "output_dataset_id": output_dataset_id,
        }

    async def _execute_api_call(self, node: WorkflowNode, ctx: dict[str, Any]) -> dict[str, Any]:
        method = str(node.config.get("method", "GET")).upper()
        url = str(node.config.get("url", "")).strip()
        if not url:
            raise ValueError("api_call requires config.url")
        headers = dict(node.config.get("headers") or {})
        body = node.config.get("body")
        auth_type = str(node.config.get("auth_type", "")).lower()
        auth_value = node.config.get("auth_value")

        auth = None
        if auth_type == "bearer" and auth_value:
            headers["Authorization"] = f"Bearer {auth_value}"
        elif auth_type == "basic" and auth_value:
            parts = str(auth_value).split(":", 1)
            if len(parts) != 2:
                raise ValueError("basic auth_value must be 'username:password'")
            auth = (parts[0], parts[1])
        elif auth_type == "api_key" and auth_value:
            headers["X-API-Key"] = str(auth_value)

        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(method, url, headers=headers, json=body, auth=auth)
        latency = round((time.perf_counter() - start) * 1000, 1)
        parsed_body: Any
        with contextlib.suppress(Exception):
            parsed_body = response.json()
            return {
                "status_code": response.status_code,
                "response_body": parsed_body,
                "latency_ms": latency,
            }
        return {
            "status_code": response.status_code,
            "response_body": response.text,
            "latency_ms": latency,
        }

    async def _execute_email_notify(self, node: WorkflowNode, ctx: dict[str, Any]) -> dict[str, Any]:
        to_list = node.config.get("to") or []
        subject = str(node.config.get("subject", "FORGE Orion Notification"))
        template_text = str(node.config.get("body_template", ""))
        rendered = Template(template_text).render(run_context=ctx, outputs=ctx.get("outputs", {}))

        smtp_host = str(ctx.get("smtp_host") or "")
        smtp_port = int(ctx.get("smtp_port") or 587)
        smtp_username = str(ctx.get("smtp_username") or "")
        smtp_password = str(ctx.get("smtp_password") or "")
        smtp_from = str(ctx.get("smtp_from") or "orion@forge.local")

        if not smtp_host:
            return {"sent_to": to_list, "subject": subject, "mock": True}

        import aiosmtplib

        message = (
            f"From: {smtp_from}\r\n"
            f"To: {', '.join(to_list)}\r\n"
            f"Subject: {subject}\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            f"{rendered}"
        )
        await aiosmtplib.send(
            message,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_username or None,
            password=smtp_password or None,
            start_tls=True,
        )
        return {"sent_to": to_list, "subject": subject, "mock": False}

    async def _execute_conditional(self, node: WorkflowNode, ctx: dict[str, Any]) -> dict[str, Any]:
        expression = str(node.config.get("expression", "")).strip()
        if not expression:
            raise ValueError("conditional requires config.expression")

        from RestrictedPython import compile_restricted
        from RestrictedPython.Guards import safe_builtins

        script = compile_restricted(f"result = bool({expression})", "<orion-conditional>", "exec")
        scope = {
            "__builtins__": safe_builtins,
            "run_context": ctx,
            "outputs": ctx.get("outputs", {}),
            "bool": bool,
        }
        local_vars: dict[str, Any] = {}
        exec(script, scope, local_vars)
        return {"result": bool(local_vars.get("result")), "expression": expression}

    async def _execute_wait(self, node: WorkflowNode, ctx: dict[str, Any]) -> dict[str, Any]:
        seconds = int(node.config.get("seconds", 0))
        await asyncio.sleep(max(0, seconds))
        passthrough = {k: v for k, v in node.config.items() if k != "seconds"}
        return {"waited_seconds": max(0, seconds), **passthrough}

    async def _execute_model_retrain(self, node: WorkflowNode, ctx: dict[str, Any]) -> dict[str, Any]:
        experiment_id = str(node.config.get("experiment_id", "")).strip()
        if not experiment_id:
            raise ValueError("model_retrain requires config.experiment_id")
        parameters = node.config.get("parameters") or {}
        workspace_id = str(ctx.get("workspace_id") or "")
        tracker = ExperimentTracker()
        run_id = await tracker.start_run(
            workspace_id=workspace_id or "orion",
            experiment_name=f"workflow_{experiment_id}",
            run_name=f"orion_retrain_{node.id[:8]}",
            tags={"orion.node_id": node.id, "orion.workflow_run_id": ctx.get("run_id", "")},
        )
        await tracker.log_params(run_id, parameters)
        await tracker.end_run(run_id, status="FINISHED")
        return {"experiment_id": experiment_id, "mlflow_run_id": run_id, "parameters": parameters}

    async def _execute_dataset_upload(self, node: WorkflowNode, ctx: dict[str, Any]) -> dict[str, Any]:
        dataset_id = str(node.config.get("dataset_id", "")).strip()
        file_url = str(node.config.get("file_url", "")).strip()
        version_message = str(node.config.get("version_message", "Orion upload"))
        if not dataset_id:
            raise ValueError("dataset_upload requires config.dataset_id")
        if not file_url:
            raise ValueError("dataset_upload requires config.file_url")

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(file_url)
            response.raise_for_status()
            payload = response.content

        async with AsyncSessionLocal() as db:
            dataset = await db.get(Dataset, dataset_id)
            if dataset is None:
                raise ValueError(f"Dataset {dataset_id} not found")
            dataset.version += 1
            dataset.size_bytes = len(payload)
            dataset.metadata_info = {
                **(dataset.metadata_info or {}),
                "last_upload_url": file_url,
                "last_upload_at": datetime.now(UTC).isoformat(),
            }
            version = DatasetVersion(
                dataset_id=dataset.id,
                version_number=dataset.version,
                message=version_message,
                schema_snapshot=dataset.schema_snapshot or {},
                row_count=dataset.row_count,
                size_bytes=dataset.size_bytes,
                parquet_path=f"versions/{dataset.id}/v{dataset.version}.parquet",
                created_by=ctx.get("triggered_by_user_id"),
            )
            db.add(version)
            await db.flush()
            await db.commit()
        return {"dataset_id": dataset_id, "version": version.version_number, "file_url": file_url}

    async def _execute_dashboard_publish(self, node: WorkflowNode, ctx: dict[str, Any]) -> dict[str, Any]:
        dashboard_id = str(node.config.get("dashboard_id", "")).strip()
        if not dashboard_id:
            raise ValueError("dashboard_publish requires config.dashboard_id")
        async with AsyncSessionLocal() as db:
            dashboard = await db.get(PublishedDashboard, dashboard_id)
            if dashboard is None:
                raise ValueError(f"Dashboard {dashboard_id} not found")
            dashboard.last_refreshed_at = datetime.now(UTC)
            await db.flush()
            await db.commit()
        return {"dashboard_id": dashboard_id, "published": True}

    async def cancel_run(self, workflow_run_id: str, user_id: str) -> None:
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise ValueError(f"WorkflowRun {workflow_run_id} not found")
            run.status = WorkflowRunStatus.cancelled.value
            run.finished_at = datetime.now(UTC)
            run.error_message = f"Cancelled by user {user_id}"

            result = await db.execute(
                select(WorkflowNodeRun).where(WorkflowNodeRun.workflow_run_id == workflow_run_id)
            )
            node_runs = list(result.scalars().all())
            for node_run in node_runs:
                if node_run.status in {
                    WorkflowNodeRunStatus.pending.value,
                    WorkflowNodeRunStatus.running.value,
                }:
                    node_run.status = WorkflowNodeRunStatus.skipped.value
                    node_run.finished_at = datetime.now(UTC)
                    node_run.error_message = "Cancelled"
            await db.flush()
            await db.commit()

        with contextlib.suppress(Exception):
            from app.workers.celery_app import celery_app

            celery_app.control.revoke_by_stamped_headers({"workflow_run_id": workflow_run_id}, terminate=True)

    def _detect_cycle(self, nodes: Sequence[WorkflowNode], edges: Sequence[WorkflowEdge]) -> bool:
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            adjacency[edge.source_node_id].append(edge.target_node_id)

        visited: set[str] = set()
        stack: set[str] = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            stack.add(node_id)
            for neighbor in adjacency.get(node_id, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in stack:
                    return True
            stack.remove(node_id)
            return False

        for node in nodes:
            if node.id not in visited and dfs(node.id):
                raise ValueError("Workflow contains a cycle")
        return False

    async def _dispatch_successors(
        self,
        workflow_run_id: str,
        node_id: str,
        run_context: dict[str, Any],
    ) -> None:
        async with AsyncSessionLocal() as db:
            node = await db.get(WorkflowNode, node_id)
            if node is None:
                return
            workflow = await self._load_workflow(db, node.workflow_id)

            outgoing = [
                edge
                for edge in workflow.edges
                if edge.source_node_id == node_id
                and edge.condition in {WorkflowEdgeCondition.always.value, WorkflowEdgeCondition.on_success.value}
            ]
            target_ids = [edge.target_node_id for edge in outgoing]
            if node.on_success_node_id:
                target_ids.append(node.on_success_node_id)

            unique_targets = sorted(set(target_ids))
            for target_id in unique_targets:
                if await self._can_execute_node(db, workflow_run_id, target_id):
                    _send_orion_execute_node(workflow_run_id, target_id, run_context)

    async def _can_execute_node(self, db, workflow_run_id: str, node_id: str) -> bool:
        run = await db.get(WorkflowRun, workflow_run_id)
        if run is None:
            return False
        workflow = await self._load_workflow(db, run.workflow_id)
        incoming = [edge for edge in workflow.edges if edge.target_node_id == node_id]
        if not incoming:
            return True

        result = await db.execute(
            select(WorkflowNodeRun).where(
                WorkflowNodeRun.workflow_run_id == workflow_run_id,
                WorkflowNodeRun.node_id.in_([edge.source_node_id for edge in incoming]),
            )
        )
        status_by_node = {nr.node_id: nr.status for nr in result.scalars().all()}
        for edge in incoming:
            source_status = status_by_node.get(edge.source_node_id)
            if edge.condition == WorkflowEdgeCondition.always.value:
                if source_status not in {
                    WorkflowNodeRunStatus.success.value,
                    WorkflowNodeRunStatus.failed.value,
                    WorkflowNodeRunStatus.skipped.value,
                }:
                    return False
            elif edge.condition == WorkflowEdgeCondition.on_success.value:
                if source_status != WorkflowNodeRunStatus.success.value:
                    return False
            elif (
                edge.condition == WorkflowEdgeCondition.on_failure.value
                and source_status != WorkflowNodeRunStatus.failed.value
            ):
                return False
        return True

    async def _finalize_run_if_complete(self, workflow_run_id: str) -> None:
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, workflow_run_id)
            if run is None:
                return
            workflow = await db.get(Workflow, run.workflow_id)
            result = await db.execute(
                select(WorkflowNodeRun).where(WorkflowNodeRun.workflow_run_id == workflow_run_id)
            )
            node_runs = list(result.scalars().all())
            if not node_runs:
                return
            statuses = {nr.status for nr in node_runs}
            if WorkflowNodeRunStatus.running.value in statuses or WorkflowNodeRunStatus.pending.value in statuses:
                return
            if run.status in {WorkflowRunStatus.cancelled.value, WorkflowRunStatus.failed.value}:
                if not run.finished_at:
                    run.finished_at = datetime.now(UTC)
            elif WorkflowNodeRunStatus.failed.value in statuses:
                run.status = WorkflowRunStatus.failed.value
                run.finished_at = datetime.now(UTC)
                failed = next((nr for nr in node_runs if nr.status == WorkflowNodeRunStatus.failed.value), None)
                run.error_message = failed.error_message if failed else run.error_message
            else:
                run.status = WorkflowRunStatus.success.value
                run.finished_at = datetime.now(UTC)
                run.error_message = None
            await db.flush()
            await db.commit()
            workflow_id = run.workflow_id
            run_id = run.id
            status = run.status
            if workflow and run.finished_at and run.started_at:
                duration_seconds = (run.finished_at - run.started_at).total_seconds()
            else:
                duration_seconds = None
            workspace_id = workflow.workspace_id if workflow else None
        if workspace_id:
            if workflow:
                status_marker = "✓" if status == WorkflowRunStatus.success.value else "✗"
                content = f"Workflow '{workflow.name}' completed {status_marker}"
                metadata = {
                    "event": "workflow_run_completed",
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "status": status,
                }
                async with AsyncSessionLocal() as chat_db:
                    await chat_service.send_system_message(chat_db, workspace_id, content, metadata=metadata)
                    await chat_db.commit()
            await self._broadcast_workflow_event(
                workspace_id,
                {
                    "type": "workflow_run_completed",
                    "data": {
                        "workflow_id": workflow_id,
                        "run_id": run_id,
                        "status": status,
                        "duration_seconds": duration_seconds,
                    },
                },
            )

    async def _load_workflow(self, db, workflow_id: str) -> Workflow:
        result = await db.execute(
            select(Workflow)
            .options(
                selectinload(Workflow.nodes),
                selectinload(Workflow.edges),
            )
            .where(Workflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()
        if workflow is None:
            raise ValueError(f"Workflow {workflow_id} not found")
        return workflow

    async def _get_or_create_node_run(self, db, workflow_run_id: str, node_id: str) -> WorkflowNodeRun:
        result = await db.execute(
            select(WorkflowNodeRun).where(
                WorkflowNodeRun.workflow_run_id == workflow_run_id,
                WorkflowNodeRun.node_id == node_id,
            )
        )
        node_run = result.scalar_one_or_none()
        if node_run:
            return node_run
        node_run = WorkflowNodeRun(
            workflow_run_id=workflow_run_id,
            node_id=node_id,
            status=WorkflowNodeRunStatus.pending.value,
        )
        db.add(node_run)
        await db.flush()
        return node_run

    def _entry_nodes(
        self,
        nodes: Sequence[WorkflowNode],
        edges: Sequence[WorkflowEdge],
    ) -> list[WorkflowNode]:
        incoming = {edge.target_node_id for edge in edges}
        return [node for node in nodes if node.id not in incoming]

    async def list_runs_for_cleanup(self) -> list[tuple[str, str, datetime]]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(WorkflowRun.id, WorkflowRun.workflow_id, WorkflowRun.created_at).order_by(
                    WorkflowRun.workflow_id.asc(), WorkflowRun.created_at.desc()
                )
            )
            return list(result.all())

    async def cleanup_old_runs(self, keep_days: int = 90, keep_last_per_workflow: int = 5) -> int:
        cutoff = datetime.now(UTC).timestamp() - keep_days * 86400
        deleted = 0
        runs = await self.list_runs_for_cleanup()
        seen_per_workflow: dict[str, int] = defaultdict(int)
        ids_to_delete: list[str] = []
        for run_id, workflow_id, created_at in runs:
            seen_per_workflow[workflow_id] += 1
            keep_newest = seen_per_workflow[workflow_id] <= keep_last_per_workflow
            if keep_newest:
                continue
            if created_at and created_at.timestamp() < cutoff:
                ids_to_delete.append(run_id)
        if not ids_to_delete:
            return 0
        async with AsyncSessionLocal() as db:
            await db.execute(delete(WorkflowRun).where(WorkflowRun.id.in_(ids_to_delete)))
            await db.commit()
        deleted = len(ids_to_delete)
        logger.info("Cleaned up %d old workflow runs", deleted)
        return deleted

    async def scheduled_candidates(self) -> list[Workflow]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Workflow).where(
                    Workflow.is_active.is_(True),
                    Workflow.trigger_type == "schedule",
                    Workflow.schedule_cron.is_not(None),
                )
            )
            return list(result.scalars().all())

    async def workflow_run_stats(self, workflow_id: str) -> tuple[int, str | None]:
        async with AsyncSessionLocal() as db:
            count_result = await db.execute(
                select(func.count()).select_from(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id)
            )
            count = count_result.scalar_one()
            last_result = await db.execute(
                select(WorkflowRun.status)
                .where(WorkflowRun.workflow_id == workflow_id)
                .order_by(WorkflowRun.created_at.desc())
                .limit(1)
            )
            last = last_result.scalar_one_or_none()
            return count, last

    async def _broadcast_workflow_event(self, workspace_id: str, message: dict[str, Any]) -> None:
        await ws_manager.broadcast_to_workspace(workspace_id, message)

    async def _broadcast_node_status(
        self,
        run_context: dict[str, Any],
        run_id: str,
        node_id: str,
        status: str,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        workspace_id = str(run_context.get("workspace_id") or "")
        if not workspace_id:
            return
        data: dict[str, Any] = {
            "workflow_id": run_context.get("workflow_id"),
            "run_id": run_id,
            "node_id": node_id,
            "status": status,
        }
        if output is not None:
            data["output"] = output
        if error is not None:
            data["error"] = error
        await self._broadcast_workflow_event(workspace_id, {"type": "node_status_change", "data": data})
