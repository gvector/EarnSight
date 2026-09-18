"""Validazione aritmetica deterministica dell'estrazione.

Prima linea di difesa: controlli calcolabili senza LLM (coerenza netto/lordo/
trattenute, somma voci vs totali, periodo valido). Gli errori generano "issue"
con un'azione suggerita: `user` (inserimento manuale) o `llm` (richiesta mirata).
"""

from __future__ import annotations

from typing import Any

TOLERANCE = 0.02


def _value(fields: dict[str, dict[str, Any]], name: str) -> Any:
    field_value = fields.get(name)
    return field_value.get("value") if field_value else None


def run_validation(
    fields: dict[str, dict[str, Any]], entries: list[dict[str, Any]]
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    gross = _value(fields, "gross_pay")
    net = _value(fields, "net_pay")
    deductions = _value(fields, "total_deductions")

    if gross is None:
        errors.append(
            {
                "field": "gross_pay",
                "check": "missing_field",
                "message": "Totale lordo non trovato nel documento",
                "action": "llm",
            }
        )
    if net is None:
        errors.append(
            {
                "field": "net_pay",
                "check": "missing_field",
                "message": "Netto da pagare non trovato nel documento",
                "action": "llm",
            }
        )

    if gross is not None and net is not None and deductions is not None:
        if abs(net + deductions - gross) > TOLERANCE:
            errors.append(
                {
                    "field": "net_pay",
                    "check": "net_consistency",
                    "message": (
                        f"Netto ({net}) + trattenute ({deductions}) non combacia "
                        f"con il lordo ({gross})"
                    ),
                    "action": "user",
                }
            )
    elif deductions is None and not any(e["field"] == "total_deductions" for e in errors):
        errors.append(
            {
                "field": "total_deductions",
                "check": "missing_field",
                "message": "Totale trattenute non trovato nel documento",
                "action": "llm",
            }
        )

    month = _value(fields, "period_month")
    year = _value(fields, "period_year")
    if month is None or year is None or not (1 <= month <= 12) or not (2000 <= year <= 2100):
        errors.append(
            {
                "field": "period_month",
                "check": "period_valid",
                "message": "Periodo di paga mancante o non valido",
                "action": "user",
            }
        )

    spettanze = sum(e["amount"] for e in entries if e["entry_type"] == "spettanza")
    trattenute = sum(e["amount"] for e in entries if e["entry_type"] == "trattenuta")
    if entries and gross is not None and abs(spettanze - gross) > 1.0:
        warnings.append(
            {
                "field": None,
                "check": "entries_sum",
                "message": (f"Somma voci spettanze ({spettanze}) diversa dal lordo ({gross})"),
                "action": "llm",
            }
        )
    if entries and deductions is not None and abs(trattenute - deductions) > 1.0:
        warnings.append(
            {
                "field": None,
                "check": "entries_deductions",
                "message": (
                    f"Somma voci trattenute ({trattenute}) diversa dal totale "
                    f"trattenute ({deductions})"
                ),
                "action": "llm",
            }
        )

    return {
        "errors": errors,
        "warnings": warnings,
        "passed": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
