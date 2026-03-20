"""Celery application — background task queue backed by Redis."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "forge",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.tasks.execution",
        "app.workers.tasks.datasets",
        "app.workers.tasks.notifications",
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
        "app.workers.tasks.execution.*": {"queue": "execution"},
        "app.workers.tasks.datasets.*": {"queue": "datasets"},
        "app.workers.tasks.notifications.*": {"queue": "default"},
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
