"""Parser for Zucchetti payslips ("Modello per procedure della Zucchetti").

Layout facts this parser relies on, observed on real documents:

- the text layer fuses small labels with an ``s`` in place of spaces
  (``TOTALEsCOMPETENZE``, ``PERIODOsDIsRETRIBUZIONE``): label patterns accept
  a space or an ``s`` between words, so either rendering matches;
- header values sit on the line *below* their label, in the label's column
  (company, employee, period, net pay); totals sit on the label's line, to
  its *right*;
- the entries table has the columns IMPORTO BASE, RIFERIMENTO, TRATTENUTE,
  COMPETENZE: only amounts in the last two are entries, rows with a value
  in IMPORTO BASE alone (taxable bases, TFR quota, ...) are informative, and
  so are amounts in parentheses (employer share, e.g. ``C/Ditta``), which
  the totals do not include;
- the net pay includes an ``ARROTONDAMENTO`` (rounding) to a round figure,
  extracted as the ``rounding`` field so validation can close the equation;
- an additional month (13th/14th) carries ``AGG.`` next to the period.

The parser receives only the payslip pages: the attendance sheet some
documents prepend is filtered out upstream (``templates.classify_pages``).
"""

from __future__ import annotations

import re
from typing import Any

from app.services.extraction.parser import AMOUNT_PATTERN, parse_amount
from app.services.extraction.result import FieldProvenance
from app.services.extraction.text_layer import Line, Word

MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "gennaio",
            "febbraio",
            "marzo",
            "aprile",
            "maggio",
            "giugno",
            "luglio",
            "agosto",
            "settembre",
            "ottobre",
            "novembre",
            "dicembre",
        ),
        start=1,
    )
}

_AMOUNT_RE = re.compile(rf"^{AMOUNT_PATTERN}$")
# l'arrotondamento può essere negativo: segno davanti o dietro
_SIGNED_AMOUNT_RE = re.compile(rf"^(-?)({AMOUNT_PATTERN})(-?)$")
_CODE_RE = re.compile(r"^(?=.*\d)[A-Z0-9]{6}$")
_FISCAL_CODE_RE = re.compile(r"^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$")
_COLUMN_MARGIN = 5.0  # pt di tolleranza a sinistra della colonna dell'etichetta
_MAX_LABEL_WORDS = 6


def _label(*words: str) -> re.Pattern[str]:
    """Whole-word label pattern tolerant to the fused ``s`` separator.

    Matched with ``fullmatch`` against runs of whole words, so
    ``competenze`` never matches inside ``TOTALEsCOMPETENZE``; a leading
    ``s`` is the fused separator of the previous label (``sMatricola``).
    """
    return re.compile(r"(?i)s?" + r"[s ]".join(words))


_PERIOD = _label("periodo", "di", "retribuzione")
_COMPANY = _label("ragione", "sociale")
_EMPLOYEE_CODE = _label("codice", "dipendente")
_EMPLOYEE_NAME = _label("cognome", "e", "nome")
_MATRICOLA = _label("matricola")
_ENTRIES_HEADER = _label("voci", "variabili", "del", "mese")
_BASE_COLUMN = _label("importo", "base")
_REFERENCE_COLUMN = _label("riferimento")
_DEDUCTIONS_COLUMN = _label("trattenute")
_EARNINGS_COLUMN = _label("competenze")
_ENTRIES_END = _label("conguaglio")
_TOTAL_EARNINGS = _label("totale", "competenze")
_TOTAL_DEDUCTIONS = _label("totale", "trattenute")
_ROUNDING = _label("arrotondamento")
_NET = _label("netto", "del", "mese")


def _find(lines: list[Line], pattern: re.Pattern[str]) -> tuple[int, Word, Word] | None:
    """First run of whole words matching the label: (line index, first word, last word)."""
    for index, line in enumerate(lines):
        words = line.words
        for i in range(len(words)):
            for j in range(i, min(i + _MAX_LABEL_WORDS, len(words))):
                if pattern.fullmatch(" ".join(w.text for w in words[i : j + 1])):
                    return index, words[i], words[j]
    return None


