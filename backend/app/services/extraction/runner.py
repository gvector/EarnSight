"""Runner di elaborazione documento: condiviso tra task Celery e fallback inline."""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.db.session import SyncSessionLocal
from app.models.payslip import PayslipDocument, PayslipEntry
from app.services.extraction.pipeline import run_extraction
from app.services.extraction.result import DocumentStatus, apply_to_document

logger = logging.getLogger(__name__)


def process_document_sync(
    doc_id: str,
    session_factory: sessionmaker | None = None,
) -> None:
    """Elabora un documento: estrazione → validazione → persistenza.

    La session factory è iniettabile: in produzione è SyncSessionLocal,
    nei test una factory su sqlite — la path di persistenza è testabile
    senza un Postgres reale.
    """
    factory = session_factory or SyncSessionLocal
    with factory() as db:
        try:
            doc = db.get(PayslipDocument, uuid.UUID(doc_id))
        except (ValueError, TypeError):
            logger.warning("process_document: doc_id non valido %s", doc_id)
            return
        if doc is None:
            logger.warning("process_document: documento %s non trovato", doc_id)
            return

        doc.status = DocumentStatus.PROCESSING.value
        doc.error = None
        db.commit()

        try:
            result = run_extraction(Path(doc.stored_path))
            apply_to_document(doc, result)

            db.query(PayslipEntry).filter_by(document_id=doc.id).delete()
            for entry in result.entries:
                db.add(
                    PayslipEntry(
                        document_id=doc.id,
                        code=entry.code,
                        description=entry.description,
                        amount=Decimal(str(entry.amount)),
                        entry_type=entry.entry_type,
                    )
                )
            logger.info("process_document: %s → %s", doc_id, doc.status)
        except Exception:
            logger.exception("process_document: errore su %s", doc_id)
            doc.status = DocumentStatus.FAILED.value
            doc.error = "Errore durante l'elaborazione del documento"
        db.commit()
