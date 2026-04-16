"""Celery application configuration."""

from celery import Celery

from infrastructure.config import settings

celery_app = Celery(
    "humanizator",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["async_tasks.rewrite_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    worker_prefetch_multiplier=1,
)
