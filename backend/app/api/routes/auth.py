from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB
from app.core.security import create_access_token, verify_password
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    """Credentials submitted by the user to obtain an access token.

    Parameters
    ----------
    username : str
        Unique username of the account attempting to log in.
    password : str
        Plaintext password; verified against the stored hash only, never
        persisted or logged.
    """

    username: str
    password: str


class LoginOut(BaseModel):
    """JWT payload returned by a successful login.

    Parameters
    ----------
    access_token : str
        Signed JWT to present as a Bearer credential on protected routes.
    token_type : str, optional
        Always ``"bearer"``; explicit for OAuth2 compatibility.
    """

    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=LoginOut)
async def login(body: LoginIn, db: DB) -> LoginOut:
    """Authenticate a user and issue a JWT access token.

    Verifies the submitted credentials against the stored password hash and
    mints a token that all protected routes accept via ``get_current_user``.

    Parameters
    ----------
    body : LoginIn
        Username and plaintext password.
    db : DB
        Async database session.

    Returns
    -------
    LoginOut
        The signed access token and its token type.

    Raises
    ------
    HTTPException
        401 — unknown username or wrong password (deliberately identical
        message to avoid leaking which one failed).

    Dependencies
    -----------
    - db : get_db session for the User lookup.
    - verify_password/create_access_token : core security helpers.

    Examples
    --------
    >>> from app.api.routes.auth import LoginIn
    >>> LoginIn(username="ada", password="s3cret").username
    'ada'
    """
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Username o password non validi")
    return LoginOut(access_token=create_access_token(user.username))
