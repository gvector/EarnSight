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
    """Accoda il job su Celery; se il broker non è raggiungibile elabora inline.

    Restituisce True se il job è stato accodato, False se elaborato inline.
    """
    try:
        process_document.delay(str(doc_id))
        return True
    except Exception:
        logger.warning("broker Redis non disponibile: elaborazione inline")
        await asyncio.to_thread(process_document_sync, str(doc_id), session_factory)
        return False
