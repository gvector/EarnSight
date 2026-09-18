"""Contratto di estrazione: il modulo unico che possiede la shape del risultato.

ExtractionResult e FieldProvenance sono l'unica interface parlata da pipeline,
worker e API: la shape JSONB esiste solo come proiezione (to_jsonb) e la
ricostruzione come from_jsonb. Lo status del documento è derivato qui
(DocumentStatus + status_from_validation) e mai composto con literal sparsi.
"""

from __future__ import annotations

import enum
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.payslip import PayslipDocument
from app.services.extraction.validation import run_validation

# Campi specchiati in colonne dedicate del documento (per analytics).
NUMERIC_FIELDS = ("gross_pay", "net_pay", "total_deductions")


class DocumentStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    NEEDS_REVIEW = "needs_review"
    NEEDS_OCR = "needs_ocr"
    FAILED = "failed"


def status_from_validation(passed: bool) -> DocumentStatus:
    return DocumentStatus.DONE if passed else DocumentStatus.NEEDS_REVIEW


class FieldProvenance(BaseModel):
    """Valore di un campo con provenienza e confidenza."""

    value: Any
    confidence: float = 0.9
    source: str | None = None
    corrected: bool = False

    @classmethod
    def parsed(cls, value: Any, source: str | None, confidence: float = 0.9) -> FieldProvenance:
        return cls(value=value, confidence=confidence, source=source)

    def apply_user_correction(self, value: Any) -> None:
        self.value = value
        self.confidence = 1.0
        self.corrected = True

    def apply_llm_correction(self, value: Any) -> None:
        self.value = value
        self.confidence = 0.7
        self.corrected = False
        self.source = "llm"

    def penalize(self) -> None:
        if not self.corrected:
            self.confidence = min(self.confidence, 0.3)


class Issue(BaseModel):
    field: str | None = None
    check: str
    message: str
    action: str  # "user" (correzione manuale) | "llm" (richiesta mirata)


class ValidationSummary(BaseModel):
    passed: bool = False
    error_count: int = 0
    warning_count: int = 0


class Entry(BaseModel):
    code: str | None = None
    description: str | None = None
    amount: float
    entry_type: str  # "spettanza" | "trattenuta"


class ExtractionResult(BaseModel):
    template: str | None = None
    fields: dict[str, FieldProvenance] = Field(default_factory=dict)
    entries: list[Entry] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    validation: ValidationSummary = Field(default_factory=ValidationSummary)
    status: DocumentStatus = DocumentStatus.PENDING
    raw_text: str = ""

    @classmethod
    def from_jsonb(cls, data: dict | None) -> ExtractionResult:
        data = data or {}
        return cls(
            template=data.get("template"),
            fields={k: FieldProvenance(**v) for k, v in (data.get("fields") or {}).items()},
            entries=[Entry(**e) for e in (data.get("entries") or [])],
            issues=[Issue(**i) for i in (data.get("issues") or [])],
            validation=ValidationSummary(**(data.get("validation") or {})),
        )

    def revalidate(self) -> None:
        """Rivalida i campi correnti, aggiorna issues/validation/status."""
        report = run_validation(self.fields, self.entries)
        issues = report["errors"] + report["warnings"]
        for issue in issues:
            field_name = issue.get("field")
            if field_name and field_name in self.fields:
                self.fields[field_name].penalize()
        self.issues = [Issue(**issue) for issue in issues]
        self.validation = ValidationSummary(
            passed=report["passed"],
            error_count=report["error_count"],
            warning_count=report["warning_count"],
        )
        self.status = status_from_validation(report["passed"])

    def apply_user_correction(self, corrections: dict[str, Any]) -> None:
        self._apply(corrections, FieldProvenance.apply_user_correction)

    def apply_llm_corrections(self, corrections: dict[str, Any]) -> None:
        self._apply(corrections, FieldProvenance.apply_llm_correction)

    def _apply(self, corrections: dict[str, Any], apply_method: Any) -> None:
        for name, value in corrections.items():
            field_value = self.fields.get(name) or FieldProvenance(value=value)
            apply_method(field_value, value)
            self.fields[name] = field_value
        self.revalidate()

    def issue_fields(self) -> list[str]:
        return sorted({issue.field for issue in self.issues if issue.field})

    def column_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name in NUMERIC_FIELDS:
            field_value = self.fields.get(name)
            value = field_value.value if field_value else None
            values[name] = Decimal(str(value)) if isinstance(value, int | float) else None
        values["period_month"] = self._field_value("period_month")
        values["period_year"] = self._field_value("period_year")
        return values

    def _field_value(self, name: str) -> Any:
        field_value = self.fields.get(name)
        return field_value.value if field_value else None

    def to_jsonb(self) -> dict[str, Any]:
        """Proiezione JSONB persistita: shape invariata rispetto alla Fase 1."""
        return self.model_dump(
            include={"fields", "entries", "issues", "validation"},
        )


def apply_to_document(doc: PayslipDocument, result: ExtractionResult) -> None:
    """Proietta il risultato sul documento ORM: JSONB, colonne, status.

    L'unico posto dove esistono la sync delle colonne e la derivazione dello
    status: worker, PATCH /fields e POST /llm-resolve condividono questa seam.
    """
    doc.template = result.template
    doc.raw_text = result.raw_text or None
    doc.extraction = result.to_jsonb()
    values = result.column_values()
    for field_name in NUMERIC_FIELDS:
        setattr(doc, field_name, values[field_name])
    doc.period_month = values["period_month"]
    doc.period_year = values["period_year"]
    doc.status = result.status.value
