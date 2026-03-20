"""Experiments router — MLflow experiment and run tracking."""

from typing import Any

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.config import settings
from app.dependencies import CurrentUser

router = APIRouter()


class ExperimentRead(BaseModel):
    experiment_id: str
    name: str
    artifact_location: str | None
    lifecycle_stage: str
    tags: dict[str, str]


class RunMetric(BaseModel):
    key: str
    value: float
    step: int
    timestamp: int


class RunRead(BaseModel):
    run_id: str
    experiment_id: str
    status: str
    start_time: int | None
    end_time: int | None
    params: dict[str, str]
    metrics: dict[str, float]
    tags: dict[str, str]
    artifact_uri: str | None


@router.get("", response_model=list[ExperimentRead], summary="List MLflow experiments")
@router.get("/", include_in_schema=False)
async def list_experiments(current_user: CurrentUser) -> list[ExperimentRead]:
    """Proxy request to the MLflow tracking server."""
    data = await _mlflow_get("/api/2.0/mlflow/experiments/search", {"max_results": 200})
    experiments = data.get("experiments", [])
    return [
        ExperimentRead(
            experiment_id=e["experiment_id"],
            name=e["name"],
            artifact_location=e.get("artifact_location"),
            lifecycle_stage=e.get("lifecycle_stage", "active"),
            tags={t["key"]: t["value"] for t in e.get("tags", [])},
        )
        for e in experiments
    ]


@router.get("/{experiment_id}", response_model=ExperimentRead, summary="Get an experiment")
async def get_experiment(experiment_id: str, current_user: CurrentUser) -> ExperimentRead:
    data = await _mlflow_get(
        "/api/2.0/mlflow/experiments/get",
        {"experiment_id": experiment_id},
    )
    e = data["experiment"]
    return ExperimentRead(
        experiment_id=e["experiment_id"],
        name=e["name"],
        artifact_location=e.get("artifact_location"),
        lifecycle_stage=e.get("lifecycle_stage", "active"),
        tags={t["key"]: t["value"] for t in e.get("tags", [])},
    )


@router.get(
    "/{experiment_id}/runs",
    response_model=list[RunRead],
    summary="List runs for an experiment",
)
async def list_runs(
    experiment_id: str,
    current_user: CurrentUser,
    max_results: int = Query(default=50, ge=1, le=1000),
) -> list[RunRead]:
    data = await _mlflow_post(
        "/api/2.0/mlflow/runs/search",
        {
            "experiment_ids": [experiment_id],
            "max_results": max_results,
            "order_by": ["start_time DESC"],
        },
    )
    runs = data.get("runs", [])
    return [_parse_run(r) for r in runs]


@router.get("/{experiment_id}/runs/{run_id}", response_model=RunRead, summary="Get a run")
async def get_run(
    experiment_id: str,
    run_id: str,
    current_user: CurrentUser,
) -> RunRead:
    data = await _mlflow_get("/api/2.0/mlflow/runs/get", {"run_id": run_id})
    return _parse_run(data["run"])


# ── MLflow API helpers ─────────────────────────────────────────────────────────


async def _mlflow_get(path: str, params: dict[str, Any] | None = None) -> dict:
    base = settings.mlflow_tracking_uri.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{base}{path}", params=params)
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        from app.core.exceptions import ServiceUnavailableException

        raise ServiceUnavailableException("MLflow") from exc


async def _mlflow_post(path: str, body: dict[str, Any]) -> dict:
    base = settings.mlflow_tracking_uri.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{base}{path}", json=body)
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        from app.core.exceptions import ServiceUnavailableException

        raise ServiceUnavailableException("MLflow") from exc


def _parse_run(r: dict) -> RunRead:
    info = r.get("info", {})
    data = r.get("data", {})
    return RunRead(
        run_id=info.get("run_id", ""),
        experiment_id=info.get("experiment_id", ""),
        status=info.get("status", "UNKNOWN"),
        start_time=info.get("start_time"),
        end_time=info.get("end_time"),
        params={p["key"]: p["value"] for p in data.get("params", [])},
        metrics={m["key"]: m["value"] for m in data.get("metrics", [])},
        tags={t["key"]: t["value"] for t in data.get("tags", [])},
        artifact_uri=info.get("artifact_uri"),
    )
