"""Celery task module imported by the worker loader."""

from app.workers.celery_app import celery_app

__all__ = ["celery_app"]

