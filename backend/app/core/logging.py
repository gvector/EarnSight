import logging

from app.core.config import settings


def setup_logging() -> None:
    level = logging.DEBUG if settings.secret_key == "dev-secret-change-me" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
