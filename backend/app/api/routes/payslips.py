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
    DocumentStatus,
    ExtractionResult,
    apply_to_document,
    coerce_correction_value,
)
from app.services.llm.gateway import get_gateway_for_user
from app.workers.dispatch import dispatch_processing

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payslips", tags=["payslips"])

FileType = Annotated[UploadFile, File(...)]


async def _get_document(doc_id: uuid.UUID, db: DB, user: CurrentUser) -> PayslipDocument:
    doc = await db.get(PayslipDocument, doc_id)
    if doc is None or doc.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento non trovato")
    return doc


async def _dispatch_and_refresh(doc_id: uuid.UUID, db: DB) -> PayslipDocument:
    """Accoda (o elabora inline) e riporta lo stato aggiornato del documento."""
    await dispatch_processing(doc_id)
    doc = await db.get(PayslipDocument, doc_id)
    if doc is not None:
        await db.refresh(doc)
    return doc


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
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File troppo grande: massimo {settings.max_upload_mb} MB",
        )
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

    return await _dispatch_and_refresh(doc_id, db)


@router.get("", response_model=list[DocumentOut])
async def list_payslips(
    user: CurrentUser,
    db: DB,
) -> list[PayslipDocument]:
    result = await db.execute(
        select(PayslipDocument)
        .where(PayslipDocument.user_id == user.id)
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
    await db.refresh(doc)
    return await _dispatch_and_refresh(doc_id, db)


@router.patch("/{doc_id}/fields", response_model=DocumentDetailOut)
async def correct_fields(
    doc_id: uuid.UUID,
    body: CorrectionIn,
    user: CurrentUser,
    db: DB,
) -> PayslipDocument:
    """Correzione manuale dei campi segnalati dalla validazione."""
    doc = await _get_document(doc_id, db, user)
    try:
        corrections = {
            name: coerce_correction_value(name, value) for name, value in body.fields.items()
        }
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Correzione non valida: {exc}"
        ) from None
    result = ExtractionResult.from_document(doc)
    result.apply_user_correction(corrections)
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
    gateway = await get_gateway_for_user(db, user)
    if gateway is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Nessun provider LLM configurato (LLM_PROVIDER vuoto)",
        )
    result = ExtractionResult.from_document(doc)

    field_names = result.issue_fields()
    if not field_names:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nessun campo da risolvere con LLM")
    issues = [issue.model_dump() for issue in result.issues if issue.field]

    raw_text = result.raw_text
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
        try:
            corrections[field_name] = coerce_correction_value(field_name, value)
        except ValueError:
            # risposta LLM malformata su questo campo: lo si lascia al problema
            # originale, l'utente può ancora correggere a mano. Mai un 500.
            logger.warning("LLM: valore non valido per %s: %r — saltato", field_name, value)
    if not corrections:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Il provider LLM non ha restituito valori utilizzabili",
        )
    result.apply_llm_corrections(corrections)
    apply_to_document(doc, result)
    await db.commit()
    await db.refresh(doc)
    return doc
