"""Regressione sui cedolini reali in example_ced/ (solo locale, mai in git).

La cartella contiene dati personali ed è ignorata da git: senza di essa (CI)
i test vengono saltati. Le asserzioni sono invarianti, nessun valore reale
compare qui: il mese atteso viene dal nome del file (``ced_apr_26.pdf``,
``quat_giu_26.pdf`` per la quattordicesima).
"""

from pathlib import Path

import pytest
from app.services.extraction.pipeline import run_extraction

EXAMPLES = Path(__file__).resolve().parent.parent / "example_ced"
MONTHS = "gen feb mar apr mag giu lug ago set ott nov dic".split()
PDFS = sorted(EXAMPLES.glob("*.pdf")) if EXAMPLES.is_dir() else []

pytestmark = pytest.mark.skipif(not PDFS, reason="example_ced/ assente (dati reali, solo locale)")


@pytest.mark.parametrize("pdf", PDFS, ids=lambda p: p.name)
def test_real_payslip_is_extracted_cleanly(pdf):
    kind, month, year = pdf.stem.split("_")
    result = run_extraction(pdf)
    fields = {name: field.value for name, field in result.fields.items()}

    assert result.template == "zucchetti"
    assert result.status == "done"
    assert result.issues == []  # nemmeno avvisi: voci e totali combaciano
    assert fields["period_month"] == MONTHS.index(month) + 1
    assert fields["period_year"] == 2000 + int(year)
    assert fields.get("additional_payment", False) is (kind in ("quat", "tred"))
    # il cedolino è l'ultima pagina; prima, eventualmente, il foglio presenze
    assert result.pages[-1] == "cedolino"
    assert set(result.pages[:-1]) <= {"presenze"}

    earnings = sum(e.amount for e in result.entries if e.entry_type == "spettanza")
    deductions = sum(e.amount for e in result.entries if e.entry_type == "trattenuta")
    assert earnings == pytest.approx(fields["gross_pay"], abs=0.01)
    assert deductions == pytest.approx(fields["total_deductions"], abs=0.01)
    assert fields["gross_pay"] - fields["total_deductions"] + fields["rounding"] == (
        pytest.approx(fields["net_pay"], abs=0.01)
    )
