from collections.abc import AsyncIterator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import AsyncSessionLocal
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_EXCEPTION = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "Credenziali non valide",
    {"WWW-Authenticate": "Bearer"},
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield an async database session scoped to the request.

    FastAPI dependency for routes and downstream dependencies (e.g.
    ``_get_current_user``): opens a session from the ``AsyncSessionLocal``
    factory and yields it for the lifetime of the request; the async
    context manager closes the session (and rolls back an uncommitted
    transaction) when the response is finished.

    Yields
    ------
    AsyncSession
        Session bound to the configured async engine.

    Dependencies
    -----------
    - app.db.session.AsyncSessionLocal : session factory providing the
      yielded sessions.

    Examples
    --------
    >>> import asyncio
    >>> async def route(db: AsyncSession) -> None:
    ...     await db.execute(select(User))
    """

    async with AsyncSessionLocal() as session:
        yield session


async def _get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Resolve the authenticated user from the Bearer token.

    Authentication dependency for protected routes. The chain is:
    ``bearer_scheme`` extracts the ``Authorization: Bearer`` header
    (``auto_error=False`` so a missing header yields ``None`` instead of
    an automatic 403), ``decode_token`` verifies the JWT, and the ``sub``
    claim is matched against ``User.username`` via ``get_db``. Every
    failure mode (missing header, undecodable token, unknown user)
    maps to the same 401 so no information leaks about accounts.

    Parameters
    ----------
    credentials : HTTPAuthorizationCredentials | None
        Bearer credentials parsed by ``bearer_scheme``; ``None`` when
        the Authorization header is missing or malformed.
    db : AsyncSession
        Async session provided by the ``get_db`` dependency.

    Returns
    -------
    User
        The authenticated user row.

    Raises
    ------
    HTTPException
        401 with ``WWW-Authenticate: Bearer`` when the header is
        missing, the token fails to decode (``jwt.PyJWTError``), or
        the ``sub`` claim matches no user.

    Dependencies
    -----------
    - app.api.deps.bearer_scheme : Bearer header extraction.
    - app.api.deps.get_db : database session dependency.
    - app.core.security.decode_token : JWT decoding and verification.
    - app.models.user.User : user lookup by ``sub`` claim.

    Examples
    --------
    Declare a protected route with the ``CurrentUser`` alias:

    >>> @app.get("/me")
    ... async def me(user: CurrentUser) -> str:
    ...     return user.username
    """

    if credentials is None:
        raise _CREDENTIALS_EXCEPTION
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise _CREDENTIALS_EXCEPTION from None
    result = await db.execute(select(User).where(User.username == payload.get("sub")))
    user = result.scalar_one_or_none()
    if user is None:
        raise _CREDENTIALS_EXCEPTION
    return user


DB = Annotated[AsyncSession, Depends(get_db)]
"""Annotated alias for injecting an ``AsyncSession`` via ``get_db``."""


CurrentUser = Annotated[User, Depends(_get_current_user)]
"""Annotated alias for the authenticated ``User`` (401 without valid Bearer)."""
