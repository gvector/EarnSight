import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class FieldValueOut(BaseModel):
    """Serialization of a FieldProvenance shape for one canonical field.

    Mirrors the ``FieldProvenance`` contract of ``ExtractionResult``:
    the field value plus how it was obtained and whether it was later
    corrected by the user or the LLM.

    Attributes
    ----------
    value : Any
        Extracted value of the field (number, string or null).
    confidence : float
        Confidence score in [0, 1] from the extraction source.
    source : str | None
        Provenance of the value (e.g. parser, ocr, llm, user).
    corrected : bool
        True when the value was corrected after initial extraction.

    Dependencies
    -----------
    - app.services.extraction.result.FieldProvenance : shape mirrored
      by this schema.
    - app.api routes : served inside ``DocumentDetailOut.extraction``.

    Examples
    --------
    >>> out = FieldValueOut(value=2450.30, confidence=0.99, source="parser")
    >>> out.corrected
    False
    """

    value: Any
    confidence: float
    source: str | None = None
    corrected: bool = False


class IssueOut(BaseModel):
    """Serialization of one validation issue with its suggested action.

    Mirrors an ``Issue`` from the ``ExtractionResult`` contract: which
    deterministic check failed, the human-readable explanation, the
    field involved (when applicable) and the action needed to resolve
    it.

    Attributes
    ----------
    field : str | None
        Canonical field the issue refers to, if any.
    check : str
        Identifier of the failed validation check.
    message : str
        Human-readable description of the problem.
    action : str
        Suggested remediation: ``"user"`` (manual correction) or
        ``"llm"`` (targeted LLM request).

    Dependencies
    -----------
    - app.services.extraction.result : Issue contract mirrored here.
    - app.services validation : producer of the checks.

    Examples
    --------
    >>> issue = IssueOut(check="net_gross", message="mismatch", action="user")
    >>> issue.action
    'user'
    """

    field: str | None = None
    check: str
    message: str
    action: str  # user | llm


class EntryOut(BaseModel):
    """Serialization of one pay entry (spettanza or trattenuta).

    API projection of a ``PayslipEntry`` ORM row, used inside
    ``DocumentDetailOut.entries``.

    Attributes
    ----------
    code : str | None
        Short pay code as printed on the payslip.
    description : str | None
        Human-readable label of the entry.
    amount : float
        Amount of the entry in euro.
    entry_type : str
        Kind of entry: ``"spettanza"`` or ``"trattenuta"``.

    Dependencies
    -----------
    - app.models.payslip.PayslipEntry : ORM row projected here.
    - app.schemas.payslip.DocumentDetailOut : parent payload.

    Examples
    --------
    >>> entry = EntryOut(code="NET", amount=2450.30, entry_type="trattenuta")
    >>> entry.entry_type
    'trattenuta'
    """

    code: str | None = None
    description: str | None = None
    amount: float
    entry_type: str


class ValidationOut(BaseModel):
    """Summary of the deterministic validation checks for a document.

    Aggregates the outcome of the arithmetic validation
    (netto+trattenute=lordo, entries vs totals, valid period) into a
    single pass flag with error and warning counts.

    Attributes
    ----------
    passed : bool
        True when no validation error was raised.
    error_count : int
        Number of blocking validation issues.
    warning_count : int
        Number of non-blocking validation warnings.

    Dependencies
    -----------
    - app.services validation : producer of the checks aggregated here.

    Examples
    --------
    >>> v = ValidationOut(passed=True)
    >>> v.error_count
    0
    """

    passed: bool
    error_count: int = 0
    warning_count: int = 0


class DocumentOut(BaseModel):
    """List-view serialization of a ``PayslipDocument``.

    Core metadata of a document for listing endpoints: identity, type,
    lifecycle status and the canonical totals, without the heavy
    payloads (raw text, extraction JSONB, entries).

    Attributes
    ----------
    id : uuid.UUID
        Identifier of the document.
    doc_type : str
        Document kind: ``"cedolino"`` or ``"cu"``.
    filename : str
        Original uploaded filename.
    status : str
        Lifecycle state (pending, processing, done, needs_review,
        needs_ocr, failed).
    template : str | None
        Detected payslip-software template, if any.
    period_month : int | None
        Canonical period month (1-12).
    period_year : int | None
        Canonical period year.
    gross_pay : Decimal | None
        Canonical gross pay total.
    net_pay : Decimal | None
        Canonical net pay total.
    total_deductions : Decimal | None
        Canonical total deductions.
    error : str | None
        Error message when processing failed.
    created_at : datetime
        Creation timestamp.

    Dependencies
    -----------
    - app.models.payslip.PayslipDocument : ORM source (built with
      ``from_attributes`` so fields are read straight from the model).

    Examples
    --------
    >>> out = DocumentOut(
    ...     id=uuid.uuid4(), doc_type="cedolino", filename="p.pdf",
    ...     status="done", template=None, period_month=1, period_year=2026,
    ...     gross_pay=None, net_pay=None, total_deductions=None,
    ...     error=None, created_at=datetime(2026, 1, 31),
    ... )
    >>> out.status
    'done'
    """

    id: uuid.UUID
    doc_type: str
    filename: str
    status: str
    template: str | None
    period_month: int | None
    period_year: int | None
    gross_pay: Decimal | None
    net_pay: Decimal | None
    total_deductions: Decimal | None
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetailOut(DocumentOut):
    """Detail-view serialization of a ``PayslipDocument``.

    Extends ``DocumentOut`` with the heavy payloads needed by the
    detail and correction UIs: the raw PDF text, the full extraction
    JSONB (fields, issues, validation) and the normalized entries.

    Attributes
    ----------
    raw_text : str | None
        Raw text layer extracted from the PDF.
    extraction : dict | None
        Full ``ExtractionResult`` payload (fields, entries, issues,
        validation) as stored on the document.
    entries : list[EntryOut]
        Normalized pay entries of the document.

    Dependencies
    -----------
    - app.schemas.payslip.DocumentOut : base metadata fields.
    - app.services.extraction.result.from_document : source of the
      extraction payload rebuilt from the ORM row.
    - app.schemas.payslip.EntryOut : entry projection included here.

    Examples
    --------
    >>> out = DocumentDetailOut(
    ...     id=uuid.uuid4(), doc_type="cedolino", filename="p.pdf",
    ...     status="done", template=None, period_month=1, period_year=2026,
    ...     gross_pay=None, net_pay=None, total_deductions=None,
    ...     error=None, created_at=datetime(2026, 1, 31),
    ...     raw_text=None, extraction=None, entries=[],
    ... )
    >>> out.entries
    []
    """

    raw_text: str | None
    extraction: dict | None
    entries: list[EntryOut] = []


class CorrectionIn(BaseModel):
    """User-supplied corrections for the canonical fields of a document.

    Request body of the correction endpoint: a mapping of canonical
    field names (e.g. ``net_pay``, ``period_month``) to replacement
    values. Values are later coerced by
    ``coerce_correction_value`` (integers for INT_FIELDS, finite
    numbers for NUMERIC_FIELDS); invalid input maps to HTTP 422.

    Attributes
    ----------
    fields : dict[str, float | str | int | None]
        Corrections keyed by canonical field name.

    Dependencies
    -----------
    - app.services.extraction corrections : typed coercion of the
      submitted values and projection onto the document.

    Examples
    --------
    >>> corr = CorrectionIn(fields={"net_pay": 2450.30})
    >>> corr.fields["net_pay"]
    2450.3
    """

    fields: dict[str, float | str | int | None]
