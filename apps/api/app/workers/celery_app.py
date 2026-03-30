"""Celery application — background task queue backed by Redis."""

import asyncio
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from celery import Celery
from croniter import croniter

from app.config import settings
from app.core.workflow_engine import OrionEngine
from app.models.workflow import WorkflowRunTriggeredBy

celery_app = Celery(
    "forge",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.tasks",
    ],
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Result expiry
    result_expires=3600,  # 1 hour
    # Task routing — map task names to specific queues
    task_routes={
        "app.workers.tasks.*": {"queue": "default"},
        "app.workers.publish.*": {"queue": "default"},
        "orion.*": {"queue": "orion"},
    },
    beat_schedule={
        "orion-trigger-scheduled-workflows": {
            "task": "orion.trigger_scheduled_workflows",
            "schedule": 60.0,
        },
        "orion-cleanup-old-runs": {
            "task": "orion.cleanup_old_runs",
            "schedule": 86400.0,
        },
    },
    # Worker concurrency defaults
    worker_prefetch_multiplier=1,  # one task at a time per worker process (fair scheduling)
    task_acks_late=True,  # acknowledge only after task completes (safe re-delivery on crash)
    # Retry defaults
    task_max_retries=3,
    task_default_retry_delay=30,  # seconds
)


@celery_app.task(bind=True, name="app.workers.celery_app.health_check")
def health_check(self):
    """Trivial task used to verify the Celery worker is reachable."""
    return {"status": "ok"}


@celery_app.task(bind=True, max_retries=3, name="orion.execute_node")
def execute_workflow_node_task(self, workflow_run_id: str, node_id: str, run_context: dict) -> dict:
    return asyncio.run(OrionEngine().execute_node(workflow_run_id, node_id, run_context))


@celery_app.task(name="orion.trigger_scheduled_workflows")
def trigger_scheduled_workflows() -> dict:
    async def _run() -> dict:
        triggered = 0
        now_utc = datetime.now(UTC)
        engine = OrionEngine()
        for workflow in await engine.scheduled_candidates():
            cron = (workflow.schedule_cron or "").strip()
            if not cron:
                continue
            tz_name = workflow.schedule_timezone or "UTC"
            try:
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = ZoneInfo("UTC")
            now_tz = now_utc.astimezone(tz)
            prev = croniter(cron, now_tz).get_prev(datetime)
            if (now_tz - prev).total_seconds() <= 60:
                await engine.start_run(
                    workflow_id=workflow.id,
                    triggered_by=WorkflowRunTriggeredBy.schedule.value,
                    triggered_by_user_id=None,
                    run_metadata={"workspace_id": workflow.workspace_id, "scheduled_at": now_utc.isoformat()},
                    trigger_payload={"scheduled_at": now_utc.isoformat()},
                )
                triggered += 1
        return {"triggered": triggered}

    return asyncio.run(_run())


@celery_app.task(name="orion.cleanup_old_runs")
def cleanup_old_runs() -> dict:
    async def _run() -> dict:
        deleted = await OrionEngine().cleanup_old_runs(keep_days=90, keep_last_per_workflow=5)
        return {"deleted": deleted}

    return asyncio.run(_run())