def _below(lines: list[Line], pattern: re.Pattern[str]) -> list[Word]:
    """Words on the line below the label, within the label's column.

    The column runs from the label's left edge to the next word on the
    label's own line (the neighbouring label), or to the page edge.
    """
    found = _find(lines, pattern)
    if found is None or found[0] + 1 >= len(lines):
        return []
    index, first, last = found
    label_line, value_line = lines[index], lines[index + 1]
    if value_line.page != label_line.page:
        return []
    right = min((w.x0 for w in label_line.words if w.x0 > last.x1), default=float("inf"))
    return [w for w in value_line.words if first.x0 - _COLUMN_MARGIN <= w.x0 < right]


def _amount_right(lines: list[Line], pattern: re.Pattern[str]) -> tuple[float, Line] | None:
    """First (signed) amount to the right of the label, on the label's line.

    The sign may be fused (``-0,66``, ``0,66-``) or a separate ``-`` word
    between the label and the amount.
    """
    found = _find(lines, pattern)
    if found is None:
        return None
    index, _, last = found
    words = lines[index].words
    for k, word in enumerate(words):
        match = _SIGNED_AMOUNT_RE.fullmatch(word.text)
        if word.x0 > last.x1 and match:
            loose_minus = k > 0 and words[k - 1].text == "-" and words[k - 1].x0 > last.x1
            sign = -1 if (match.group(1) or match.group(3) or loose_minus) else 1
            return sign * parse_amount(match.group(2)), lines[index]
    return None


def _is_table_end(line: Line) -> bool:
    """CONGUAGLIO section label: first word of a line that carries no amount.

    A voci row may also start with «Conguaglio …» (with or without a code),
    but a real row has an amount in one of its columns.
    """
    return bool(_ENTRIES_END.fullmatch(line.words[0].text)) and not any(
        _SIGNED_AMOUNT_RE.fullmatch(w.text) for w in line.words
    )


def _text(words: list[Word]) -> str | None:
    return " ".join(w.text for w in words) or None


def _header_fields(lines: list[Line], fields: dict[str, FieldProvenance]) -> None:
    """Period, company and employee identity from the label/value pairs."""
    period = _below(lines, _PERIOD)
    if len(period) >= 2 and period[0].text.lower() in MONTHS and period[1].text.isdigit():
        source = _text(period)
        fields["period_month"] = FieldProvenance.parsed(MONTHS[period[0].text.lower()], source)
        fields["period_year"] = FieldProvenance.parsed(int(period[1].text), source)
        if any(w.text.upper().startswith("AGG") for w in period[2:]):
            fields["additional_payment"] = FieldProvenance.parsed(True, source)

    for name, pattern in (
        ("company_name", _COMPANY),
        ("employee_code", _EMPLOYEE_CODE),
        ("matricola", _MATRICOLA),
    ):
        value = _text(_below(lines, pattern))
        if value:
            fields[name] = FieldProvenance.parsed(value, value)

    # il codice fiscale del dipendente è sulla riga di COGNOME E NOME (quello a
    # sinistra in testata è dell'azienda)
    name_words = _below(lines, _EMPLOYEE_NAME)
    if name_words:
        fields["employee_name"] = FieldProvenance.parsed(_text(name_words), _text(name_words))
    found = _find(lines, _EMPLOYEE_NAME)
    if found and found[0] + 1 < len(lines):
        for word in lines[found[0] + 1].words:
            if _FISCAL_CODE_RE.fullmatch(word.text):
                fields["fiscal_code"] = FieldProvenance.parsed(word.text, word.text)


