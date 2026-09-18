from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

import app.models.payslip  # noqa: F401
import app.models.user  # noqa: F401  (registra i modelli su Base.metadata)
from app.api.routes.auth import router as auth_router
from app.api.routes.payslips import router as payslips_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models.user import User


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == settings.auth_username))
        if result.scalar_one_or_none() is None:
            db.add(
                User(
                    username=settings.auth_username,
                    password_hash=hash_password(settings.auth_password),
                )
            )
            await db.commit()
    yield


app = FastAPI(title="EarnSight API", version="0.1.0", lifespan=lifespan)

app.include_router(auth_router, prefix="/api")
app.include_router(payslips_router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
