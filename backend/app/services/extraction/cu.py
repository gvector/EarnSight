"""Parser for the CU (Certificazione Unica) on the ministerial form.

The CU is the Italian annual income certificate, printed on the official
ministerial form: every value sits in a numbered box ("punto"), with the
point label above it (Futura), the point number in a 5 pt font at the
box's left edge and the value in Courier on the same visual line, to the
right of the number and before the next point number. The parser reads
the values by geometry, not by label text: the same point number recurs in
other sections, so each point is found through its section heading and its
label.

Fields: ``period_year`` (after "RELATIVA ALL'ANNO"), ``taxable_income``
(point 1 of DATI FISCALI, employee income), ``income_tax`` (point 21,
IRPEF withheld) and ``employer_tax_code`` (the employer's box on page 1).
An empty point gives an absent field, never an invented zero.

The PDF bundles the original for the recipient, unheaded instruction and
choice pages, and a copy headed "COPIA PER IL PERCIPIENTE":
``classify_cu_pages`` tags the copy pages ``copia`` so the pipeline parses
the original only. Known limitation: one employer per CU.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.extraction.parser import AMOUNT_PATTERN, parse_amount
from app.services.extraction.result import FieldProvenance
from app.services.extraction.text_layer import Line, Word

# "Anno 2024", "Anno di riferimento: 2024", "Anno/Periodo d'imposta 2024",
# "RELATIVA ALL’ANNO 2024" (anche con apostrofo tipografico, come esce spesso
# dal text layer).
_CU_YEAR_RE = re.compile(
    r"(?i:\b(?:anno|periodo)(?:\s+(?:di\s+|d['’]\s*)?(?:riferimento|imposta))?\s*:?\s*)(\d{4})"
)
_COPY_HEADER = "copia per il percipiente"
# L'intestazione «COPIA PER IL PERCIPIENTE» sta in cima alla pagina.
_HEADER_BAND = 30.0
_TAX_CODE_RE = re.compile(r"^\d{11}$")
_AMOUNT_RE = re.compile(rf"^{AMOUNT_PATTERN}$")
_POINTS = {
    # campo → punti da sommare: (pagina con l'intestazione, etichetta sopra il punto, numero).
    # Il reddito di lavoro dipendente è diviso fra contratto a tempo indeterminato
    # (punto 1) e determinato (punto 2): l'imponibile è la loro somma.
    "taxable_income": (
        ("dati fiscali", "a tempo indeterminato", "1"),
        ("dati fiscali", "a tempo determinato", "2"),
    ),
    "income_tax": (("dati fiscali", "ritenute irpef", "21"),),
}


def classify_cu_pages(lines: list[Line], page_count: int) -> list[str]:
    """Assign a role to every CU page: ``copia`` or ``cu``.

    Pages headed «COPIA PER IL PERCIPIENTE» (the phrase on a line within
    ``_HEADER_BAND`` points of the top) are the recipient's copy and get
    ``copia``; every other page — the original, the instructions and the
    choice forms — gets ``cu``. Only ``cu`` pages are parsed.

    Parameters
    ----------
    lines : list of Line
        All the extracted lines of the PDF.
    page_count : int
        Number of pages of the PDF, including pages without text.

    Returns
    -------
    list of str
        One role per page, in page order.

    Examples
    --------
    >>> from app.services.extraction.text_layer import Line, Word
    >>> header = Line(page=1, y=9.9, words=[
    ...     Word("COPIA", 372.0, 9.9, 390.0, 15.0, 1),
    ...     Word("PER", 392.0, 9.9, 402.0, 15.0, 1),
    ...     Word("IL", 404.0, 9.9, 408.0, 15.0, 1),
    ...     Word("PERCIPIENTE", 410.0, 9.9, 450.0, 15.0, 1),
    ... ])
    >>> classify_cu_pages([header], 2)
    ['cu', 'copia']
    """
    roles = ["cu"] * page_count
    for line in lines:
        if line.y < _HEADER_BAND and _COPY_HEADER in line.text.lower():
            roles[line.page] = "copia"
    return roles


def _label_x0(line: Line, label: str) -> float | None:
    """Return the left edge of ``label`` in a line, if the line contains it.

    Parameters
    ----------
    line : Line
        Candidate line.
    label : str
        Lower-case label, matched word by word.

    Returns
    -------
    float or None
        ``x0`` of the label's first word, or None when absent.
    """
    target = label.split()
    texts = [w.text.lower() for w in line.words]
    for i in range(len(texts) - len(target) + 1):
        if texts[i : i + len(target)] == target:
            return line.words[i].x0
    return None


def _overlaps(word: Word, number: Word) -> bool:
    """Tell whether a word sits on the same visual line as a point number.

    The 10 pt value and the 5 pt number have different boxes (different
    fonts, offset baselines): they are on the same line when at least half
    of the number's height overlaps the word's.

    Parameters
    ----------
    word : Word
        Candidate value word.
    number : Word
        Point-number word.

    Returns
    -------
    bool
        True when the vertical overlap covers half the number's height.
    """
    overlap = min(word.y1, number.y1) - max(word.y0, number.y0)
    return overlap >= (number.y1 - number.y0) / 2


def _point_value(
    lines: list[Line], section: str, label: str, number: str
) -> tuple[float, str] | None:
    """Read the amount of a numbered point of the CU.

    The point is located in three steps: the first page whose text holds
    the ``section`` heading; on it, the point-number word equal to
    ``number`` lying 4–20 pt below a line containing ``label``, with the
    label inside the number's box (from the number's left edge, 8 pt of
    slack, to the next point number on the row). The value is the amount
    on the number's visual line, right of the number and left of the next
    point number.

    Parameters
    ----------
    lines : list of Line
        Lines of the ``cu`` pages.
    section : str
        Lower-case section heading, e.g. ``"dati fiscali"``.
    label : str
        Lower-case point label printed above the number.
    number : str
        Point number, e.g. ``"21"``.

    Returns
    -------
    tuple of (float, str) or None
        The parsed amount and its raw text, or None when the point is
        missing or empty.

    Examples
    --------
    >>> _point_value([], "dati fiscali", "ritenute irpef", "21") is None
    True
    """
    page = next((ln.page for ln in lines if section in ln.text.lower()), None)
    if page is None:
        return None
    page_lines = [ln for ln in lines if ln.page == page]
    words = [w for ln in page_lines for w in ln.words]
    labels = [(ln.y, x0) for ln in page_lines if (x0 := _label_x0(ln, label)) is not None]
    for word in words:
        if word.text != number:
            continue
        # il punto successivo: numero puro sulla stessa riga dei numeri di punto
        next_x0 = min(
            (
                w.x0
                for w in words
                if w.text.isdigit()
                and w.x0 > word.x1
                and abs(w.y0 - word.y0) < 1.5
                and abs(w.y1 - word.y1) < 1.5
            ),
            default=float("inf"),
        )
        if not any(4 <= word.y0 - y <= 20 and word.x0 - 8 <= x0 < next_x0 for y, x0 in labels):
            continue
        values = sorted(
            (
                w
                for w in words
                if _AMOUNT_RE.match(w.text)
                and w.x0 > word.x1
                and w.x1 < next_x0
                and _overlaps(w, word)
            ),
            key=lambda w: w.x0,
        )
        # punto vuoto: campo assente, mai uno zero inventato
        if values:
            return parse_amount(values[0].text), values[0].text
    return None


def _employer_tax_code(lines: list[Line]) -> str | None:
    """Return the employer's tax code from the first page of the CU.

    The employer's box comes first on page 1: its «Codice fiscale» label is
    the first one in reading order, and the 11-digit code sits within 14 pt
    below it, aligned with the label (the recipient's 16-character code
    never matches).

    Parameters
    ----------
    lines : list of Line
        Lines of the ``cu`` pages.

    Returns
    -------
    str or None
        The 11-digit tax code, or None when not found.

    Examples
    --------
    >>> _employer_tax_code([]) is None
    True
    """
    if not lines:
        return None
    first_page = [ln for ln in lines if ln.page == lines[0].page]
    label = next(
        ((ln.y, x0) for ln in first_page if (x0 := _label_x0(ln, "codice fiscale")) is not None),
        None,
    )
    if label is None:
        return None
    label_y, label_x0 = label
    for ln in first_page:
        for word in ln.words:
            if (
                _TAX_CODE_RE.match(word.text)
                and 0 < word.y0 - label_y <= 14
                and abs(word.x0 - label_x0) < 20
            ):
                return word.text
    return None


def parse_cu(lines: list[Line]) -> tuple[dict[str, FieldProvenance], list[dict[str, Any]]]:
    """Parse the fiscal fields of a CU from the lines of its ``cu`` pages.

    The reference year comes from the first line matching ``_CU_YEAR_RE``
    ("RELATIVA ALL'ANNO 2025" on the form); taxable income and IRPEF
    withheld are read from DATI FISCALI (``_point_value``): taxable income
    is the sum of points 1 and 2 (employment under a permanent and a
    fixed-term contract), IRPEF withheld is point 21; the employer's tax
    code comes from page 1. A field whose points are all missing or empty
    is left out.

    Parameters
    ----------
    lines : list of Line
        Text lines with layout info of the ``cu`` pages, as produced by
        ``text_layer.extract_lines`` and filtered by ``classify_cu_pages``.

    Returns
    -------
    tuple of (dict of str to FieldProvenance, list of dict)
        The fields dict (``period_year``, ``taxable_income``,
        ``income_tax``, ``employer_tax_code`` when found) and an empty
        entries list: the CU has no payslip entries.

    Dependencies
    -----------
    - parser.AMOUNT_PATTERN, parser.parse_amount : shared Italian amount
      pattern and float conversion.
    - result.FieldProvenance : field provenance shape.
    - text_layer.Line, text_layer.Word : input types with word coordinates.

    Examples
    --------
    >>> from app.services.extraction.text_layer import Line, Word
    >>> line = Line(page=0, y=70.0, words=[
    ...     Word("RELATIVA", 300.0, 70.0, 330.0, 76.0, 0),
    ...     Word("ALL’ANNO", 332.0, 70.0, 360.0, 76.0, 0),
    ...     Word("2025", 362.0, 70.0, 376.0, 76.0, 0),
    ... ])
    >>> fields, entries = parse_cu([line])
    >>> fields["period_year"].value
    2025
    >>> entries
    []
    """
    fields: dict[str, FieldProvenance] = {}
    for line in lines:
        if match := _CU_YEAR_RE.search(line.text):
            fields["period_year"] = FieldProvenance.parsed(int(match.group(1)), line.text)
            break
    for name, points in _POINTS.items():
        found = [v for point in points if (v := _point_value(lines, *point)) is not None]
        if found:
            total = round(sum(amount for amount, _ in found), 2)
            fields[name] = FieldProvenance.parsed(total, " + ".join(text for _, text in found))
    if code := _employer_tax_code(lines):
        fields["employer_tax_code"] = FieldProvenance.parsed(code, code)
    return fields, []
