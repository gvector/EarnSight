"""Document processing runner, shared by the Celery task and the inline fallback.

``process_document_sync`` is the single execution body behind
``dispatch_processing``: the worker (Celery or local thread) always ends up
here, so the processing path — extraction, validation, projection and
persistence — has one owner and one testable implementation.
"""

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
    """Process one document end-to-end: extraction → validation → persistence.

    Loads the ``PayslipDocument``, marks it ``processing`` and clears any
    previous error, then runs the extraction pipeline on the stored PDF.
    The resulting ``ExtractionResult`` is projected onto the document via
    ``apply_to_document`` — the single projection owner for the JSONB
    payload, the dedicated columns (template, raw_text, numeric totals,
    period) and the derived status — and the ``PayslipEntry`` rows are
    replaced with the freshly parsed entries. Any failure is caught and
    logged: the document is marked ``failed`` with a generic error message,
    so the runner never re-raises to the caller (a Celery retry loop would
    just replay the same deterministic failure).

    Parameters
    ----------
    doc_id : str
        UUID string of the ``PayslipDocument`` to process. Invalid or
        unknown ids are logged and skipped.
    session_factory : sessionmaker, optional
        Injected sync session factory. Defaults to ``SyncSessionLocal`` in
        production; tests inject a factory backed by sqlite so the
        persistence path is testable without a real Postgres.

    Returns
    -------
    None

    Dependencies
    -----------
    - pipeline.run_extraction : extraction pipeline (text, template,
      parser, validation).
    - result.apply_to_document : projection seam of the ExtractionResult
      onto the Document (JSONB, dedicated columns, status).
    - db.session.SyncSessionLocal : default sync session factory derived
      from ``DATABASE_URL``.
    - models.payslip : ``PayslipDocument`` and ``PayslipEntry`` ORM models.

    Examples
    --------
    >>> process_document_sync("00000000-0000-0000-0000-000000000000")
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
            result = run_extraction(Path(doc.stored_path), doc_type=doc.doc_type or "cedolino")
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
