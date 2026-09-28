"""Dispatch dell'elaborazione: la decisione Celery-vs-inline vive qui.

Due adapter giustificano il seam: task Celery quando il broker è
raggiungibile (produzione), thread locale quando non lo è (dev/test).
Il resto del codice non decide mai come eseguire il job.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy.orm import sessionmaker

from app.services.extraction.runner import process_document_sync
from app.workers.tasks import process_document

logger = logging.getLogger(__name__)


async def dispatch_processing(
    doc_id: uuid.UUID,
    session_factory: sessionmaker | None = None,
) -> bool:
    """Queue the job on Celery; process inline if the broker is unreachable.

    This function owns the execution decision for document processing
    (the dispatch seam): it enqueues a Celery task when the Redis broker
    is reachable (production), and falls back to running the synchronous
    pipeline in a local thread when it is not (dev/test). The two
    execution adapters justify the seam; no other code decides how the
    job runs.

    Parameters
    ----------
    doc_id : uuid.UUID
        Identifier of the ``PayslipDocument`` to process.
    session_factory : sessionmaker, optional
        SQLAlchemy session factory forwarded to the inline fallback
        (``process_document_sync``) so it can open its own sessions;
        ignored when the Celery path is taken.

    Returns
    -------
    bool
        True if the job was queued on Celery, False if it was processed
        inline in a local thread.

    Raises
    ------
    Exception
        Any error raised by ``process_document_sync`` while running the
        inline fallback; the Celery path swallows the enqueue failure
        and logs a warning instead.

    Dependencies
    -----------
    - app.workers.tasks.process_document : Celery task enqueued when the
      broker is reachable.
    - app.services.extraction.runner.process_document_sync : synchronous
      pipeline used for the inline fallback.

    Examples
    --------
    >>> queued = await dispatch_processing(doc.id)  # doctest: +SKIP
    >>> queued  # doctest: +SKIP
    True
    """
    try:
        process_document.delay(str(doc_id))
        return True
    except Exception:
        logger.warning("broker Redis non disponibile: elaborazione inline")
        await asyncio.to_thread(process_document_sync, str(doc_id), session_factory)
        return False
