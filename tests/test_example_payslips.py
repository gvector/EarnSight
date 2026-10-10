"""Regressione sui cedolini reali in example_ced/ (solo locale, mai in git).

La cartella contiene dati personali ed è ignorata da git: senza di essa (CI)
i test vengono saltati. Le asserzioni sono invarianti, nessun valore reale
compare qui: il mese atteso viene dal nome del file (``ced_apr_26.pdf``,
``quat_giu_26.pdf`` per la quattordicesima, ``tred_dic_25.pdf`` per la
tredicesima), ``unico_<aa>.pdf`` è una CU.
"""

from pathlib import Path

import pytest
from app.services.extraction.pipeline import run_extraction

EXAMPLES = Path(__file__).resolve().parent.parent / "example_ced"
MONTHS = "gen feb mar apr mag giu lug ago set ott nov dic".split()
PDFS = sorted(EXAMPLES.glob("*.pdf")) if EXAMPLES.is_dir() else []
PAYSLIPS = [p for p in PDFS if not p.stem.startswith("unico")]
CUS = [p for p in PDFS if p.stem.startswith("unico")]
TEMPLATE_BY_YEAR = {2025: "ranocchi", 2026: "zucchetti"}  # datore precedente / attuale
FISCAL_FIELDS = (
    "taxable_income",
    "income_tax",
    "ytd_taxable_income",
    "ytd_income_tax",
    "employer_tax_code",
)

pytestmark = pytest.mark.skipif(not PDFS, reason="example_ced/ assente (dati reali, solo locale)")


def _fields(result):
    return {name: field.value for name, field in result.fields.items()}


@pytest.mark.parametrize("pdf", PAYSLIPS, ids=lambda p: p.name)
def test_real_payslip_is_extracted_cleanly(pdf):
    kind, month, year = pdf.stem.split("_")
    result = run_extraction(pdf)
    fields = _fields(result)

    assert result.template == TEMPLATE_BY_YEAR[2000 + int(year)]
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
    for name in FISCAL_FIELDS:
        assert name in fields, name


def _chains():
    """Cedolini per (datore, anno), ordinati per progressivo dell'imponibile: (file, campi)."""
    chains = {}
    for pdf in PAYSLIPS:
        fields = _fields(run_extraction(pdf))
        key = (fields["employer_tax_code"], fields["period_year"])
        chains.setdefault(key, []).append((pdf.stem, fields))
    return {
        key: sorted(chain, key=lambda c: c[1]["ytd_taxable_income"])
        for key, chain in chains.items()
    }


def _close(a, b):
    # confronto booleano: un fallimento non deve stampare importi reali
    return abs(a - b) < 0.01


def test_year_to_date_grows_by_each_month():
    pairs = 0
    for chain in _chains().values():
        ordinary = {f["period_month"] for _, f in chain if not f.get("additional_payment")}
        for (prev_name, prev), (name, cur) in zip(chain, chain[1:], strict=False):
            months = range(prev["period_month"], cur["period_month"] + 1)
            if not set(months) <= ordinary:  # manca un mese ordinario nel set
                continue
            pairs += 1
            step = f"{prev_name} -> {name}"
            assert _close(
                cur["ytd_taxable_income"] - prev["ytd_taxable_income"], cur["taxable_income"]
            ), step
            assert _close(cur["ytd_income_tax"] - prev["ytd_income_tax"], cur["income_tax"]), step
    assert pairs >= 5  # il confronto deve aver girato davvero


@pytest.mark.parametrize("pdf", CUS, ids=lambda p: p.name)
def test_real_cu_matches_last_payslip_of_the_year(pdf):
    result = run_extraction(pdf, doc_type="cu")
    cu = _fields(result)
    assert result.status == "done", [i.check for i in result.issues]
    assert result.issues == []
    assert set(result.pages) == {"cu", "copia"}
    assert result.pages.index("copia") > 0  # prima l'originale, poi la copia
    last_name, last = _chains()[(cu["employer_tax_code"], cu["period_year"])][-1]
    assert _close(cu["taxable_income"], last["ytd_taxable_income"]), last_name
    assert _close(cu["income_tax"], last["ytd_income_tax"]), last_name
