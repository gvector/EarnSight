from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """An application user authenticating with username and password.

    Accounts anchor document ownership (``PayslipDocument.user_id``,
    ``AppSetting.user_id``) and authentication: the JWT ``sub`` claim
    carries the username, which ``app.api.deps`` resolves to this row.

    Attributes
    ----------
    id : Integer, primary key, autoincrement
        Unique identifier of the user.
    username : String(64), unique, indexed
        Login name; also the JWT ``sub`` claim used for lookup.
    password_hash : String(256)
        Hashed password (never the plaintext) for verification.

    Dependencies
    -----------
    - app.db.base.Base : declarative base and metadata registry.
    - app.core.security : password hashing and JWT issuing/decoding.
    - app.api.deps._get_current_user : resolves tokens to a ``User``.

    Examples
    --------
    >>> user = User(username="giacomo", password_hash="$2b$12$...")
    >>> user.username
    'giacomo'
    """

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
