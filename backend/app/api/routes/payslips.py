import asyncio
import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.models.payslip import PayslipDocument
from app.schemas.payslip import CorrectionIn, DocumentDetailOut, DocumentOut
from app.services.extraction.result import (
    NUMERIC_FIELDS,
    DocumentStatus,
    ExtractionResult,
    apply_to_document,
)
from app.services.extraction.runner import process_document_sync
from app.services.llm.gateway import get_gateway
from app.workers.tasks import process_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payslips", tags=["payslips"])

FileType = Annotated[UploadFile, File(...)]


async def _get_document(doc_id: uuid.UUID, db: DB, user: CurrentUser) -> PayslipDocument:
    doc = await db.get(PayslipDocument, doc_id)
    if doc is None or (doc.user_id is not None and doc.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento non trovato")
    return doc


async def _enqueue_or_process_inline(doc_id: uuid.UUID, db: DB) -> None:
    try:
        process_document.delay(str(doc_id))
    except Exception:
        logger.warning("broker Redis non disponibile: elaborazione inline")
        await asyncio.to_thread(process_document_sync, str(doc_id))
        await db.refresh(await db.get(PayslipDocument, doc_id))  # pragma: no cover


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_payslip(
    file: FileType,
    user: CurrentUser,
    db: DB,
    doc_type: str = Form("cedolino"),  # noqa: B008
) -> PayslipDocument:
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sono accettati solo file PDF")
    if doc_type not in ("cedolino", "cu"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "doc_type deve essere 'cedolino' o 'cu'")

    doc_id = uuid.uuid4()
    dest = Path(settings.data_dir) / "pdfs" / f"{doc_id}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    dest.write_bytes(content)

    doc = PayslipDocument(
        id=doc_id,
        user_id=user.id,
        doc_type=doc_type,
        filename=filename,
        stored_path=str(dest),
        status=DocumentStatus.PENDING.value,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    await _enqueue_or_process_inline(doc_id, db)
    return doc


@router.get("", response_model=list[DocumentOut])
async def list_payslips(
    user: CurrentUser,
    db: DB,
) -> list[PayslipDocument]:
    result = await db.execute(
        select(PayslipDocument)
        .where((PayslipDocument.user_id == user.id) | (PayslipDocument.user_id.is_(None)))
        .order_by(PayslipDocument.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{doc_id}", response_model=DocumentDetailOut)
async def get_payslip(
    doc_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
) -> PayslipDocument:
    return await _get_document(doc_id, db, user)


@router.post("/{doc_id}/reprocess", response_model=DocumentOut)
async def reprocess_payslip(
    doc_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
) -> PayslipDocument:
    doc = await _get_document(doc_id, db, user)
    doc.status = DocumentStatus.PENDING.value
    await db.commit()
    await _enqueue_or_process_inline(doc.id, db)
    return doc


@router.patch("/{doc_id}/fields", response_model=DocumentDetailOut)
async def correct_fields(
    doc_id: uuid.UUID,
    body: CorrectionIn,
    user: CurrentUser,
    db: DB,
) -> PayslipDocument:
    """Correzione manuale dei campi segnalati dalla validazione."""
    doc = await _get_document(doc_id, db, user)
    result = ExtractionResult.from_jsonb(doc.extraction)
    result.apply_user_correction(body.fields)
    apply_to_document(doc, result)
    doc.error = None
    await db.commit()
    await db.refresh(doc)
    return doc


@router.post("/{doc_id}/llm-resolve", response_model=DocumentDetailOut)
async def llm_resolve_fields(
    doc_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
) -> PayslipDocument:
    """Richiede all'LLM (gateway configurato) i valori dei campi con problemi."""
    doc = await _get_document(doc_id, db, user)
    gateway = get_gateway()
    if gateway is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Nessun provider LLM configurato (LLM_PROVIDER vuoto)",
        )
    result = ExtractionResult.from_jsonb(doc.extraction)

    field_names = result.issue_fields()
    if not field_names:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nessun campo da risolvere con LLM")
    issues = [issue.model_dump() for issue in result.issues if issue.field]

    raw_text = doc.raw_text or ""
    try:
        resolved = await asyncio.to_thread(gateway.resolve_fields, raw_text, field_names, issues)
    except Exception as exc:
        logger.exception("LLM resolve fallito")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Provider LLM non raggiungibile: {exc}"
        ) from exc

    corrections = {}
    for field_name, value in (resolved or {}).items():
        if field_name not in field_names:
            continue
        if field_name in ("period_month", "period_year"):
            value = int(value)
        elif field_name in NUMERIC_FIELDS:
            value = float(value)
        corrections[field_name] = value
    result.apply_llm_corrections(corrections)
    apply_to_document(doc, result)
    await db.commit()
    await db.refresh(doc)
    return doc
