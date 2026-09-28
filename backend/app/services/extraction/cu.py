"""Label-based parser for the CU (Certificazione Unica).

Parses the totals of the employee-income section (quadro lavoro dipendente)
of the CU, the Italian annual income certificate: compenso lordo (gross
pay), totale ritenute (total deductions), netto erogato (net pay) and the
reference year. The output uses the same shape as the payslip parser, so
the CU can flow through the same ExtractionResult contract and be used for
cross-validation against the payslips.

Phase-1 scope is limited to the section totals; the individual CU entries
are left for extraction once real samples arrive. Unlike payslips, CU
validation checks only the year, not the month.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.extraction.parser import AMOUNT_PATTERN, parse_amount
from app.services.extraction.result import FieldProvenance
from app.services.extraction.text_layer import Line

# Specifiche prima, generiche in coda ("Netto" matcherebbe anche
# "Netto erogato": l'ordine del registry decide).
_CU_TOTAL_LABELS: dict[str, list[str]] = {
    "gross_pay": [r"(?i:compenso\s+lordo)"],
    "total_deductions": [r"(?i:totale(?:\s+delle)?\s+ritenute)", r"(?i:ritenute)"],
    "net_pay": [r"(?i:netto\s+erogato)", r"(?i:netto)"],
}

_CU_YEAR_RE = re.compile(r"(?i:anno(?:\s+di\s+)?(?:riferimento|imposta)?\s*:?\s*)(\d{4})")


def _parsed(value: Any, source: str) -> FieldProvenance:
    """Build a provenance-stamped field for a successfully parsed CU value.

    Convenience wrapper around ``FieldProvenance.parsed`` so every CU field
    carries its parsed value, the source line it was extracted from and the
    default parsed confidence.

    Parameters
    ----------
    value : Any
        Parsed value: float for amounts, int for the reference year.
    source : str
        Text of the line the value was extracted from.

    Returns
    -------
    FieldProvenance
        Field ready to be stored in the fields dict of the result.
    """
    return FieldProvenance.parsed(value, source=source)


def parse_cu(lines: list[Line]) -> tuple[dict[str, FieldProvenance], list[dict[str, Any]]]:
    """Parse the CU totals and the reference year from extracted lines.

    For each canonical field (gross_pay, total_deductions, net_pay) the
    label-pattern registry is tried in order, most specific first — the
    registry order is what decides, since a generic label like ``"netto"``
    would also match ``"netto erogato"``. The first label whose pattern
    matches a line wins, and the matched amount is parsed with the shared
    payslip amount pattern. The reference year is recovered from an
    ``"Anno (di riferimento/di imposta)"`` label only if no field already
    supplied it.

    Parameters
    ----------
    lines : list of Line
        Text lines with layout info, as produced by
        ``text_layer.extract_lines``.

    Returns
    -------
    tuple of (dict of str to FieldProvenance, list of dict)
        The fields dict mapping canonical names to provenance-stamped
        values, and an empty entries list: individual CU entries are a
        future phase.

    Dependencies
    -----------
    - parser.AMOUNT_PATTERN, parser.parse_amount : shared Italian amount
      pattern and float conversion.
    - result.FieldProvenance : field provenance shape.
    - text_layer.Line : input line type with word coordinates.

    Examples
    --------
    >>> from app.services.extraction.text_layer import Line, Word
    >>> line = Line(page=0, y=100.0, words=[
    ...     Word("Compenso", 0.0, 100.0, 40.0, 108.0, 0),
    ...     Word("lordo:", 44.0, 100.0, 70.0, 108.0, 0),
    ...     Word("30.000,00", 74.0, 100.0, 100.0, 108.0, 0),
    ... ])
    >>> fields, entries = parse_cu([line])
    >>> fields["gross_pay"].value
    30000.0
    >>> entries
    []
    """
    fields: dict[str, FieldProvenance] = {}
    for name, labels in _CU_TOTAL_LABELS.items():
        if name in fields:
            continue
        for label in labels:
            pattern = re.compile(label + r"\s*:?\s*(" + AMOUNT_PATTERN + r")")
            for line in lines:
                match = pattern.search(line.text)
                if match:
                    fields[name] = _parsed(parse_amount(match.group(1)), line.text)
                    break
            if name in fields:
                break

    if "period_year" not in fields:
        for line in lines:
            match = _CU_YEAR_RE.search(line.text)
            if match:
                fields["period_year"] = _parsed(int(match.group(1)), line.text)
                break
    return fields, []
