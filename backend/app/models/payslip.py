import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PayslipDocument(Base):
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
    extraction: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

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
