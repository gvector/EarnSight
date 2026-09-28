"""Celery tasks for EarnSight document processing.

Each task is a thin Celery wrapper around the synchronous extraction
runner: serialization, retry policy, and queue routing live here, while
all domain logic (parsing, validation, projection on the Document) stays
in the extraction service so it can be reused by the inline fallback.
"""

import logging

from app.services.extraction.runner import process_document_sync
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="process_document", bind=True, max_retries=0)
def process_document(self, doc_id: str) -> str:  # noqa: ANN001
    """Process a single uploaded document through the extraction pipeline.

    Celery entry point for background processing of a payslip (cedolino)
    or CU document: it delegates to ``process_document_sync``, which owns
    parsing, deterministic validation, optional LLM fallback, and
    projection of the result onto the ``PayslipDocument`` row. Retries are
    deliberately disabled (``max_retries=0``) because a failed extraction
    is recorded on the document as a terminal ``failed`` status rather
    than retried.

    Parameters
    ----------
    self : Task
        Bound Celery task instance (``bind=True``), unused by the body.
    doc_id : str
        Identifier of the ``PayslipDocument`` row to process, as produced
        by the upload API (stringified UUID).

    Returns
    -------
    str
        The same ``doc_id`` that was passed in, so the caller or the
        result backend can correlate the task with its document.

    Raises
    ------
    Exception
        Any error raised by ``process_document_sync``; the document is
        marked ``failed`` by the runner before the exception propagates.

    Dependencies
    -----------
    - app.services.extraction.runner.process_document_sync : synchronous
      extraction pipeline invoked by the task.
    - app.workers.celery_app.celery_app : Celery application that
      registers the task on the ``earnsight`` queue.

    Examples
    --------
    >>> result = process_document.delay("3fa85f64-5717-4562-b3fc-2c963f66afa6")
    >>> result.status
    'PENDING'
    """
    logger.info("task process_document: %s", doc_id)
    process_document_sync(doc_id)
    return doc_id
