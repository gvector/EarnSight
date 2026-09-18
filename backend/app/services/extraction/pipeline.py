"""Pipeline di estrazione: testo → template → parser → validazione.

Restituisce un ExtractionResult, il contratto tipizzato definito in result.py.
"""

from __future__ import annotations

from pathlib import Path

from app.services.extraction.parser import parse_payslip
from app.services.extraction.result import (
    DocumentStatus,
    Entry,
    ExtractionResult,
    Issue,
    ValidationSummary,
)
from app.services.extraction.templates import detect_template
from app.services.extraction.text_layer import extract_lines, has_text_layer


def run_extraction(pdf_path: Path) -> ExtractionResult:
    if not has_text_layer(pdf_path):
        return ExtractionResult(
            status=DocumentStatus.NEEDS_OCR,
            issues=[
                Issue(
                    check="text_layer",
                    message="Nessun layer di testo: richiesto OCR (componente futura)",
                    action="user",
                )
            ],
            validation=ValidationSummary(passed=False, error_count=1),
        )

    lines = extract_lines(pdf_path)
    full_text = "\n".join(line.text for line in lines)
    template = detect_template(full_text)
    fields, entries = parse_payslip(lines)
    result = ExtractionResult(
        template=template,
        fields=fields,
        entries=[Entry(**entry) for entry in entries],
        raw_text=full_text,
    )
    result.revalidate()
    return result
