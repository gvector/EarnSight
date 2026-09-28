"""Text and layout extraction from digital PDFs via PyMuPDF.

The payslips received in production are digital PDFs with an embedded text
layer: PyMuPDF exposes the words together with their bounding-box
coordinates, which this module uses to rebuild the visual lines (words
grouped by Y coordinate) and to preserve horizontal positions for
column-aware parsing. OCR remains a future fallback for scanned PDFs.

Module constants: ``_Y_TOLERANCE`` is the maximum vertical distance (in page
points) for two words to share a line; ``_MIN_WORDS_PER_PAGE`` is the
average word density below which a PDF is considered a scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf  # PyMuPDF

_Y_TOLERANCE = 3.0
_MIN_WORDS_PER_PAGE = 20


@dataclass
class Word:
    """A single word extracted from a PDF page, with its bounding box.

    PyMuPDF's ``page.get_text("words")`` yields words as
    ``(x0, y0, x1, y1, text, ...)`` tuples; this dataclass keeps the word
    geometry so that lines can be rebuilt from Y coordinates and columns
    (labels vs. amounts) can be told apart from X positions.

    Attributes
    ----------
    text : str
        The word's text content.
    x0 : float
        Left edge of the bounding box, in page points.
    y0 : float
        Top edge of the bounding box, in page points; used as the word's
        vertical position for line grouping.
    x1 : float
        Right edge of the bounding box, in page points.
    y1 : float
        Bottom edge of the bounding box, in page points.
    page : int
        Zero-based index of the page the word belongs to.

    Methods
    -------
    center_x
        Horizontal center of the bounding box, for column attribution.

    Examples
    --------
    >>> Word("lordo", x0=100.0, y0=50.0, x1=130.0, y1=58.0, page=0)
    Word(text='lordo', x0=100.0, y0=50.0, x1=130.0, y1=58.0, page=0)
    """

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page: int

    @property
    def center_x(self) -> float:
        """Horizontal center of the word's bounding box.

        Used after line reconstruction to attribute each word to a layout
        column, e.g. deciding whether an amount belongs to the
        "Spettanze" or "Trattenute" column of a payslip table.

        Returns
        -------
        float
            Midpoint between ``x0`` and ``x1``.
        """
        return (self.x0 + self.x1) / 2


@dataclass
class Line:
    """A visual line of text: words on the same page sharing a Y position.

    Rebuilt from ``Word`` coordinates by ``extract_lines``: consecutive
    words on the same page whose ``y0`` falls within ``_Y_TOLERANCE`` of
    the line's baseline are grouped together, and the words are finally
    sorted by ``x0`` so the rendered text reads left to right.

    Attributes
    ----------
    page : int
        Zero-based index of the page the line belongs to.
    y : float
        Baseline of the line (the ``y0`` of its first word), in page
        points; the reference for grouping further words.
    words : list of Word
        Words on the line, sorted by ``x0``.

    Methods
    -------
    text
        The line rendered as a single space-joined string.

    Examples
    --------
    >>> line = Line(page=0, y=50.0, words=[
    ...     Word("Netto", 0.0, 50.0, 30.0, 58.0, 0),
    ...     Word("1.500,00", 40.0, 50.0, 70.0, 58.0, 0),
    ... ])
    >>> line.text
    'Netto 1.500,00'
    """

    page: int
    y: float
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Render the line's words as one space-joined string.

        Returns
        -------
        str
            The words in ``x0`` order joined by single spaces; an empty
            string when the line holds no words. This is the text every
            label-based parser and regex operates on.
        """
        return " ".join(w.text for w in self.words)


def has_text_layer(pdf_path: Path) -> bool:
    """Check whether the PDF has a usable text layer (is not a scan).

    Counts the words on every page with PyMuPDF and compares the average
    words-per-page against ``_MIN_WORDS_PER_PAGE``: digital payslips carry
    a dense text layer, while scanned PDFs expose almost no embedded
    words. The pipeline uses this as its gate: PDFs failing the check are
    routed to the ``needs_ocr`` status instead of being parsed.

    Parameters
    ----------
    pdf_path : Path
        Path to the PDF to inspect.

    Returns
    -------
    bool
        True when the average words-per-page meets the threshold, False
        when the document looks like a scan (or is empty).

    Dependencies
    -----------
    - pymupdf : word counting per page.

    Examples
    --------
    >>> has_text_layer(Path("payslip.pdf"))
    True
    >>> has_text_layer(Path("scanned_payslip.pdf"))
    False
    """
    doc = pymupdf.open(pdf_path)
    try:
        pages = max(len(doc), 1)
        total_words = sum(len(page.get_text("words")) for page in doc)
        return total_words / pages >= _MIN_WORDS_PER_PAGE
    finally:
        doc.close()


def extract_lines(pdf_path: Path) -> list[Line]:
    """Extract the text lines of every page, grouping words by Y coordinate.

    PDF text extraction yields positioned words, not lines; this function
    rebuilds the visual reading order. Words are collected per page via
    PyMuPDF with their bounding boxes and sorted by ``(y0, x0)``; each word
    is then folded into the current line when it stays on the same page and
    its ``y0`` lies within ``_Y_TOLERANCE`` of that line's baseline,
    otherwise a new line is started. After each page, the words of that
    page's lines are sorted by ``x0`` so labels and amounts keep their
    horizontal positions for column-aware parsing.

    Parameters
    ----------
    pdf_path : Path
        Path to the PDF to extract.

    Returns
    -------
    list of Line
        Lines in reading order: by page, then vertical position, with the
        words of each line sorted horizontally.

    Dependencies
    -----------
    - pymupdf : per-page word extraction with bounding-box coordinates.
    - text_layer.Word, text_layer.Line : geometry and line dataclasses.

    Examples
    --------
    >>> lines = extract_lines(Path("payslip.pdf"))
    >>> len(lines) > 0
    True
    """
    doc = pymupdf.open(pdf_path)
    try:
        lines: list[Line] = []
        for page_no, page in enumerate(doc):
            words = [
                Word(text=w[4], x0=w[0], y0=w[1], x1=w[2], y1=w[3], page=page_no)
                for w in page.get_text("words")
            ]
            words.sort(key=lambda w: (w.y0, w.x0))
            for word in words:
                if (
                    lines
                    and lines[-1].page == page_no
                    and abs(word.y0 - lines[-1].y) <= _Y_TOLERANCE
                ):
                    lines[-1].words.append(word)
                else:
                    lines.append(Line(page=page_no, y=word.y0, words=[word]))
            for line in lines:
                if line.page == page_no:
                    line.words.sort(key=lambda w: w.x0)
        return lines
    finally:
        doc.close()
