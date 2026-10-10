"""Validazione aritmetica deterministica dell'estrazione.

Prima linea di difesa: controlli calcolabili senza LLM (coerenza netto/lordo/
trattenute, somma voci vs totali, periodo valido; per la CU imponibile, IRPEF
trattenuta e anno). Gli errori generano "issue" con un'azione suggerita: `user`
(inserimento manuale) o `llm` (richiesta mirata).
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
    deductions); the arithmetic identity ``gross - deductions + rounding
    == net`` within TOLERANCE (``rounding`` is the optional "arrotondamento"
    some payrolls add to reach a round net, 0 when absent); and period
    validity - a month/year in range.
    When entries are present, their sums are cross-checked against the
    totals: mismatches are warnings (not blocking), since partially
    printed tables are legitimate. Every failure becomes an issue dict
    with a suggested action: ``"user"`` for arithmetic contradictions a
    human must fix, ``"llm"`` for missing values a targeted gateway
    request may recover. A CU skips all of this and goes to
    ``_validate_cu``: it has no gross/net/deductions nor entries.

    Parameters
    ----------
    fields : dict of str to Any
        Canonical fields keyed by name; values expose ``value``
        (FieldProvenance instances).
    entries : list of Any
        Recognised payslip entries; each exposes ``amount`` and
        ``entry_type`` ("spettanza" or "trattenuta").
    doc_type : str, optional
        ``"cedolino"`` (default) runs the payslip checks; ``"cu"`` runs
        the CU checks of ``_validate_cu``.

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
    - validation._validate_cu : the CU checks.

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
    if doc_type == "cu":
        return _validate_cu(fields)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    gross = _value(fields, "gross_pay")
    net = _value(fields, "net_pay")
    deductions = _value(fields, "total_deductions")
    rounding = _value(fields, "rounding")
    rounding = rounding if _is_number(rounding) else 0.0

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
        if abs(gross - deductions + rounding - net) > TOLERANCE:
            with_rounding = f" + arrotondamento ({rounding})" if rounding else ""
            errors.append(
                {
                    "field": "net_pay",
                    "check": "net_consistency",
                    "message": (
                        f"Lordo ({gross}) − trattenute ({deductions}){with_rounding} "
                        f"non combacia con il netto ({net})"
                    ),
                    "action": "user",
                }
            )
    elif not _is_number(deductions):
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
    if not (_is_number(month) and _is_number(year) and 1 <= month <= 12 and 2000 <= year <= 2100):
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


def _validate_cu(fields: dict[str, Any]) -> dict[str, Any]:
    """Run the deterministic checks of a CU.

    The CU has no gross/net/deductions totals and no entries, so the
    payslip checks do not apply. The checks are: taxable income (point 1)
    and IRPEF withheld (point 21) present (``missing_field``, action
    ``"llm"``); a plausible reference year (``period_valid``, ``"user"``);
    and ``tax_consistency`` (``"user"``): the tax neither negative nor
    above the taxable income, nor the taxable income negative - the one
    arithmetic check available inside a CU, which catches the two points
    read swapped or shifted.

    Parameters
    ----------
    fields : dict of str to Any
        Canonical CU fields keyed by name; values expose ``value``.

    Returns
    -------
    dict of str to Any
        Report with the same shape as ``run_validation``; ``warnings`` is
        always empty.

    Examples
    --------
    >>> from types import SimpleNamespace
    >>> fields = {name: SimpleNamespace(value=v) for name, v in {
    ...     "period_year": 2025, "taxable_income": 25000.0,
    ...     "income_tax": 5000.0}.items()}
    >>> _validate_cu(fields)["passed"]
    True
    """
    errors: list[dict[str, Any]] = []
    taxable = _value(fields, "taxable_income")
    tax = _value(fields, "income_tax")
    year = _value(fields, "period_year")

    if taxable is None:
        errors.append(
            {
                "field": "taxable_income",
                "check": "missing_field",
                "message": "Imponibile IRPEF (punto 1) non trovato nella CU",
                "action": "llm",
            }
        )
    if tax is None:
        errors.append(
            {
                "field": "income_tax",
                "check": "missing_field",
                "message": "IRPEF trattenuta (punto 21) non trovata nella CU",
                "action": "llm",
            }
        )
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
    if _is_number(taxable) and _is_number(tax) and (tax > taxable or tax < 0 or taxable < 0):
        errors.append(
            {
                "field": "income_tax",
                "check": "tax_consistency",
                "message": (
                    f"IRPEF trattenuta ({tax}) maggiore dell'imponibile ({taxable}) o negativa"
                ),
                "action": "user",
            }
        )
    return {
        "errors": errors,
        "warnings": [],
        "passed": not errors,
        "error_count": len(errors),
        "warning_count": 0,
    }
