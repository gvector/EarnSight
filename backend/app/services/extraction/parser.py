"""Parser a regole per cedolini italiani (label-based, generico).

Produce campi canonici con confidenza e riga sorgente, più le voci di paga
(spettanze/trattenute) riconosciute dalle colonne della tabella.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.services.extraction.result import NUMERIC_FIELDS, FieldProvenance
from app.services.extraction.text_layer import Line

AMOUNT_PATTERN = r"\d{1,3}(?:\.\d{3})*,\d{2}"
_AMOUNT_RE = re.compile(rf"^{AMOUNT_PATTERN}$")
_CODE_RE = re.compile(r"^\d{1,4}$")

# Ordine dei totali: prima le etichette specifiche, poi quelle generiche
# ("Netto" da solo matcherebbe anche "Netto imponibile").
_TOTAL_LABELS: dict[str, list[str]] = {
    "gross_pay": [
        r"(?i:(?:totale\s+)?compenso\s+lordo)",
        r"(?i:retribuzione\s+lorda)",
        r"(?i:lordo\s+di\s+paga)",
        r"(?i:totale\s+lordo)",
    ],
    "total_deductions": [
        r"(?i:totale(?:\s+delle)?\s+trattenute)",
        r"(?i:somma\s+trattenute)",
    ],
    "net_pay": [
        r"(?i:netto\s+(?:da|a)\s+pagare)",
        r"(?i:netto\s+in\s+busta)",
        r"(?i:(?:totale\s+)?netto)",  # generica, in coda
    ],
}

_TEXT_LABELS: dict[str, str] = {
    "company_name": r"(?i:azienda|datore\s+di\s+lavoro|ragione\s+sociale)",
    "employee_name": r"(?i:dipendente|lavoratore)",
    "matricola": r"(?i:matricola)",
}

_FISCAL_CODE_RE = re.compile(
    r"(?i:codice\s+fiscale)\s*:?\s*([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])"
)
_PERIOD_RE = re.compile(r"(?i:periodo\s+di\s+paga|competenza)\s*:?\s*(\d{1,2})\s*/\s*(\d{2,4})")

_ENTRIES_STOP_RE = re.compile(
    r"(?i:compenso\s+lordo|totale\s+lordo|retribuzione\s+lorda|lordo\s+di\s+paga"
    r"|totale(?:\s+delle)?\s+trattenute|somma\s+trattenute"
    r"|netto\s+(?:da|a)\s+pagare|netto\s+in\s+busta|(?:totale\s+)?netto)"
)


def parse_amount(raw: str) -> float:
    """Convert an Italian-formatted amount string to float.

    Italian payslips print amounts with ``.`` as the thousands separator
    and ``,`` as the decimal separator (e.g. ``1.234,56``). Stripping the
    dots and swapping the comma for a dot yields a string the float
    constructor understands.

    Parameters
    ----------
    raw : str
        Amount in Italian format, as matched by AMOUNT_PATTERN.

    Returns
    -------
    float
        Numeric value of the amount.

    Raises
    ------
    ValueError
        If ``raw`` is not a valid float after reformatting.

    Dependencies
    -----------
    - parser.AMOUNT_PATTERN : the format this function expects.

    Examples
    --------
    >>> parse_amount("1.234,56")
    1234.56
    >>> parse_amount("250,00")
    250.0
    """
    return float(raw.replace(".", "").replace(",", "."))


def _field_value(value: Any, line: Line, confidence: float = 0.9) -> FieldProvenance:
    """Wrap a parsed value in a FieldProvenance with its source line.

    Parameters
    ----------
    value : Any
        Parsed value.
    line : Line
        Source line the value was parsed from; its rendered text
        becomes the provenance ``source``.
    confidence : float, optional
        Trust score; defaults to 0.9.

    Returns
    -------
    FieldProvenance
        New provenance with ``corrected`` left False.

    Dependencies
    -----------
    - result.FieldProvenance.parsed : provenance constructor.

    Examples
    --------
    >>> from app.services.extraction.text_layer import Line, Word
    >>> line = Line(page=0, y=50.0, words=[
    ...     Word("Periodo:", 0.0, 50.0, 40.0, 58.0, 0),
    ...     Word("09/2026", 45.0, 50.0, 80.0, 58.0, 0)])
    >>> pv = _field_value(9, line)
    >>> (pv.value, pv.source)
    (9, 'Periodo: 09/2026')
    """
    return FieldProvenance.parsed(value, source=line.text, confidence=confidence)


def _parse_total_fields(lines: list[Line], fields: dict[str, dict[str, Any]]) -> None:
    """Extract the total fields (gross, net, deductions) from labels.

    Label-based matching: for each canonical total, the specific label
    patterns are tried first (in declared order) because generic ones
    would also match narrower labels - a bare ``Netto`` pattern would
    capture ``Netto imponibile``. If no specific label matched, a second
    pass retries with the generic pattern (the last of each list) so
    loosely formatted payslips still yield the three totals.

    Parameters
    ----------
    lines : list of Line
        Text-layer lines of the payslip, in reading order.
    fields : dict of str to Any
        Parsed-field accumulator, keyed by canonical field name;
        updated in place; existing keys are never overwritten.

    Returns
    -------
    None

    Dependencies
    -----------
    - parser._TOTAL_LABELS : ordered label patterns per total.
    - parser.AMOUNT_PATTERN / parse_amount : amount matching and
      conversion.
    - parser._field_value : provenance wrapping.

    Examples
    --------
    >>> from app.services.extraction.text_layer import Line, Word
    >>> lines = [Line(page=0, y=50.0, words=[
    ...     Word("Netto", 0.0, 50.0, 40.0, 58.0, 0),
    ...     Word("1.750,00", 45.0, 50.0, 90.0, 58.0, 0)])]
    >>> fields = {}
    >>> _parse_total_fields(lines, fields)
    >>> fields["net_pay"].value
    1750.0
    """
    for name in NUMERIC_FIELDS:
        for label in _TOTAL_LABELS[name]:
            pattern = re.compile(label + r"\s*:?\s*(" + AMOUNT_PATTERN + r")")
            for line in lines:
                if name in fields:
                    break
                match = pattern.search(line.text)
                if match:
                    fields[name] = _field_value(parse_amount(match.group(1)), line)
    for name in NUMERIC_FIELDS:
        if name not in fields:
            generic = re.compile(_TOTAL_LABELS[name][-1] + r"\s*:?\s*(" + AMOUNT_PATTERN + r")")
            for line in lines:
                match = generic.search(line.text)
                if match:
                    fields[name] = _field_value(parse_amount(match.group(1)), line)
                    break


def _parse_simple_fields(lines: list[Line], fields: dict[str, dict[str, Any]]) -> None:
    """Extract scalar fields: fiscal code, pay period, names, matricola.

    Single pass over all lines, first match wins per field: the fiscal
    code via its rigid 16-character regex, the pay period from an
    ``MM/YYYY`` (or ``MM/YY``) notation with two-digit years normalised
    to 2000+, and the remaining text labels (company, employee,
    matricola) as label-colon-value pairs.

    Parameters
    ----------
    lines : list of Line
        Text-layer lines of the payslip, in reading order.
    fields : dict of str to Any
        Parsed-field accumulator, keyed by canonical field name;
        updated in place; existing keys are never overwritten.

    Returns
    -------
    None

    Dependencies
    -----------
    - parser._FISCAL_CODE_RE / _PERIOD_RE / _TEXT_LABELS : matchers.
    - parser._field_value : provenance wrapping.

    Examples
    --------
    >>> from app.services.extraction.text_layer import Line, Word
    >>> lines = [Line(page=0, y=20.0, words=[
    ...     Word("Codice", 0.0, 20.0, 30.0, 28.0, 0),
    ...     Word("fiscale:", 35.0, 20.0, 60.0, 28.0, 0),
    ...     Word("RSSMRA80A01H501U", 65.0, 20.0, 120.0, 28.0, 0)])]
    >>> fields = {}
    >>> _parse_simple_fields(lines, fields)
    >>> fields["fiscal_code"].value
    'RSSMRA80A01H501U'
    """
    for line in lines:
        if "fiscal_code" not in fields:
            match = _FISCAL_CODE_RE.search(line.text)
            if match:
                fields["fiscal_code"] = _field_value(match.group(1), line)
        if "period_month" not in fields:
            match = _PERIOD_RE.search(line.text)
            if match:
                month = int(match.group(1))
                year = int(match.group(2))
                if year < 100:
                    year += 2000
                fields["period_month"] = _field_value(month, line)
                fields["period_year"] = _field_value(year, line)
        for name, label in _TEXT_LABELS.items():
            if name in fields:
                continue
            match = re.search(label + r"\s*:?\s*(\S.*)", line.text)
            if match:
                fields[name] = _field_value(match.group(1).strip(), line)


def _parse_entries(lines: list[Line]) -> list[dict[str, Any]]:
    """Recognise payslip line items from the earnings/deductions table.

    Locates the header row containing both the ``Spettanze`` and
    ``Trattenute`` column labels and records their horizontal positions.
    Each subsequent row is scanned until a totals label ends the table:
    every Italian-format amount is attributed to the closer column header
    (geometry-based classification), and the row's numeric code and the
    remaining words become the item's code and description. Rows without
    amounts are skipped.

    Parameters
    ----------
    lines : list of Line
        Text-layer lines of the payslip, in reading order.

    Returns
    -------
    list of dict
        Recognised entries, each with ``code``, ``description``,
        ``amount`` and ``entry_type`` keys; empty when no table header
        is found.

    Dependencies
    -----------
    - parser._ENTRIES_STOP_RE : end-of-table detection.
    - parser._AMOUNT_RE / _CODE_RE : amount and code matching.
    - parser.parse_amount : Italian amount conversion.

    Examples
    --------
    >>> from app.services.extraction.text_layer import Line, Word
    >>> lines = [
    ...     Line(page=0, y=10.0, words=[Word("Spettanze", 0.0, 10.0, 40.0, 18.0, 0),
    ...                                Word("Trattenute", 100.0, 10.0, 140.0, 18.0, 0)]),
    ...     Line(page=0, y=20.0, words=[Word("Stipendio", 0.0, 20.0, 40.0, 28.0, 0),
    ...                               Word("1.500,00", 10.0, 20.0, 50.0, 28.0, 0)])]
    >>> entries = _parse_entries(lines)
    >>> (entries[0]["description"], entries[0]["amount"],
    ...  entries[0]["entry_type"])
    ('Stipendio', 1500.0, 'spettanza')
    """
    header_idx, col_spett_x, col_tratt_x = None, None, None
    for i, line in enumerate(lines):
        by_text = {w.text.lower(): w for w in line.words}
        if "spettanze" in by_text and "trattenute" in by_text:
            header_idx = i
            col_spett_x = by_text["spettanze"].center_x
            col_tratt_x = by_text["trattenute"].center_x
            break
    if header_idx is None:
        return []

    entries: list[dict[str, Any]] = []
    for line in lines[header_idx + 1 :]:
        if _ENTRIES_STOP_RE.search(line.text):
            break
        amounts: list[tuple[str, float]] = []
        for word in line.words:
            if _AMOUNT_RE.fullmatch(word.text):
                distance_spett = abs(word.center_x - col_spett_x)
                distance_tratt = abs(word.center_x - col_tratt_x)
                entry_type = "spettanza" if distance_spett <= distance_tratt else "trattenuta"
                amounts.append((entry_type, parse_amount(word.text)))
        if not amounts:
            continue

        code_word = next((w for w in line.words if _CODE_RE.fullmatch(w.text)), None)
        description_words = [
            w.text for w in line.words if w is not code_word and not _AMOUNT_RE.fullmatch(w.text)
        ]
        # esclude l'etichetta di colonna ripetuta sulla riga, se presente
        description = " ".join(
            t for t in description_words if t.lower() not in ("spettanze", "trattenute")
        )
        for entry_type, amount in amounts:
            entries.append(
                {
                    "code": code_word.text if code_word else None,
                    "description": description or None,
                    "amount": amount,
                    "entry_type": entry_type,
                }
            )
    return entries


def parse_payslip(
    lines: list[Line],
) -> tuple[dict[str, FieldProvenance], list[dict[str, Any]]]:
    """Full generic parsing of a payslip text layer.

    Orchestrates the three generic passes - scalar fields, totals and
    table entries - and returns them together. The registry
    TEMPLATE_PARSERS points template-specific parsers at this same
    contract; this function is the fallback when no tuned parser exists
    for the detected template.

    Parameters
    ----------
    lines : list of Line
        Text-layer lines of the payslip, in reading order.

    Returns
    -------
    tuple of (dict of str to FieldProvenance, list of dict)
        Canonical fields keyed by name and the recognised entries.

    Dependencies
    -----------
    - parser._parse_simple_fields / _parse_total_fields /
      _parse_entries : the three passes.

    Examples
    --------
    >>> from app.services.extraction.text_layer import Line, Word
    >>> lines = [Line(page=0, y=50.0, words=[
    ...     Word("Netto", 0.0, 50.0, 40.0, 58.0, 0),
    ...     Word("1.750,00", 45.0, 50.0, 90.0, 58.0, 0)])]
    >>> fields, entries = parse_payslip(lines)
    >>> fields["net_pay"].value
    1750.0
    """
    fields: dict[str, dict[str, Any]] = {}
    _parse_simple_fields(lines, fields)
    _parse_total_fields(lines, fields)
    entries = _parse_entries(lines)
    return fields, entries


# Registry per-template: detect_template sceglie il parser da qui. I parser
# specifici (zucchetti, teamsystem, ...) si registrano man mano che vengono
# tarati sui PDF reali; fino ad allora usano il fallback generico.
TEMPLATE_PARSERS: dict[str, Callable[[list[Line]], tuple[dict, list[dict]]]] = {}


def get_parser(template: str | None) -> Callable[[list[Line]], tuple[dict, list[dict]]]:
    """Return the parser registered for a template, generic as fallback.

    Looks up the detected template signature in TEMPLATE_PARSERS; when no
    tuned parser has been registered yet (or the template is None), the
    generic label-based ``parse_payslip`` is returned so the pipeline
    always has a callable with the same contract.

    Parameters
    ----------
    template : str or None
        Template signature produced by ``detect_template``.

    Returns
    -------
    Callable
        Parser with the ``parse_payslip`` contract:
        ``list[Line] -> (fields, entries)``.

    Dependencies
    -----------
    - parser.TEMPLATE_PARSERS : per-template registry.
    - parser.parse_payslip : generic fallback.

    Examples
    --------
    >>> get_parser(None) is parse_payslip
    True
    """
    return TEMPLATE_PARSERS.get(template or "generic", parse_payslip)
