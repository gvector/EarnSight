from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def _sync_url() -> str:
    return settings.database_url.replace("+asyncpg", "+psycopg")


def make_sync_engine():
    return create_engine(_sync_url(), pool_pre_ping=True)


_sync_engine = None
SyncSessionLocal: sessionmaker | None = None


def sync_session_local() -> sessionmaker:
    global _sync_engine, SyncSessionLocal
    if SyncSessionLocal is None:
        _sync_engine = make_sync_engine()
        SyncSessionLocal = sessionmaker(_sync_engine, expire_on_commit=False)
    return SyncSessionLocal
