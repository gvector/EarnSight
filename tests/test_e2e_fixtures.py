"""I PDF di prova degli E2E (frontend/e2e/fixtures) restano coerenti con i parser.

Sono binari committati: se il parser o il generatore sintetico cambiano, qui si
vede subito (in CI, job Python) invece che come un E2E rosso difficile da leggere.
Rigenerazione: .venv/bin/python frontend/e2e/make_fixtures.py
"""

from pathlib import Path

import pytest
from app.services.extraction.pipeline import run_extraction

FIXTURES = Path(__file__).resolve().parent.parent / "frontend" / "e2e" / "fixtures"


@pytest.mark.parametrize(
    ("name", "status", "month", "additional", "pages"),
    [
        ("cedolino-aprile.pdf", "done", 4, False, ["presenze", "cedolino"]),
        ("cedolino-maggio-incoerente.pdf", "needs_review", 5, False, ["cedolino"]),
        ("quattordicesima-giugno.pdf", "done", 6, True, ["cedolino"]),
    ],
)
def test_e2e_fixture_matches_expectations(name, status, month, additional, pages):
    result = run_extraction(FIXTURES / name)
    assert result.status == status
    assert result.fields["period_month"].value == month
    assert ("additional_payment" in result.fields) is additional
    assert result.pages == pages
    assert result.fields["gross_pay"].value == 2005.0  # gli E2E si aspettano questi totali


def test_fake_pdf_fixture_is_not_a_pdf():
    assert not (FIXTURES / "non-un-pdf.pdf").read_bytes().startswith(b"%PDF")
