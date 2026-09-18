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
