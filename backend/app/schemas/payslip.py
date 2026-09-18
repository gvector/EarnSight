import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class FieldValueOut(BaseModel):
    value: Any
    confidence: float
    source: str | None = None
    corrected: bool = False


class IssueOut(BaseModel):
    field: str | None = None
    check: str
    message: str
    action: str  # user | llm


class EntryOut(BaseModel):
    code: str | None = None
    description: str | None = None
    amount: float
    entry_type: str


class ValidationOut(BaseModel):
    passed: bool
    error_count: int = 0
    warning_count: int = 0


class DocumentOut(BaseModel):
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
    raw_text: str | None
    extraction: dict | None


class CorrectionIn(BaseModel):
    fields: dict[str, float | str | int | None]
