"""Pipeline di estrazione: testo → template → parser → validazione.

Restituisce un dizionario serializzabile in JSONB con campi, voci, issue e
stato (`done` | `needs_review` | `needs_ocr`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.extraction.parser import parse_payslip
from app.services.extraction.templates import detect_template
from app.services.extraction.text_layer import extract_lines, has_text_layer
from app.services.extraction.validation import run_validation


def _penalize_error_fields(fields: dict[str, dict[str, Any]], issues: list[dict[str, Any]]) -> None:
    for issue in issues:
        field_name = issue.get("field")
        if field_name and field_name in fields and not fields[field_name].get("corrected"):
            fields[field_name]["confidence"] = min(fields[field_name].get("confidence", 1.0), 0.3)


def run_extraction(pdf_path: Path) -> dict[str, Any]:
    if not has_text_layer(pdf_path):
        return {
            "status": "needs_ocr",
            "template": None,
            "fields": {},
            "entries": [],
            "issues": [
                {
                    "field": None,
                    "check": "text_layer",
                    "message": "Nessun layer di testo: richiesto OCR (componente futura)",
                    "action": "user",
                }
            ],
            "validation": {"passed": False, "error_count": 1, "warning_count": 0},
            "raw_text": "",
        }

    lines = extract_lines(pdf_path)
    full_text = "\n".join(line.text for line in lines)
    template = detect_template(full_text)
    fields, entries = parse_payslip(lines)
    report = run_validation(fields, entries)
    issues = report["errors"] + report["warnings"]
    _penalize_error_fields(fields, issues)

    return {
        "status": "done" if report["passed"] else "needs_review",
        "template": template,
        "fields": fields,
        "entries": entries,
        "issues": issues,
        "validation": {
            "passed": report["passed"],
            "error_count": report["error_count"],
            "warning_count": report["warning_count"],
        },
        "raw_text": full_text,
    }


def revalidate(fields: dict[str, dict[str, Any]], entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Rivalida dopo correzioni utente/LLM; restituisce issues+validation aggiornati."""
    report = run_validation(fields, entries)
    issues = report["errors"] + report["warnings"]
    _penalize_error_fields(fields, issues)
    return {
        "issues": issues,
        "validation": {
            "passed": report["passed"],
            "error_count": report["error_count"],
            "warning_count": report["warning_count"],
        },
    }
