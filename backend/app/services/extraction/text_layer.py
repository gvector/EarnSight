"""Estrazione testo + layout da PDF digitali (PyMuPDF).

I cedolini forniti sono PDF digitali con layer di testo: si estraggono le parole
con le coordinate per ricostruire righe e colonne. L'OCR resta un fallback futuro
per PDF scannerizzati.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf  # PyMuPDF

_Y_TOLERANCE = 3.0
_MIN_WORDS_PER_PAGE = 20


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page: int

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Line:
    page: int
    y: float
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def has_text_layer(pdf_path: Path) -> bool:
    """True se il PDF ha un layer di testo utilizzabile (non è uno scan)."""
    doc = pymupdf.open(pdf_path)
    try:
        pages = max(len(doc), 1)
        total_words = sum(len(page.get_text("words")) for page in doc)
        return total_words / pages >= _MIN_WORDS_PER_PAGE
    finally:
        doc.close()


def extract_lines(pdf_path: Path) -> list[Line]:
    """Estrae le righe di testo raggruppando le parole per coordinata Y."""
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
