"""Experiments router - FORGE MLflow tracking and model registry endpoints."""

from __future__ import annotations

import base64
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.core.exceptions import ValidationError
from app.core.experiment_tracker import ExperimentTracker
from app.dependencies import CurrentUser, DBSession
from app.services import workspace_service

router = APIRouter()
tracker = ExperimentTracker()
logger = logging.getLogger(__name__)


class CreateExperimentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class StartRunRequest(BaseModel):
    experiment_name: str = Field(min_length=1, max_length=255)
    run_name: str = Field(min_length=1, max_length=255)
    tags: dict[str, str] = Field(default_factory=dict)


class LogRunRequest(BaseModel):
    params: dict[str, Any] | None = None
    metrics: dict[str, float | int] | None = None
    step: int | None = None


class EndRunRequest(BaseModel):
    status: str = "FINISHED"


class LogModelRequest(BaseModel):
    model_name: str = Field(min_length=1, max_length=255)
    model_pickle_b64: str = Field(min_length=1)


class DeployModelRequest(BaseModel):
    model_name: str = Field(min_length=1, max_length=255)


class ExperimentRead(BaseModel):
    experiment_id: str
    name: str
    artifact_location: str | None
    lifecycle_stage: str


class RunRead(BaseModel):
    run_id: str
    run_name: str
    status: str
    params: dict[str, str]
    metrics: dict[str, float]
    start_time: int | None
    duration: float | None


@router.get(
    "/workspaces/{workspace_id}/experiments",
    response_model=list[ExperimentRead],
    summary="List all experiments in workspace",
)
async def list_workspace_experiments(
    workspace_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
) -> list[ExperimentRead]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    experiments = await tracker.list_experiments(workspace_id)
    return [ExperimentRead(**exp) for exp in experiments]


