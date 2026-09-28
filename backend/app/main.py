"""EarnSight API application factory, lifespan bootstrap and health probe."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from app.api.routes.auth import router as auth_router
from app.api.routes.payslips import router as payslips_router
from app.api.routes.settings import router as settings_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.user import User


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """FastAPI lifespan handler: bootstrap logging and the admin account.

    Runs once at startup: it activates logging, hard-fails while SECRET_KEY
    is still a placeholder (the Fernet key that protects stored API keys
    derives from it, so starting with the placeholder would strand every
    encrypted secret), and seeds the bootstrap admin user when missing.
    The parameter is unused because the hook is bound to the module-level
    ``app`` instance directly.

    Parameters
    ----------
    _app : FastAPI
        The application instance passed by FastAPI (intentionally unused).

    Yields
    ------
    None
        Control back to the application for the duration of its run.

    Raises
    ------
    RuntimeError
        If SECRET_KEY is a known placeholder or shorter than the minimum
        length, with instructions for generating a replacement.

    Dependencies
    -----------
    - app.core.logging.setup_logging : configures the root logger.
    - app.core.config.settings : secret key check and admin credentials.
    - app.core.security.hash_password : hashes the seeded admin password.
    - app.db.session.AsyncSessionLocal : startup database session.
    - app.models.user.User : bootstrap account model.
    """
    setup_logging()
    if settings.secret_key_is_placeholder:
        raise RuntimeError(
            "SECRET_KEY non configurata (o placeholder): generane una con "
            '`python -c "import secrets; print(secrets.token_urlsafe(48))"` '
            "e mettila nel .env. Da essa deriva la chiave Fernet delle API key."
        )
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
app.include_router(settings_router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    """Report process liveness for orchestrators and load balancers.

    Returns a static payload on purpose: the probe must stay available
    even when the database or the broker are degraded, so it never
    touches downstream dependencies.

    Returns
    -------
    dict
        ``{"status": "ok"}``.
    """
    return {"status": "ok"}
