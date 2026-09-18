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
    async with AsyncSessionLocal() as session:
        yield session


async def _get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
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
CurrentUser = Annotated[User, Depends(_get_current_user)]