@router.post(
    "/workspaces/{workspace_id}/experiments",
    response_model=dict[str, str],
    summary="Create new MLflow experiment",
)
async def create_workspace_experiment(
    workspace_id: UUID,
    payload: CreateExperimentRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> dict[str, str]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    experiment_id = await tracker.get_or_create_experiment(workspace_id, payload.name)
    return {"experiment_id": experiment_id}


@router.get(
    "/workspaces/{workspace_id}/experiments/{experiment_id}/runs",
    response_model=list[RunRead],
    summary="List all runs with params and metrics",
)
async def list_experiment_runs(
    workspace_id: UUID,
    experiment_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> list[RunRead]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    runs = await tracker.list_runs(experiment_id)
    return [RunRead(**run) for run in runs]


@router.get(
    "/workspaces/{workspace_id}/experiments/{experiment_id}/runs/compare",
    summary="Compare runs side-by-side",
)
async def compare_experiment_runs(
    workspace_id: UUID,
    experiment_id: str,
    current_user: CurrentUser,
    db: DBSession,
    run_ids: str = Query(min_length=1),
) -> dict[str, Any]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    _ = experiment_id
    parsed_run_ids = [run_id.strip() for run_id in run_ids.split(",") if run_id.strip()]
    if not parsed_run_ids:
        raise ValidationError("Query param 'run_ids' must include at least one run ID")
    return await tracker.compare_runs(parsed_run_ids)


@router.post(
    "/workspaces/{workspace_id}/experiments/{experiment_id}/runs/{run_id}/deploy",
    summary="Deploy model to MLflow registry",
)
async def deploy_run_model(
    workspace_id: UUID,
    experiment_id: str,
    run_id: str,
    payload: DeployModelRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> dict[str, str]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    _ = experiment_id
    model_uri = await tracker.deploy_model(workspace_id, run_id, payload.model_name)
    return {
        "workspace_id": str(workspace_id),
        "run_id": run_id,
        "model_name": payload.model_name,
        "model_uri": model_uri,
        "stage": "Production",
    }


@router.get(
    "/workspaces/{workspace_id}/models",
    summary="List all registered models from MLflow registry",
)
async def list_workspace_models(
    workspace_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
) -> list[dict[str, Any]]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    return await tracker.list_models(workspace_id)


@router.post(
    "/workspaces/{workspace_id}/runs/start",
    summary="Start a FORGE experiment run",
)
@router.post(
    "/{workspace_id}/runs/start",
    include_in_schema=False,
)
async def start_run(
    workspace_id: UUID,
    payload: StartRunRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> dict[str, str]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    run_id = await tracker.start_run(
        workspace_id=workspace_id,
        experiment_name=payload.experiment_name,
        run_name=payload.run_name,
        tags=payload.tags,
    )
    return {"run_id": run_id}


@router.post(
    "/workspaces/{workspace_id}/runs/{run_id}/log",
    summary="Log params and/or metrics to run",
)
@router.post(
    "/{workspace_id}/runs/{run_id}/log",
    include_in_schema=False,
)
async def log_run(
    workspace_id: UUID,
    run_id: str,
    payload: LogRunRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> dict[str, str]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    if payload.params:
        await tracker.log_params(run_id, payload.params)
    if payload.metrics:
        await tracker.log_metrics(run_id, payload.metrics, step=payload.step)
    if not payload.params and not payload.metrics:
        raise ValidationError("Provide at least one of: params, metrics")
    return {"status": "ok"}


@router.post(
    "/workspaces/{workspace_id}/runs/{run_id}/model",
    summary="Log serialized sklearn/xgboost model",
)
@router.post(
    "/{workspace_id}/runs/{run_id}/model",
    include_in_schema=False,
)
async def log_model(
    workspace_id: UUID,
    run_id: str,
    payload: LogModelRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> dict[str, str]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    import pickle
    import cloudpickle

    try:
        b64_payload = payload.model_pickle_b64.strip()
        if not b64_payload:
            raise ValueError("Empty model payload")
        # Kernel-side JSON transport can introduce formatting differences;
        # normalize and accept both standard and URL-safe base64 forms.
        normalized = "".join(b64_payload.split())
        padding = "=" * ((4 - len(normalized) % 4) % 4)
        try:
            model_bytes = base64.b64decode(f"{normalized}{padding}", validate=False)
        except Exception:
            model_bytes = base64.urlsafe_b64decode(f"{normalized}{padding}")
        try:
            model = cloudpickle.loads(model_bytes)
        except Exception:
            model = pickle.loads(model_bytes)
    except Exception as exc:
        logger.exception("Failed to decode/deserialize model payload for run %s", run_id)
        raise ValidationError("Invalid model payload for 'model_pickle_b64'") from exc

    model_uri = await tracker.log_model(run_id, model, payload.model_name)
    return {"model_uri": model_uri}


@router.post(
    "/workspaces/{workspace_id}/runs/{run_id}/end",
    summary="End a FORGE experiment run",
)
@router.post(
    "/{workspace_id}/runs/{run_id}/end",
    include_in_schema=False,
)
async def end_run(
    workspace_id: UUID,
    run_id: str,
    payload: EndRunRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> dict[str, str]:
    await workspace_service.get_workspace(db, str(workspace_id), current_user.id)
    await tracker.end_run(run_id, payload.status)
    return {"status": payload.status.upper()}


# Backward-compatible endpoint used by existing frontend pages.
@router.get("", response_model=list[ExperimentRead], summary="List MLflow experiments")
@router.get("/", include_in_schema=False)
async def list_experiments_legacy(current_user: CurrentUser) -> list[ExperimentRead]:
    _ = current_user
    experiments = tracker._client.search_experiments(max_results=200)
    return [
        ExperimentRead(
            experiment_id=exp.experiment_id,
            name=exp.name,
            artifact_location=exp.artifact_location,
            lifecycle_stage=exp.lifecycle_stage,
        )
        for exp in experiments
    ]

