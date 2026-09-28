"""Declarative ORM base for the EarnSight data model."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base class for all EarnSight ORM models.

    Every model (User, PayslipDocument, ...) inherits from this class,
    which gives them a shared ``MetaData`` registry and the typed query
    interface; Alembic autogenerate diffs migrations against this same
    metadata.

    Dependencies
    -----------
    - sqlalchemy.orm.DeclarativeBase : typed declarative machinery.

    Examples
    --------
    >>> class User(Base):  # doctest: +SKIP
    ...     __tablename__ = "users"
    """
