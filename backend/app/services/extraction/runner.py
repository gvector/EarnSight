"""Runner di elaborazione documento: condiviso tra task Celery e fallback inline."""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from pathlib import Path

from app.db.session import sync_session_local
from app.models.payslip import PayslipDocument, PayslipEntry
from app.services.extraction.pipeline import run_extraction

logger = logging.getLogger(__name__)

NUMERIC_FIELDS = ("gross_pay", "net_pay", "total_deductions")


def process_document_sync(doc_id: str) -> None:
    """Elabora un documento: estrazione → validazione → persistenza."""
    SyncSessionLocal = sync_session_local()
    with SyncSessionLocal() as db:
        try:
            doc = db.get(PayslipDocument, uuid.UUID(doc_id))
        except (ValueError, TypeError):
            logger.warning("process_document: doc_id non valido %s", doc_id)
            return
        if doc is None:
            logger.warning("process_document: documento %s non trovato", doc_id)
            return

        doc.status = "processing"
        doc.error = None
        db.commit()

        try:
            result = run_extraction(Path(doc.stored_path))
            doc.template = result["template"]
            doc.raw_text = result.get("raw_text") or None
            doc.extraction = {
                key: result[key] for key in ("fields", "entries", "issues", "validation")
            }

            fields = result["fields"]
            for field_name in NUMERIC_FIELDS:
                value = (fields.get(field_name) or {}).get("value")
                setattr(
                    doc,
                    field_name,
                    Decimal(str(value)) if isinstance(value, int | float) else None,
                )
            doc.period_month = (fields.get("period_month") or {}).get("value")
            doc.period_year = (fields.get("period_year") or {}).get("value")
            doc.status = result["status"]

            db.query(PayslipEntry).filter_by(document_id=doc.id).delete()
            for entry in result["entries"]:
                db.add(
                    PayslipEntry(
                        document_id=doc.id,
                        code=str(entry.get("code") or "") or None,
                        description=entry.get("description"),
                        amount=Decimal(str(entry["amount"])),
                        entry_type=entry["entry_type"],
                    )
                )
            logger.info("process_document: %s → %s", doc_id, doc.status)
        except Exception:
            logger.exception("process_document: errore su %s", doc_id)
            doc.status = "failed"
            doc.error = "Errore durante l'elaborazione del documento"
        db.commit()
