"""Validazione aritmetica deterministica dell'estrazione.

Prima linea di difesa: controlli calcolabili senza LLM (coerenza netto/lordo/
trattenute, somma voci vs totali, periodo valido). Gli errori generano "issue"
con un'azione suggerita: `user` (inserimento manuale) o `llm` (richiesta mirata).
"""

from __future__ import annotations

from typing import Any

TOLERANCE = 0.02


def _value(fields: dict[str, Any], name: str) -> Any:
    field_value = fields.get(name)
    return field_value.value if field_value else None


def _is_number(value: Any) -> bool:
    """Un valore aritmetico valido: mai stringhe o bool lungo la pipeline."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def run_validation(
    fields: dict[str, Any], entries: list[Any], doc_type: str = "cedolino"
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

    if _is_number(gross) and _is_number(net) and _is_number(deductions):
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
    elif not _is_number(deductions) and not any(e["field"] == "total_deductions" for e in errors):
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
    if doc_type == "cu":
        # La CU non ha un mese di paga: il periodo è solo l'anno di riferimento.
        if not (_is_number(year) and 2000 <= year <= 2100):
            errors.append(
                {
                    "field": "period_year",
                    "check": "period_valid",
                    "message": "Anno di riferimento della CU mancante o non valido",
                    "action": "user",
                }
            )
    elif not (_is_number(month) and _is_number(year) and 1 <= month <= 12 and 2000 <= year <= 2100):
        errors.append(
            {
                "field": "period_month",
                "check": "period_valid",
                "message": "Periodo di paga mancante o non valido",
                "action": "user",
            }
        )

    spettanze = sum(e.amount for e in entries if e.entry_type == "spettanza")
    trattenute = sum(e.amount for e in entries if e.entry_type == "trattenuta")
    if entries and _is_number(gross) and abs(spettanze - gross) > 1.0:
        warnings.append(
            {
                "field": None,
                "check": "entries_sum",
                "message": (f"Somma voci spettanze ({spettanze}) diversa dal lordo ({gross})"),
                "action": "llm",
            }
        )
    if entries and _is_number(deductions) and abs(trattenute - deductions) > 1.0:
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
