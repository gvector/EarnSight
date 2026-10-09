"""Celery application instance for EarnSight background jobs.

Configures a single shared Celery app with Redis as broker, routing all
tasks to the ``earnsight`` queue. There is deliberately no result
backend: a job's outcome is written to the database by the runner, and
nobody reads task results. With a result backend configured, a Redis
outage made every upload hang ~19 s in reconnect retries before the
inline fallback; without it the publish fails in under a second.
Workers can be started with ``celery -A app.workers.celery_app worker``
(on macOS add ``--pool=solo``: the default prefork pool fails there).

Dependencies
------------
- celery.Celery : task queue framework instantiated here.
- app.core.config.settings : application settings providing the Redis
  broker URL.

Examples
--------
>>> from app.workers.celery_app import celery_app
>>> celery_app.main
'earnsight'
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery("earnsight", broker=settings.redis_url)  # nessun result backend: vedi sopra
celery_app.conf.update(
    task_default_queue="earnsight",
    imports=("app.workers.tasks",),
)
