"""Orion workflow authoring and execution APIs."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, Path, Request
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationError,
)
from app.core.workflow_engine import OrionEngine
from app.core.workflow_templates import get_workflow_templates, instantiate_template
from app.dependencies import CurrentUser, DBSession
from app.models.workflow import (
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowRunTriggeredBy,
    WorkflowTriggerType,
)
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowDetailSchema,
    WorkflowEdgeCreate,
    WorkflowEdgeSchema,
    WorkflowListItemSchema,
    WorkflowNodeCreate,
    WorkflowNodeRunSchema,
    WorkflowNodeSchema,
    WorkflowNodeUpdate,
    WorkflowRunDetailSchema,
    WorkflowRunSchema,
    WorkflowSchema,
    WorkflowTemplateInstantiateRequest,
    WorkflowTriggerRequest,
    WorkflowUpdate,
)
from app.services import workspace_service

router = APIRouter()
engine = OrionEngine()


async def _get_workflow(db: DBSession, workspace_id: str, workflow_id: str) -> Workflow:
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.nodes), selectinload(Workflow.edges))
        .where(Workflow.workspace_id == workspace_id, Workflow.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()
    if workflow is None:
        raise NotFoundException("Workflow", workflow_id)
    return workflow


@router.get("/templates", response_model=list[dict[str, Any]], summary="Built-in templates")
async def templates(workspace_id: str, current_user: CurrentUser, db: DBSession) -> list[dict[str, Any]]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    return get_workflow_templates()


@router.post("/from-template", response_model=WorkflowDetailSchema, status_code=201)
async def from_template(
    workspace_id: str,
    payload: WorkflowTemplateInstantiateRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> WorkflowDetailSchema:
    await workspace_service.check_workspace_role(db, workspace_id, current_user.id, ("editor", "admin"))
    template = instantiate_template(payload.template_key, payload.config_overrides or {})

    wf = template["workflow"]
    workflow = Workflow(
        workspace_id=workspace_id,
        name=payload.name,
        description=payload.description or template["description"],
        is_active=True,
        schedule_cron=wf.get("schedule_cron"),
        schedule_timezone=wf.get("schedule_timezone", "UTC"),
        trigger_type=wf.get("trigger_type", "manual"),
        trigger_config=wf.get("trigger_config", {}),
        webhook_secret=(payload.config_overrides or {}).get("webhook_secret"),
        created_by=current_user.id,
    )
    db.add(workflow)
    await db.flush()

    nodes: list[WorkflowNode] = []
    node_ids: list[str] = []
    alias_by_type: dict[str, str] = {}
    for node_template in wf.get("nodes", []):
        node = WorkflowNode(
            workflow_id=workflow.id,
            node_type=node_template["node_type"],
            label=node_template["label"],
            config=node_template.get("config", {}),
            position_x=node_template.get("position_x", 0),
            position_y=node_template.get("position_y", 0),
        )
        db.add(node)
        await db.flush()
        nodes.append(node)
        node_ids.append(node.id)
        alias_by_type.setdefault(node.node_type, node.id)

    for node in nodes:
        cfg = dict(node.config or {})
        if "expression" in cfg and isinstance(cfg["expression"], str):
            cfg["expression"] = cfg["expression"].replace("{{sql_node_id}}", alias_by_type.get("sql_query", ""))
        node.config = cfg

    edges: list[WorkflowEdge] = []
    for edge_template in wf.get("edges", []):
        edge = WorkflowEdge(
            workflow_id=workflow.id,
            source_node_id=node_ids[edge_template["from"]],
            target_node_id=node_ids[edge_template["to"]],
            condition=edge_template.get("condition", "always"),
        )
        db.add(edge)
        await db.flush()
        edges.append(edge)
    engine._detect_cycle(nodes, edges)

    return WorkflowDetailSchema(
        **WorkflowSchema.model_validate(workflow).model_dump(),
        nodes=[WorkflowNodeSchema.model_validate(n) for n in nodes],
        edges=[WorkflowEdgeSchema.model_validate(e) for e in edges],
        recent_runs=[],
    )


@router.post("/webhook/{id}", response_model=WorkflowRunSchema, summary="Public webhook")
async def webhook(
    workspace_id: str,
    request: Request,
    db: DBSession,
    x_forge_signature: str | None = Header(default=None),
    workflow_id: str = Path(alias="id"),
) -> WorkflowRunSchema:
    workflow = await _get_workflow(db, workspace_id, workflow_id)
    if workflow.trigger_type != WorkflowTriggerType.webhook.value:
        raise ForbiddenException("Workflow trigger type is not webhook")
    if not workflow.webhook_secret:
        raise ForbiddenException("Workflow webhook secret is not configured")

    raw = await request.body()
    digest = hmac.new(workflow.webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not x_forge_signature or not hmac.compare_digest(f"sha256={digest}", x_forge_signature):
        raise ForbiddenException("Invalid webhook signature")
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        payload = {"raw_payload": raw.decode("utf-8", errors="replace")}

    run = await engine.start_run(
        workflow_id=workflow_id,
        triggered_by=WorkflowRunTriggeredBy.webhook.value,
        triggered_by_user_id=None,
        run_metadata={
            "workspace_id": workspace_id,
            "webhook_received_at": datetime.now(UTC).isoformat(),
            **payload,
        },
        trigger_payload=payload,
    )
    return WorkflowRunSchema.model_validate(run)


@router.post("", response_model=WorkflowSchema, status_code=201, summary="Create workflow")
@router.post("/", include_in_schema=False)
async def create(workspace_id: str, payload: WorkflowCreate, current_user: CurrentUser, db: DBSession) -> WorkflowSchema:
    await workspace_service.check_workspace_role(db, workspace_id, current_user.id, ("editor", "admin"))
    workflow = Workflow(workspace_id=workspace_id, created_by=current_user.id, **payload.model_dump())
    db.add(workflow)
    await db.flush()
    await db.refresh(workflow)
    return WorkflowSchema.model_validate(workflow)


@router.get("", response_model=list[WorkflowListItemSchema], summary="List workflows")
@router.get("/", include_in_schema=False)
async def list_all(workspace_id: str, current_user: CurrentUser, db: DBSession) -> list[WorkflowListItemSchema]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    result = await db.execute(
        select(Workflow).where(Workflow.workspace_id == workspace_id).order_by(Workflow.created_at.desc())
    )
    workflows = list(result.scalars().all())
    ids = [w.id for w in workflows]
    counts: dict[str, int] = {}
    last: dict[str, str] = {}
    if ids:
        counts_result = await db.execute(
            select(WorkflowRun.workflow_id, func.count())
            .where(WorkflowRun.workflow_id.in_(ids))
            .group_by(WorkflowRun.workflow_id)
        )
        counts = dict(counts_result.all())
        last_result = await db.execute(
            select(WorkflowRun.workflow_id, WorkflowRun.status)
            .where(WorkflowRun.workflow_id.in_(ids))
            .order_by(WorkflowRun.workflow_id.asc(), WorkflowRun.created_at.desc())
        )
        for wid, status in last_result.all():
            if wid not in last:
                last[wid] = status
    return [
        WorkflowListItemSchema(
            **WorkflowSchema.model_validate(w).model_dump(),
            run_count=counts.get(w.id, 0),
            last_run_status=last.get(w.id),
        )
        for w in workflows
    ]


@router.get("/{id}", response_model=WorkflowDetailSchema, summary="Get workflow")
async def get_one(
    workspace_id: str,
    current_user: CurrentUser,
    db: DBSession,
    workflow_id: str = Path(alias="id"),
) -> WorkflowDetailSchema:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    workflow = await _get_workflow(db, workspace_id, workflow_id)
    runs = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(10)
    )
    return WorkflowDetailSchema(
        **WorkflowSchema.model_validate(workflow).model_dump(),
        nodes=[WorkflowNodeSchema.model_validate(n) for n in workflow.nodes],
        edges=[WorkflowEdgeSchema.model_validate(e) for e in workflow.edges],
        recent_runs=[WorkflowRunSchema.model_validate(r) for r in runs.scalars().all()],
    )


@router.put("/{id}", response_model=WorkflowSchema, summary="Update workflow")
async def update(
    workspace_id: str,
    payload: WorkflowUpdate,
    current_user: CurrentUser,
    db: DBSession,
    workflow_id: str = Path(alias="id"),
) -> WorkflowSchema:
    await workspace_service.check_workspace_role(db, workspace_id, current_user.id, ("editor", "admin"))
    workflow = await _get_workflow(db, workspace_id, workflow_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(workflow, key, value)
    await db.flush()
    await db.refresh(workflow)
    return WorkflowSchema.model_validate(workflow)


@router.delete("/{id}", status_code=200, summary="Delete workflow")
async def delete(
    workspace_id: str,
    current_user: CurrentUser,
    db: DBSession,
    workflow_id: str = Path(alias="id"),
) -> None:
    await workspace_service.check_workspace_role(db, workspace_id, current_user.id, ("editor", "admin"))
    workflow = await _get_workflow(db, workspace_id, workflow_id)
    await db.delete(workflow)
    await db.flush()


@router.post("/{id}/nodes", response_model=WorkflowNodeSchema, status_code=201, summary="Add node")
async def add_node(
    workspace_id: str,
    payload: WorkflowNodeCreate,
    current_user: CurrentUser,
    db: DBSession,
    workflow_id: str = Path(alias="id"),
) -> WorkflowNodeSchema:
    await workspace_service.check_workspace_role(db, workspace_id, current_user.id, ("editor", "admin"))
    await _get_workflow(db, workspace_id, workflow_id)
    node = WorkflowNode(workflow_id=workflow_id, **payload.model_dump())
    db.add(node)
    await db.flush()
    await db.refresh(node)
    return WorkflowNodeSchema.model_validate(node)


@router.put("/{id}/nodes/{nid}", response_model=WorkflowNodeSchema, summary="Update node")
async def update_node(
    workspace_id: str,
    nid: str,
    payload: WorkflowNodeUpdate,
    current_user: CurrentUser,
    db: DBSession,
    workflow_id: str = Path(alias="id"),
) -> WorkflowNodeSchema:
    await workspace_service.check_workspace_role(db, workspace_id, current_user.id, ("editor", "admin"))
    await _get_workflow(db, workspace_id, workflow_id)
    node = await db.get(WorkflowNode, nid)
    if node is None or node.workflow_id != workflow_id:
        raise NotFoundException("WorkflowNode", nid)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(node, key, value)
    await db.flush()
    await db.refresh(node)
    return WorkflowNodeSchema.model_validate(node)


@router.delete("/{id}/nodes/{nid}", status_code=200, summary="Delete node")
async def remove_node(
    workspace_id: str,
    nid: str,
    current_user: CurrentUser,
    db: DBSession,
    workflow_id: str = Path(alias="id"),
) -> None:
    await workspace_service.check_workspace_role(db, workspace_id, current_user.id, ("editor", "admin"))
    await _get_workflow(db, workspace_id, workflow_id)
    node = await db.get(WorkflowNode, nid)
    if node is None or node.workflow_id != workflow_id:
        raise NotFoundException("WorkflowNode", nid)
    await db.delete(node)
    await db.flush()


@router.post("/{id}/edges", response_model=WorkflowEdgeSchema, status_code=201, summary="Add edge")
async def add_edge(
    workspace_id: str,
    payload: WorkflowEdgeCreate,
    current_user: CurrentUser,
    db: DBSession,
    workflow_id: str = Path(alias="id"),
) -> WorkflowEdgeSchema:
    await workspace_service.check_workspace_role(db, workspace_id, current_user.id, ("editor", "admin"))
    workflow = await _get_workflow(db, workspace_id, workflow_id)
    node_ids = {node.id for node in workflow.nodes}
    if payload.source_node_id not in node_ids or payload.target_node_id not in node_ids:
        raise ValidationError("source_node_id and target_node_id must belong to workflow")
    edge = WorkflowEdge(workflow_id=workflow_id, **payload.model_dump())
    db.add(edge)
    await db.flush()
    await db.refresh(edge)
    try:
        refreshed = await _get_workflow(db, workspace_id, workflow_id)
        engine._detect_cycle(refreshed.nodes, refreshed.edges)
    except ValueError:
        await db.delete(edge)
        await db.flush()
        raise ConflictException("Edge creates a cycle") from None
    return WorkflowEdgeSchema.model_validate(edge)


@router.delete("/{id}/edges/{eid}", status_code=200, summary="Delete edge")
async def remove_edge(
    workspace_id: str,
    eid: str,
    current_user: CurrentUser,
    db: DBSession,
    workflow_id: str = Path(alias="id"),
) -> None:
    await workspace_service.check_workspace_role(db, workspace_id, current_user.id, ("editor", "admin"))
    await _get_workflow(db, workspace_id, workflow_id)
    edge = await db.get(WorkflowEdge, eid)
    if edge is None or edge.workflow_id != workflow_id:
        raise NotFoundException("WorkflowEdge", eid)
    await db.delete(edge)
    await db.flush()


@router.post("/{id}/trigger", response_model=WorkflowRunSchema, status_code=201, summary="Manual trigger")
async def trigger(
    workspace_id: str,
    payload: WorkflowTriggerRequest,
    current_user: CurrentUser,
    db: DBSession,
    workflow_id: str = Path(alias="id"),
) -> WorkflowRunSchema:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    await _get_workflow(db, workspace_id, workflow_id)
    run = await engine.start_run(
        workflow_id=workflow_id,
        triggered_by=WorkflowRunTriggeredBy.manual.value,
        triggered_by_user_id=current_user.id,
        run_metadata={"workspace_id": workspace_id, **payload.run_metadata},
        trigger_payload=payload.run_metadata,
    )
    return WorkflowRunSchema.model_validate(run)


@router.get("/{id}/runs", response_model=list[WorkflowRunSchema], summary="List runs")
async def runs(
    workspace_id: str,
    current_user: CurrentUser,
    db: DBSession,
    workflow_id: str = Path(alias="id"),
) -> list[WorkflowRunSchema]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    await _get_workflow(db, workspace_id, workflow_id)
    result = await db.execute(
        select(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id).order_by(WorkflowRun.created_at.desc())
    )
    return [WorkflowRunSchema.model_validate(run) for run in result.scalars().all()]


@router.get("/{id}/runs/{rid}", response_model=WorkflowRunDetailSchema, summary="Run detail")
async def run_detail(
    workspace_id: str,
    rid: str,
    current_user: CurrentUser,
    db: DBSession,
    workflow_id: str = Path(alias="id"),
) -> WorkflowRunDetailSchema:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    await _get_workflow(db, workspace_id, workflow_id)
    run = await db.get(WorkflowRun, rid)
    if run is None or run.workflow_id != workflow_id:
        raise NotFoundException("WorkflowRun", rid)
    node_runs_result = await db.execute(
        select(WorkflowNodeRun).where(WorkflowNodeRun.workflow_run_id == rid)
    )
    node_runs = list(node_runs_result.scalars().all())
    return WorkflowRunDetailSchema(
        **WorkflowRunSchema.model_validate(run).model_dump(),
        node_runs=[WorkflowNodeRunSchema.model_validate(nr) for nr in node_runs],
    )


@router.post("/{id}/runs/{rid}/cancel", response_model=WorkflowRunSchema, summary="Cancel run")
async def cancel(
    workspace_id: str,
    rid: str,
    current_user: CurrentUser,
    db: DBSession,
    workflow_id: str = Path(alias="id"),
) -> WorkflowRunSchema:
    await workspace_service.check_workspace_role(db, workspace_id, current_user.id, ("editor", "admin"))
    await _get_workflow(db, workspace_id, workflow_id)
    await engine.cancel_run(rid, current_user.id)
    run = await db.get(WorkflowRun, rid)
    if run is None:
        raise NotFoundException("WorkflowRun", rid)
    return WorkflowRunSchema.model_validate(run)
