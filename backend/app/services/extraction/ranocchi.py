"""Parser for Ranocchi payslips (GIS Paghe, «Ranocchi Software»).

Layout facts this parser relies on, observed on real documents:

- a preprinted form: labels in a small sans-serif font, values stamped in
  Courier, the value right-aligned in the label's cell, a few points below
  the label; label and value never share a ``y0``, so the parser regroups
  the words into visual rows by their bottom edge and reads the values
  through label-anchored cells (from the label's left edge to the next
  label on its row);
- rotated margin text (with the software's imprint) and the attendance
  calendar, with its hour amounts, sit outside x 22–447 and are discarded
  first;
- there is no TOTALE COMPETENZE/TRATTENUTE label: the entries table ends
  with an unlabelled totals row (the sums of COMPETENZA and TRATTENUTA),
  then the ENTE-VOCE header of the bottom grid;
- contributions, IRPEF, its year-end adjustment (signed, minus sign at the
  end), regional and municipal surcharges and the previous month's rounding
  live in the bottom grid and become synthetic deduction entries, so that
  entries and totals mean what they mean on Zucchetti; TRATTENUTE DA VOCI
  and ALTRE TRATTENUTE are subtotals and are never added;
- FIGURATIVA amounts (meal vouchers, flexible benefits) are informative;
- a 13th/14th month carries ``13^ mens.`` in the MESE cell.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.extraction.parser import AMOUNT_PATTERN, parse_amount
from app.services.extraction.result import FieldProvenance
from app.services.extraction.text_layer import Line, Word
from app.services.extraction.zucchetti import MONTHS

_X_MIN, _X_MAX = 22.0, 447.0  # fuori: testo ruotato (x1 < 22,5) e calendario presenze
_ROW_TOLERANCE = 2.5  # pt fra i bordi inferiori di parole sulla stessa riga visiva
_CELL_DEPTH = 20.0  # pt sotto l'etichetta in cui cercare il valore (≈ 7–18 sul modulo)
_CONTRIBUTIONS_DEPTH = 42.0  # TOTALE CONTRIBUTI: valore sulla terza riga del riquadro
_EDGE = 6.0  # pt di tolleranza a sinistra della cella
_SIGNED_RE = re.compile(rf"^(-?)({AMOUNT_PATTERN})(-?)$")
_TAX_CODE_RE = re.compile(r"^CF:(\d{11})$")
_FISCAL_CODE_RE = re.compile(r"^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$")
_ADDITIONAL_RE = re.compile(r"^\d{2}\^$")  # «13^ mens.», «14^ mens.»

# celle della griglia in basso che diventano voci di trattenuta (etichetta stampata)
_GRID_DEDUCTIONS = (
    ("TOTALE CONTRIBUTI", _CONTRIBUTIONS_DEPTH),
    ("TOTALE IRPEF MESE", _CELL_DEPTH),
    ("TOTALE IRPEF CONGUAGLIO", _CELL_DEPTH),
    ("TOT. ADDIZIONALI", _CELL_DEPTH),
    ("ARROTOND. PREC.", _CELL_DEPTH),
)
_COLUMNS = (("spettanza", "COMPETENZA"), ("trattenuta", "TRATTENUTA"), ("figurativa", "FIGURATIVA"))

_Found = tuple[int, Word, Word]  # (indice della riga, prima parola, ultima parola)


def _rows(lines: list[Line]) -> list[Line]:
    """Words inside the form, regrouped into visual rows by their bottom edge.

    Parameters
    ----------
    lines : list of Line
        Lines of the payslip pages, as from ``extract_lines``.

    Returns
    -------
    list of Line
        Rows top to bottom (``y`` is the bottom edge of the row's first
        word), words sorted by ``x0``; margin words are dropped.
    """
    words = [w for line in lines for w in line.words if _X_MIN <= w.x0 and w.x1 <= _X_MAX]
    rows: list[Line] = []
    for word in sorted(words, key=lambda w: (w.page, w.y1, w.x0)):
        if rows and rows[-1].page == word.page and word.y1 - rows[-1].y <= _ROW_TOLERANCE:
            rows[-1].words.append(word)
        else:
            rows.append(Line(page=word.page, y=word.y1, words=[word]))
    for row in rows:
        row.words.sort(key=lambda w: w.x0)
    return rows


def _find_all(rows: list[Line], label: str) -> list[_Found]:
    """Every run of words spelling ``label`` on one row, top to bottom."""
    parts = label.split()
    found = []
    for index, row in enumerate(rows):
        texts = [w.text for w in row.words]
        for i in range(len(texts) - len(parts) + 1):
            if texts[i : i + len(parts)] == parts:
                found.append((index, row.words[i], row.words[i + len(parts) - 1]))
    return found


def _find(rows: list[Line], label: str) -> _Found | None:
    """First (top-most) occurrence of ``label``, or None."""
    return next(iter(_find_all(rows, label)), None)


def _cell(rows: list[Line], found: _Found, depth: float = _CELL_DEPTH) -> list[list[Word]]:
    """Words stamped in the label's cell, row by row.

    The cell runs from the label's left edge (minus ``_EDGE``) to the next
    word on the label's row (the neighbouring label), and down to ``depth``
    points below the label's bottom edge.

    Parameters
    ----------
    rows : list of Line
        Rows from ``_rows``.
    found : tuple of (int, Word, Word)
        The label, as returned by ``_find``.
    depth : float, optional
        Vertical extent of the cell below the label, in points.

    Returns
    -------
    list of list of Word
        The non-empty rows of the cell, top to bottom.
    """
    index, first, last = found
    label_row = rows[index]
    right = min((w.x0 for w in label_row.words if w.x0 > last.x1), default=float("inf"))
    cell = []
    for row in rows[index + 1 :]:
        if row.page != label_row.page or row.y - last.y1 > depth:
            break
        words = [w for w in row.words if w.x0 >= first.x0 - _EDGE and w.x1 <= right]
        if words:
            cell.append(words)
    return cell


def _signed(word: Word) -> float | None:
    """Signed amount of a word (minus sign before or after), or None."""
    match = _SIGNED_RE.fullmatch(word.text)
    if match is None:
        return None
    sign = -1 if (match.group(1) or match.group(3)) else 1
    return sign * parse_amount(match.group(2))


def _amount_in(
    rows: list[Line], found: _Found | None, depth: float = _CELL_DEPTH
) -> tuple[float, str] | None:
    """First signed amount in the cell of a found label: (value, printed text)."""
    for words in _cell(rows, found, depth) if found else []:
        for word in words:
            value = _signed(word)
            if value is not None:
                return value, word.text
    return None


def _cell_amount(
    rows: list[Line], label: str, depth: float = _CELL_DEPTH
) -> tuple[float, str] | None:
    """First signed amount in the cell of the top-most ``label``."""
    return _amount_in(rows, _find(rows, label), depth)


def _text(words: list[Word]) -> str:
    return " ".join(w.text for w in words)


def _header_fields(rows: list[Line], fields: dict[str, FieldProvenance]) -> None:
    """Period, company and employee identity from the top of the form.

    Parameters
    ----------
    rows : list of Line
        Rows above the entries table.
    fields : dict of str to FieldProvenance
        Filled in place.
    """
    mese = _find(rows, "MESE")
    if mese:
        cell = [w for words in _cell(rows, mese) for w in words]
        for k, word in enumerate(cell[:-1]):
            year = cell[k + 1]
            if word.text.lower() in MONTHS and year.text.isdigit() and len(year.text) == 4:
                source = _text([word, year])
                fields["period_month"] = FieldProvenance.parsed(MONTHS[word.text.lower()], source)
                fields["period_year"] = FieldProvenance.parsed(int(year.text), source)
                break
        extra = [w for w in cell if _ADDITIONAL_RE.fullmatch(w.text)]
        if extra:
            fields["additional_payment"] = FieldProvenance.parsed(True, _text(extra))

    # «CODICE» compare due volte: quello del dipendente è sulla riga di COGNOME E NOME
    codes = _find_all(rows, "CODICE")
    employee = next((c for c in codes if any(w.text == "COGNOME" for w in rows[c[0]].words)), None)
    company_code = next((c for c in codes if employee is None or c[0] < employee[0]), None)
    right = company_code[1].x0 if company_code else float("inf")
    for row in rows[: employee[0] if employee else len(rows)]:
        # ragione sociale: la prima riga in alto a sinistra, senza etichetta
        words = [w for w in row.words if w.x1 < right]
        if words:
            fields["company_name"] = FieldProvenance.parsed(_text(words), _text(words))
            break
    tax_code = next(
        (m for row in rows for w in row.words if (m := _TAX_CODE_RE.fullmatch(w.text))), None
    )
    if tax_code:
        fields["employer_tax_code"] = FieldProvenance.parsed(tax_code.group(1), tax_code.group(0))

    if employee:
        cell = [w for words in _cell(rows, employee) for w in words]
        code = next((w for w in cell if w.text.isdigit()), None)
        if code:
            fields["employee_code"] = FieldProvenance.parsed(code.text, code.text)
    name = _find(rows, "COGNOME E NOME")
    cell = _cell(rows, name) if name else []
    if cell:
        fields["employee_name"] = FieldProvenance.parsed(_text(cell[0]), _text(cell[0]))
    fiscal = _find(rows, "COD. FISC.")
    if fiscal:
        # stessa riga visiva dell'etichetta (il valore sporge di ~3 pt sopra)
        for word in rows[fiscal[0]].words:
            if word.x0 > fiscal[2].x1 and _FISCAL_CODE_RE.fullmatch(word.text):
                fields["fiscal_code"] = FieldProvenance.parsed(word.text, word.text)
                break


def _grid_fields(rows: list[Line], fields: dict[str, FieldProvenance]) -> None:
    """Net pay, rounding and the IRPEF fields from the bottom grid.

    ``income_tax`` is TOTALE IRPEF MESE plus the signed TOTALE IRPEF
    CONGUAGLIO; the monthly and year-to-date IMPONIBILE IRPEF are told
    apart by the row they share with TOTALE IRPEF MESE and IRPEF PAGATA.

    Parameters
    ----------
    rows : list of Line
        Rows of the bottom grid (from ENTE-VOCE down).
    fields : dict of str to FieldProvenance
        Filled in place.
    """
    for name, label in (("net_pay", "NETTO"), ("rounding", "ARROTOND. ATT.")):
        found = _cell_amount(rows, label)
        if found:
            fields[name] = FieldProvenance.parsed(found[0], found[1])

    taxable = _find_all(rows, "IMPONIBILE IRPEF")
    for name, anchor in (
        ("taxable_income", "TOTALE IRPEF MESE"),
        ("ytd_taxable_income", "IRPEF PAGATA"),
    ):
        row = _find(rows, anchor)
        label = next((t for t in taxable if row and t[0] == row[0]), None)
        amount = _amount_in(rows, label)
        if amount:
            fields[name] = FieldProvenance.parsed(amount[0], amount[1])

    month = _cell_amount(rows, "TOTALE IRPEF MESE")
    if month:
        adjustment = _cell_amount(rows, "TOTALE IRPEF CONGUAGLIO")
        value = month[0] + (adjustment[0] if adjustment else 0.0)
        source = month[1] + (f" + {adjustment[1]}" if adjustment else "")
        fields["income_tax"] = FieldProvenance.parsed(round(value, 2), source)
    paid = _cell_amount(rows, "IRPEF PAGATA")
    if paid:
        fields["ytd_income_tax"] = FieldProvenance.parsed(paid[0], paid[1])


def _table(rows: list[Line]) -> tuple[list[dict[str, Any]], dict[str, tuple[float, str]]]:
    """Entries of the COMPETENZA/TRATTENUTA columns and the printed totals row.

    Each amount goes to the column whose header it ends under: from the
    header's left edge to the next header (values are right-aligned past
    their header). Amounts elsewhere (quantity, base) are not entries and
    FIGURATIVA amounts are informative. The row with amounts but neither
    code nor description is the unlabelled totals row.

    Parameters
    ----------
    rows : list of Line
        Rows from the table header to the bottom grid (excluded).

    Returns
    -------
    tuple of (list of dict, dict of str to tuple of (float, str))
        The entries, and the printed totals by role (``spettanza``,
        ``trattenuta``) as (value, text).
    """
    header = _find(rows, "COMPETENZA")
    voce = _find(rows, "VOCE")
    described = _find(rows, "DESCRIZIONE")
    if header is None or voce is None or described is None:
        return [], {}
    header_words = rows[header[0]].words
    columns: dict[str, tuple[float, float]] = {}  # ruolo → (x0 intestazione, x0 successiva]
    for role, label in _COLUMNS:
        word = next((w for w in header_words if w.text == label), None)
        if word:
            right = min((w.x0 for w in header_words if w.x0 > word.x1), default=float("inf"))
            columns[role] = (word.x0, right)
    code_end = voce[2].x1 + _EDGE  # codice voce allineato a destra sotto VOCE
    description_end = min(
        (w.x0 for w in header_words if w.x0 > described[2].x1), default=float("inf")
    )

    entries: list[dict[str, Any]] = []
    totals: dict[str, tuple[float, str]] = {}
    for row in rows[header[0] + 1 :]:
        amounts = []
        for word in row.words:
            value = _signed(word)
            role = next((r for r, (x0, x1) in columns.items() if x0 < word.x1 <= x1), None)
            if value is not None and role:
                amounts.append((role, value, word.text))
        if not amounts:
            continue
        code = next((w for w in row.words if w.text.isdigit() and w.x1 <= code_end), None)
        description = [
            w
            for w in row.words
            if w.x0 >= voce[2].x1 and w.x1 <= description_end and _signed(w) is None
        ]
        if code is None and not description:
            totals = {role: (value, text) for role, value, text in amounts}
            continue
        for role, value, _ in amounts:
            if role != "figurativa":  # buoni pasto, flexible benefit: fuori dai totali
                entries.append(
                    {
                        "code": code.text if code else None,
                        "description": _text(description) or None,
                        "amount": value,
                        "entry_type": role,
                    }
                )
    return entries, totals


def parse_ranocchi(
    lines: list[Line],
) -> tuple[dict[str, FieldProvenance], list[dict[str, Any]]]:
    """Parse the payslip pages of a Ranocchi document.

    Parameters
    ----------
    lines : list of Line
        Text lines of the payslip pages.

    Returns
    -------
    tuple of (dict of str to FieldProvenance, list of dict)
        Canonical fields — period, identity, ``employer_tax_code``, totals,
        ``rounding``, the IRPEF fields (``taxable_income``, ``income_tax``,
        ``ytd_taxable_income``, ``ytd_income_tax``) and, for a 13th/14th
        month, ``additional_payment`` — and the entries: the table's
        COMPETENZA/TRATTENUTA amounts plus one deduction per filled
        bottom-grid box (contributions, IRPEF, adjustment, surcharges,
        previous rounding), so that they add up to the totals.
        ``gross_pay`` and the table part of ``total_deductions`` come from
        the printed totals row when present (the entries are then a real
        cross-check), from the entries otherwise.
    """
    rows = _rows(lines)
    table = _find(rows, "COMPETENZA")
    grid = _find(rows, "ENTE-VOCE")
    table_start = table[0] if table else len(rows)
    grid_start = grid[0] if grid else len(rows)
    top, body, bottom = rows[:table_start], rows[table_start:grid_start], rows[grid_start:]

    fields: dict[str, FieldProvenance] = {}
    _header_fields(top, fields)
    _grid_fields(bottom, fields)
    entries, printed = _table(body)
    grid = []  # (voce, testo stampato) per ogni riquadro valorizzato
    for label, depth in _GRID_DEDUCTIONS:
        found = _cell_amount(bottom, label, depth)
        if found:
            entry = {"code": None, "description": label, "amount": found[0]}
            grid.append(({**entry, "entry_type": "trattenuta"}, f"{label} {found[1]}"))

    if entries or grid:
        for name, role, column in (
            ("gross_pay", "spettanza", "COMPETENZA"),
            ("total_deductions", "trattenuta", "TRATTENUTA"),
        ):
            # la riga dei totali stampata vince sulla somma delle voci
            value, source = printed.get(role) or (
                sum(e["amount"] for e in entries if e["entry_type"] == role),
                f"Σ {column}",
            )
            if role == "trattenuta":
                value += sum(entry["amount"] for entry, _ in grid)
                source = " + ".join([source, *(text for _, text in grid)])
            fields[name] = FieldProvenance.parsed(round(value, 2), source)
    return fields, entries + [entry for entry, _ in grid]
