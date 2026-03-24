"""MLflow-backed experiment tracking and model registry for FORGE."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

import mlflow
import mlflow.pyfunc
import mlflow.sklearn
import mlflow.xgboost
from mlflow import MlflowClient
from mlflow.entities import ViewType

from app.config import settings
from app.core.exceptions import ServiceUnavailableException


class ExperimentTracker:
    """
    Wraps MLflow to provide FORGE-native experiment tracking.
    Each workspace gets its own MLflow experiment namespace.
    """

    def __init__(self) -> None:
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        self._client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)

    @staticmethod
    def _experiment_name(workspace_id: UUID | str, name: str) -> str:
        return f"forge_{workspace_id}_{name}"

    @staticmethod
    def _model_name(workspace_id: UUID | str, model_name: str) -> str:
        return f"forge_{workspace_id}_{model_name}"

    async def get_or_create_experiment(self, workspace_id: UUID | str, name: str) -> str:
        experiment_name = self._experiment_name(workspace_id, name)
        experiment = self._client.get_experiment_by_name(experiment_name)
        if experiment is not None:
            return experiment.experiment_id
        return self._client.create_experiment(experiment_name)

    async def start_run(
        self,
        workspace_id: UUID | str,
        experiment_name: str,
        run_name: str,
        tags: dict[str, str] | None = None,
    ) -> str:
        experiment_id = await self.get_or_create_experiment(workspace_id, experiment_name)
        merged_tags = {
            "forge.workspace_id": str(workspace_id),
            "forge.experiment_name": experiment_name,
            "mlflow.runName": run_name,
            **(tags or {}),
        }
        run = self._client.create_run(experiment_id=experiment_id, tags=merged_tags)
        return run.info.run_id

    async def log_params(self, run_id: str, params: Mapping[str, Any]) -> None:
        for key, value in params.items():
            self._client.log_param(run_id=run_id, key=str(key), value=str(value))

    async def log_metrics(
        self,
        run_id: str,
        metrics: Mapping[str, float | int],
        step: int | None = None,
    ) -> None:
        for key, value in metrics.items():
            if step is None:
                self._client.log_metric(run_id=run_id, key=str(key), value=float(value))
            else:
                self._client.log_metric(run_id=run_id, key=str(key), value=float(value), step=step)

    async def log_artifact(
        self,
        run_id: str,
        file_path: str,
        artifact_path: str | None = None,
    ) -> None:
        self._client.log_artifact(run_id=run_id, local_path=file_path, artifact_path=artifact_path)

    async def log_model(
        self,
        run_id: str,
        model: Any,
        model_name: str,
        signature: Any = None,
        input_example: Any = None,
    ) -> str:
        run = self._client.get_run(run_id)
        workspace_id = run.data.tags.get("forge.workspace_id")
        if not workspace_id:
            raise ServiceUnavailableException("Experiment tracking metadata")

        registered_model_name = self._model_name(workspace_id, model_name)
        artifact_path = model_name
        with mlflow.start_run(run_id=run_id):
            model_module = getattr(model, "__module__", "")
            if "xgboost" in model_module:
                mlflow.xgboost.log_model(
                    xgb_model=model,
                    artifact_path=artifact_path,
                    registered_model_name=registered_model_name,
                    signature=signature,
                    input_example=input_example,
                )
            elif "sklearn" in model_module:
                mlflow.sklearn.log_model(
                    sk_model=model,
                    artifact_path=artifact_path,
                    registered_model_name=registered_model_name,
                    signature=signature,
                    input_example=input_example,
                )
            else:
                mlflow.pyfunc.log_model(
                    artifact_path=artifact_path,
                    python_model=model,
                    registered_model_name=registered_model_name,
                    signature=signature,
                    input_example=input_example,
                )
        return f"models:/{registered_model_name}/latest"

    async def end_run(self, run_id: str, status: str = "FINISHED") -> None:
        self._client.set_terminated(run_id=run_id, status=status.upper())

    async def list_experiments(self, workspace_id: UUID | str) -> list[dict[str, Any]]:
        prefix = f"forge_{workspace_id}_"
        experiments = self._client.search_experiments(
            view_type=ViewType.ACTIVE_ONLY,
            max_results=500,
        )
        return [
            {
                "experiment_id": e.experiment_id,
                "name": e.name,
                "artifact_location": e.artifact_location,
                "lifecycle_stage": e.lifecycle_stage,
            }
            for e in experiments
            if e.name.startswith(prefix)
        ]

    async def list_models(self, workspace_id: UUID | str) -> list[dict[str, Any]]:
        prefix = f"forge_{workspace_id}_"
        models = self._client.search_registered_models(max_results=500)
        results: list[dict[str, Any]] = []
        for model in models:
            if not model.name.startswith(prefix):
                continue
            latest_versions = [
                {
                    "version": mv.version,
                    "stage": mv.current_stage,
                    "run_id": mv.run_id,
                    "source": mv.source,
                }
                for mv in model.latest_versions
            ]
            results.append({"name": model.name, "latest_versions": latest_versions})
        return results

    async def list_runs(self, experiment_id: str) -> list[dict[str, Any]]:
        runs = self._client.search_runs(
            experiment_ids=[experiment_id],
            order_by=["start_time DESC"],
            max_results=500,
        )
        results: list[dict[str, Any]] = []
        for run in runs:
            info = run.info
            start_time = info.start_time
            end_time = info.end_time
            duration = ((end_time - start_time) / 1000.0) if start_time and end_time else None
            results.append(
                {
                    "run_id": info.run_id,
                    "run_name": run.data.tags.get("mlflow.runName", ""),
                    "status": info.status,
                    "params": dict(run.data.params),
                    "metrics": dict(run.data.metrics),
                    "start_time": start_time,
                    "duration": duration,
                }
            )
        return results

    async def compare_runs(self, run_ids: list[str]) -> dict[str, Any]:
        runs = [self._client.get_run(run_id) for run_id in run_ids]
        all_param_keys = sorted({k for run in runs for k in run.data.params})
        all_metric_keys = sorted({k for run in runs for k in run.data.metrics})
        return {
            "run_ids": run_ids,
            "params": {
                key: {run.info.run_id: run.data.params.get(key) for run in runs}
                for key in all_param_keys
            },
            "metrics": {
                key: {run.info.run_id: run.data.metrics.get(key) for run in runs}
                for key in all_metric_keys
            },
        }

    async def get_best_run(
        self,
        experiment_id: str,
        metric: str,
        mode: str = "min",
    ) -> dict[str, Any]:
        runs = await self.list_runs(experiment_id)
        metric_runs = [r for r in runs if metric in r["metrics"]]
        if not metric_runs:
            raise ServiceUnavailableException(f"Metric '{metric}'")
        reverse = mode.lower() == "max"
        best = sorted(metric_runs, key=lambda r: r["metrics"][metric], reverse=reverse)[0]
        return best

    async def deploy_model(
        self,
        workspace_id: UUID | str,
        run_id: str,
        model_name: str,
    ) -> str:
        registered_model_name = self._model_name(workspace_id, model_name)
        model_uri = f"runs:/{run_id}/{model_name}"
        model_version = mlflow.register_model(model_uri=model_uri, name=registered_model_name)
        self._client.transition_model_version_stage(
            name=registered_model_name,
            version=model_version.version,
            stage="Production",
            archive_existing_versions=True,
        )
        return f"models:/{registered_model_name}/Production"

    async def get_model_uri(self, workspace_id: UUID | str, model_name: str) -> str:
        registered_model_name = self._model_name(workspace_id, model_name)
        versions = self._client.get_latest_versions(registered_model_name, stages=["Production"])
        if not versions:
            raise ServiceUnavailableException(f"Production model '{registered_model_name}'")
        version = versions[0].version
        return f"models:/{registered_model_name}/{version}"