def _total_fields(lines: list[Line], fields: dict[str, FieldProvenance]) -> None:
    """Totals block: earnings, deductions, rounding (right of label), net (below).

    Searched only after the voci table (from CONGUAGLIO on), so a row whose
    description spells «ARROTONDAMENTO» can never stand in for a total.
    """
    start = next((i for i, line in enumerate(lines) if _is_table_end(line)), 0)
    lines = lines[start:]
    for name, pattern in (
        ("gross_pay", _TOTAL_EARNINGS),
        ("total_deductions", _TOTAL_DEDUCTIONS),
        ("rounding", _ROUNDING),
    ):
        found = _amount_right(lines, pattern)
        if found:
            fields[name] = FieldProvenance.parsed(found[0], found[1].text)
    net = next((w for w in _below(lines, _NET) if _AMOUNT_RE.fullmatch(w.text)), None)
    if net is not None:
        fields["net_pay"] = FieldProvenance.parsed(parse_amount(net.text), net.text)


def _entries(lines: list[Line]) -> list[dict[str, Any]]:
    """Rows of the VOCI VARIABILI table with an amount in TRATTENUTE or COMPETENZE.

    Each amount goes to the nearest column header by horizontal centre;
    amounts in IMPORTO BASE or RIFERIMENTO are bases, not entries, and
    amounts in parentheses are informative. The table ends at CONGUAGLIO
    or at the page break.
    """
    entries: list[dict[str, Any]] = []
    start = 0
    while (header := _find(lines[start:], _ENTRIES_HEADER)) is not None:
        index = start + header[0]
        columns: dict[str, float] = {}  # ruolo → centro orizzontale dell'intestazione
        description_end = float("inf")  # la descrizione finisce dove inizia IMPORTO BASE
        for role, pattern in (
            ("base", _BASE_COLUMN),
            ("riferimento", _REFERENCE_COLUMN),
            ("trattenuta", _DEDUCTIONS_COLUMN),
            ("spettanza", _EARNINGS_COLUMN),
        ):
            found = _find([lines[index]], pattern)
            if found:
                columns[role] = (found[1].x0 + found[2].x1) / 2
                if role == "base":
                    description_end = found[1].x0
        page = lines[index].page
        for line in lines[index + 1 :]:
            if line.page != page or _is_table_end(line):
                break
            code = next((w for w in line.words if _CODE_RE.fullmatch(w.text)), None)
            description = [
                w.text
                for w in line.words
                if w is not code
                and w.text != "*"
                and not _AMOUNT_RE.fullmatch(w.text)
                and w.x0 >= (code.x1 if code else 0)
                and w.x1 <= description_end
            ]
            for k, word in enumerate(line.words):
                if not _AMOUNT_RE.fullmatch(word.text) or not columns:
                    continue
                before = line.words[k - 1].text if k else ""
                after = line.words[k + 1].text if k + 1 < len(line.words) else ""
                if before.endswith("(") and after.startswith(")"):
                    continue  # quota informativa (es. C/Ditta): fuori dai totali
                role = min(columns, key=lambda r: abs(columns[r] - word.center_x))
                if role in ("trattenuta", "spettanza"):
                    entries.append(
                        {
                            "code": code.text if code else None,
                            "description": " ".join(description) or None,
                            "amount": parse_amount(word.text),
                            "entry_type": role,
                        }
                    )
        start = index + 1
    return entries


def parse_zucchetti(
    lines: list[Line],
) -> tuple[dict[str, FieldProvenance], list[dict[str, Any]]]:
    """Parse the payslip pages of a Zucchetti document.

    Parameters
    ----------
    lines : list of Line
        Text lines of the payslip pages only (attendance pages removed).

    Returns
    -------
    tuple of (dict of str to FieldProvenance, list of dict)
        Canonical fields — period, identity, totals, ``rounding`` and,
        for a 13th/14th month, ``additional_payment`` — and the entries
        of the TRATTENUTE/COMPETENZE columns.
    """
    fields: dict[str, FieldProvenance] = {}
    _header_fields(lines, fields)
    _total_fields(lines, fields)
    return fields, _entries(lines)
