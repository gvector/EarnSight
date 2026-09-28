"""Validazione aritmetica deterministica dell'estrazione.

Prima linea di difesa: controlli calcolabili senza LLM (coerenza netto/lordo/
trattenute, somma voci vs totali, periodo valido). Gli errori generano "issue"
con un'azione suggerita: `user` (inserimento manuale) o `llm` (richiesta mirata).
"""

from __future__ import annotations

from typing import Any

TOLERANCE = 0.02


def _value(fields: dict[str, Any], name: str) -> Any:
    """Return the raw value of a field from the provenance map.

    Parameters
    ----------
    fields : dict of str to Any
        Field map whose values expose a ``value`` attribute
        (FieldProvenance instances).
    name : str
        Canonical field name.

    Returns
    -------
    Any
        The field's value, or None when the field is missing.

    Examples
    --------
    >>> _value({}, "net_pay") is None
    True
    """
    field_value = fields.get(name)
    return field_value.value if field_value else None


def _is_number(value: Any) -> bool:
    """Check whether a value is an arithmetic-safe number.

    Strings and bools are rejected on purpose: Python's bool is an int
    subclass, so a bare ``isinstance`` check would let ``True`` flow
    into the arithmetic checks, and uncoerced strings from raw payloads
    must never take part in the deterministic checks.

    Parameters
    ----------
    value : Any
        Candidate value.

    Returns
    -------
    bool
        True when the value is an int or float and not a bool.

    Examples
    --------
    >>> _is_number(1750.0)
    True
    >>> _is_number(True)
    False
    >>> _is_number("1750")
    False
    """
    return isinstance(value, int | float) and not isinstance(value, bool)


def run_validation(
    fields: dict[str, Any], entries: list[Any], doc_type: str = "cedolino"
) -> dict[str, Any]:
    """Run the deterministic arithmetic checks on an extraction.

    First line of defence before any LLM involvement. Three families of
    checks run in order: presence of the three totals (gross, net,
    deductions); the arithmetic identity ``net + deductions == gross``
    within TOLERANCE; and period validity - a month/year in range for
    cedolini, only a plausible year for the CU, which has no pay month.
    When entries are present, their sums are cross-checked against the
    totals: mismatches are warnings (not blocking), since partially
    printed tables are legitimate. Every failure becomes an issue dict
    with a suggested action: ``"user"`` for arithmetic contradictions a
    human must fix, ``"llm"`` for missing values a targeted gateway
    request may recover.

    Parameters
    ----------
    fields : dict of str to Any
        Canonical fields keyed by name; values expose ``value``
        (FieldProvenance instances).
    entries : list of Any
        Recognised payslip entries; each exposes ``amount`` and
        ``entry_type`` ("spettanza" or "trattenuta").
    doc_type : str, optional
        ``"cedolino"`` (default) validates month and year; ``"cu"``
        validates only the reference year.

    Returns
    -------
    dict of str to Any
        Report with ``errors`` and ``warnings`` (lists of issue dicts),
        ``passed`` (True when no errors), ``error_count`` and
        ``warning_count``.

    Dependencies
    -----------
    - validation._value / _is_number : safe field access and typing.
    - validation.TOLERANCE : cents-level rounding slack.

    Examples
    --------
    >>> from types import SimpleNamespace
    >>> fields = {name: SimpleNamespace(value=v) for name, v in {
    ...     "gross_pay": 2500.0, "net_pay": 1750.0,
    ...     "total_deductions": 750.0, "period_month": 9,
    ...     "period_year": 2026}.items()}
    >>> run_validation(fields, [])["passed"]
    True
    """
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
