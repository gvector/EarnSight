"""Celery application instance for EarnSight background jobs.

Configures a single shared Celery app backed by Redis (same URL for
broker and result backend, taken from application settings), routing
all tasks to the ``earnsight`` queue. Workers can be started with
``celery -A app.workers.celery_app worker``.

Dependencies
------------
- celery.Celery : task queue framework instantiated here.
- app.core.config.settings : application settings providing the Redis
  URL used for both broker and result backend.

Examples
--------
>>> from app.workers.celery_app import celery_app
>>> celery_app.main
'earnsight'
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "earnsight",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_default_queue="earnsight",
    imports=("app.workers.tasks",),
    task_track_started=True,
)
