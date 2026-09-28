"""Application-wide logging configuration for the EarnSight backend."""

import logging

from app.core.config import settings


def setup_logging() -> None:
    """Configure the root logger format and verbosity for the process.

    The DEBUG level is reserved for development: it is enabled only while
    SECRET_KEY still carries the known development placeholder, so verbose
    output cannot accidentally ship to a production deployment.

    Dependencies
    -----------
    - app.core.config.settings : inspected to choose the log level.
    - logging.basicConfig : mutates the root logger of the whole process.

    Examples
    --------
    >>> setup_logging()  # doctest: +SKIP
    """
    level = logging.DEBUG if settings.secret_key == "dev-secret-change-me" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
