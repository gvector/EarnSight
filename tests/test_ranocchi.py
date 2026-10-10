"""Parser Ranocchi su cedolini sintetici con la geometria del modulo reale."""

import pytest
from app.services.extraction.pipeline import run_extraction
from conftest import build_zucchetti_pdf
from ranocchi_pdf import build_ranocchi_pdf


def _run(tmp_path, **kwargs):
    path = tmp_path / "ranocchi.pdf"
    build_ranocchi_pdf(path, **kwargs)
    return run_extraction(path)


def _values(result):
    return {name: field.value for name, field in result.fields.items()}


def test_ranocchi_payslip_is_done_and_harmonised(tmp_path):
    result = _run(tmp_path)
    v = _values(result)
    assert result.template == "ranocchi"
    assert result.pages == ["cedolino"]
    assert result.status == "done", result.issues
    assert result.issues == []
    assert (v["period_month"], v["period_year"]) == (12, 2025)
    assert v["company_name"] == "DITTA SINTETICA SRL"
    assert v["employer_tax_code"] == "01234567890"
    assert v["employee_code"] == "0042"
    assert v["employee_name"] == "ROSSI MARIO"
    assert v["fiscal_code"] == "RSSMRA80A01H501U"
    assert v["gross_pay"] == 2141.77
    assert v["total_deductions"] == pytest.approx(12.48 + 196.57 + 335.42 + 0.37)
    assert v["rounding"] == 0.07
    assert v["net_pay"] == 1597.0
    assert v["taxable_income"] == 1932.72
    assert v["income_tax"] == 335.42
    assert v["ytd_taxable_income"] == 19327.2
    assert v["ytd_income_tax"] == 3354.2
    assert "additional_payment" not in v


def test_entries_exclude_figurativa_and_include_grid_deductions(tmp_path):
    result = _run(tmp_path)
    entries = [(e.code, e.description, e.amount, e.entry_type) for e in result.entries]
    # niente FIGURATIVA (buoni pasto), quantità, calendario presenze né subtotali
    # (TRATTENUTE DA VOCI, ALTRE TRATTENUTE): solo voci che compongono i totali
    assert entries == [
        ("1", "RETRIBUZIONE ORDINARIA", 2037.15, "spettanza"),
        ("1001", "ASSENZE (ore)", 12.48, "trattenuta"),
        ("202", "FERIE GODUTE", 104.62, "spettanza"),
        (None, "TOTALE CONTRIBUTI", 196.57, "trattenuta"),
        (None, "TOTALE IRPEF MESE", 335.42, "trattenuta"),
        (None, "ARROTOND. PREC.", 0.37, "trattenuta"),
    ]


def test_thirteenth_month_is_an_additional_payment(tmp_path):
    result = _run(tmp_path, thirteenth=True)
    v = _values(result)
    assert v["additional_payment"] is True
    assert (v["period_month"], v["period_year"]) == (12, 2025)


def test_negative_year_end_adjustment_is_subtracted(tmp_path):
    # rimborso IRPEF a conguaglio (segno in coda, come sul modulo): il netto cresce di 52,16
    result = _run(tmp_path, conguaglio="52,16-", net="1.649,16")
    v = _values(result)
    assert result.status == "done", result.issues
    assert v["income_tax"] == 283.26
    assert ("TOTALE IRPEF CONGUAGLIO", "trattenuta", -52.16) in {
        (e.description, e.entry_type, e.amount) for e in result.entries
    }


def test_empty_box_gives_absent_field(tmp_path):
    result = _run(tmp_path, empty={"irpef"}, net="1.932,42")
    v = _values(result)
    assert result.status == "done", result.issues
    assert "taxable_income" not in v
    assert "income_tax" not in v


def test_detection_does_not_cross_templates(tmp_path):
    zucchetti = tmp_path / "z.pdf"
    build_zucchetti_pdf(zucchetti)
    assert run_extraction(zucchetti).template == "zucchetti"
    assert _run(tmp_path).template == "ranocchi"
