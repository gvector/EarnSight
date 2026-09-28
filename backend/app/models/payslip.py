import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# JSONB su Postgres, JSON su sqlite: rende la path di persistenza testabile
# in memoria (session factory iniettata) senza un Postgres reale.
JSONType = JSONB().with_variant(JSON(), "sqlite")


class PayslipDocument(Base):
    """An uploaded payslip or CU document with its extraction result.

    Persistence root of the extraction pipeline: it records the uploaded
    PDF reference, the detection metadata (template, doc type), the raw
    text layer, and the full ``ExtractionResult`` projection (fields,
    entries, issues, validation) split between a JSONB column and
    dedicated canonical-total columns. Recognized entries are
    normalized into the related ``PayslipEntry`` rows. The ``status``
    column drives the document lifecycle consumed by the API and the
    background worker.

    Attributes
    ----------
    id : Uuid, primary key, default uuid4
        Unique identifier of the document.
    user_id : Integer, FK ``user.id``, nullable, indexed
        Owner of the document; ``None`` for unowned documents.
    doc_type : String(16), default ``"cedolino"``
        Document kind: ``"cedolino"`` (monthly payslip) or ``"cu"``
        (annual Certificazione Unica).
    filename : String(512)
        Original filename as uploaded by the user.
    stored_path : String(1024)
        Filesystem path where the uploaded PDF is stored.
    status : String(16), default ``"pending"``, indexed
        Lifecycle state; valid values are defined by
        ``app.services.extraction.result.DocumentStatus`` (pending,
        processing, done, needs_review, needs_ocr, failed).
    template : String(64), nullable
        Detected payslip-software layout signature that guided the
        parser.
    raw_text : Text, nullable
        Raw text extracted from the PDF, kept for corrections and
        re-parsing.
    extraction : JSONB (JSON on sqlite), nullable
        Full ``ExtractionResult`` payload: fields, entries, issues and
        validation outcomes.
    period_month : Integer, nullable
        Canonical period month (1-12) extracted from the document.
    period_year : Integer, nullable
        Canonical period year extracted from the document.
    gross_pay : Numeric(12, 2), nullable
        Canonical gross pay total.
    net_pay : Numeric(12, 2), nullable
        Canonical net pay total.
    total_deductions : Numeric(12, 2), nullable
        Canonical total deductions.
    error : Text, nullable
        Error message set when processing failed.
    created_at : DateTime(timezone=True), server default now()
        Creation timestamp.
    updated_at : DateTime(timezone=True), nullable
        Last update timestamp, refreshed on UPDATE.
    entries : list[PayslipEntry]
        Related normalized entries, eagerly loaded (selectin) and
        deleted with the document (cascade delete-orphan).

    Dependencies
    -----------
    - app.db.base.Base : declarative base and metadata registry.
    - sqlalchemy.dialects.postgresql.JSONB : JSONB storage with a JSON
      variant on sqlite so persistence is testable in memory.
    - app.services.extraction.result.DocumentStatus : valid status
      values referenced by the ``status`` column.

    Examples
    --------
    >>> doc = PayslipDocument(
    ...     filename="cedolino_2026_01.pdf", stored_path="/data/abc.pdf"
    ... )
    >>> doc.filename
    'cedolino_2026_01.pdf'
    """

    __tablename__ = "payslip_document"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True, index=True)
    doc_type: Mapped[str] = mapped_column(String(16), default="cedolino")  # cedolino | cu
    filename: Mapped[str] = mapped_column(String(512))
    stored_path: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # valori validi: app.services.extraction.result.DocumentStatus
    # (pending | processing | done | needs_review | needs_ocr | failed)
    template: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    period_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gross_pay: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    net_pay: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_deductions: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    entries: Mapped[list["PayslipEntry"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )


class PayslipEntry(Base):
    """A single pay entry recognized in a payslip (spettanza/trattenuta).

    Normalized row for one line of the payslip's entry table: each entry
    belongs to exactly one ``PayslipDocument`` (cascade delete) and keeps
    the code, description, amount and whether it is a spettanza
    (earnings) or a trattenuta (deduction).

    Attributes
    ----------
    id : Integer, primary key, autoincrement
        Unique identifier of the entry.
    document_id : Uuid, FK ``payslip_document.id``, indexed
        Owner document; rows are deleted with the document (CASCADE).
    code : String(16), nullable
        Short pay code as printed on the payslip (e.g. ``"NET"``,
        ``"IRET"``).
    description : Text, nullable
        Human-readable label of the entry.
    amount : Numeric(12, 2)
        Signed amount of the entry in euro.
    entry_type : String(16)
        Kind of entry: ``"spettanza"`` (earnings) or ``"trattenuta"``
        (deductions).
    document : PayslipDocument
        Parent document relationship (inverse of
        ``PayslipDocument.entries``).

    Dependencies
    -----------
    - app.db.base.Base : declarative base and metadata registry.
    - app.models.payslip.PayslipDocument : parent document of the
      one-to-many relationship.

    Examples
    --------
    >>> entry = PayslipEntry(
    ...     code="NET", amount=2450.30, entry_type="trattenuta"
    ... )
    >>> entry.code
    'NET'
    """

    __tablename__ = "payslip_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("payslip_document.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    entry_type: Mapped[str] = mapped_column(String(16))  # spettanza | trattenuta

    document: Mapped[PayslipDocument] = relationship(back_populates="entries")
