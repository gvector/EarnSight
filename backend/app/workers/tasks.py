import logging

from app.services.extraction.runner import process_document_sync
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="process_document", bind=True, max_retries=0)
def process_document(self, doc_id: str) -> str:  # noqa: ANN001
    logger.info("task process_document: %s", doc_id)
    process_document_sync(doc_id)
    return doc_id
