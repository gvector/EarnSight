"""Engine and session factories for async (API) and sync (worker) access.

``engine``/``AsyncSessionLocal`` serve the FastAPI request path, while
``sync_engine``/``SyncSessionLocal`` back Celery workers and Alembic through
``settings.sync_database_url``. Both engines enable ``pool_pre_ping`` so
stale connections are recycled transparently, and both session factories set
``expire_on_commit=False`` so ORM objects remain readable after a commit.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

sync_engine = create_engine(settings.sync_database_url, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)
