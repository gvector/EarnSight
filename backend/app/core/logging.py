"""Application-wide logging configuration for the EarnSight backend."""

import logging


def setup_logging() -> None:
    """Configure the root logger format and verbosity (INFO) for the process.

    Dependencies
    -----------
    - logging.basicConfig : mutates the root logger of the whole process.

    Examples
    --------
    >>> setup_logging()  # doctest: +SKIP
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
