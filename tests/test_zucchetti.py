"""Parser Zucchetti su cedolini sintetici con il layout reale (dati inventati).

Casi del layout reale: etichette con «s» al posto degli spazi, valori sotto o a
destra dell'etichetta, foglio presenze come pagina 1 (con un periodo diverso),
arrotondamento nel netto, mensilità aggiuntiva («AGG.»).
"""

import pytest
from app.services.extraction.pipeline import run_extraction
from conftest import ZUCCHETTI_ENTRIES, build_zucchetti_pdf


@pytest.fixture
def zucchetti_pdf(tmp_path):
    path = tmp_path / "zucchetti.pdf"
    build_zucchetti_pdf(path)
    return path


def _values(result):
    return {name: field.value for name, field in result.fields.items()}


def test_single_page_payslip_is_fully_extracted(zucchetti_pdf):
    result = run_extraction(zucchetti_pdf)
    assert result.template == "zucchetti"
    assert result.pages == ["cedolino"]
    assert _values(result) == {
        "period_month": 4,
        "period_year": 2026,
        "company_name": "AZIENDA ESEMPIO S.P.A.",
        "employee_name": "ROSSI MARIO",
        "employee_code": "0000123",
        "fiscal_code": "RSSMRA80A01H501U",
        "gross_pay": 2005.0,
        "total_deductions": 434.66,
        "rounding": 0.66,
        "net_pay": 1571.0,
        "taxable_income": 1820.74,
        "income_tax": 250.0,
        "ytd_taxable_income": 8950.0,
        "ytd_income_tax": 1234.0,
        "employer_tax_code": "01234567890",
    }
    assert result.status == "done", result.issues
    assert result.issues == []


def test_entries_follow_the_trattenute_competenze_columns(zucchetti_pdf):
    entries = run_extraction(zucchetti_pdf).entries
    got = [(e.code, e.description, e.entry_type, e.amount) for e in entries]
    assert got == [
        ("000014", "Retribuzione", "spettanza", 2000.0),
        ("001201", "Ente Bilaterale Commercio", "spettanza", 5.0),
        ("ZP9960", "Arrotond. mese pr.", "trattenuta", 0.40),
        ("Z00000", "Contributo IVS", "trattenuta", 184.26),
        ("F03020", "Ritenute IRPEF", "trattenuta", 250.0),
    ]  # F02000 (solo importo base) e 002400 C/Ditta (tra parentesi) non sono voci


def test_attendance_page_is_tracked_and_ignored(tmp_path):
    path = tmp_path / "due_pagine.pdf"
    build_zucchetti_pdf(path, period="Aprile 2026", attendance_period="Marzo 2026")
    result = run_extraction(path)
    assert result.pages == ["presenze", "cedolino"]
    # il periodo viene dal cedolino, non dal foglio presenze (mese delle variabili)
    assert (result.fields["period_month"].value, result.fields["period_year"].value) == (4, 2026)
    assert result.status == "done", result.issues


def test_additional_month_is_flagged(tmp_path):
    path = tmp_path / "quattordicesima.pdf"
    build_zucchetti_pdf(path, period="Giugno 2026 AGG.")
    result = run_extraction(path)
    assert result.fields["period_month"].value == 6
    assert result.fields["additional_payment"].value is True
    assert result.status == "done", result.issues


def test_regular_month_has_no_additional_flag(zucchetti_pdf):
    assert "additional_payment" not in run_extraction(zucchetti_pdf).fields


def test_entry_spelled_arrotondamento_does_not_hijack_the_rounding_total(tmp_path):
    """I totali si cercano dopo la tabella voci: una voce «ARROTONDAMENTO» non li tocca."""
    entries = [
        ("ZP9960", "ARROTONDAMENTO", None, None, "0,40", None) if e[0] == "ZP9960" else e
        for e in ZUCCHETTI_ENTRIES
    ]
    path = tmp_path / "voce_arrotondamento.pdf"
    build_zucchetti_pdf(path, entries=entries)
    result = run_extraction(path)
    assert result.fields["rounding"].value == 0.66
    assert result.status == "done", result.issues


def test_codeless_row_starting_with_conguaglio_does_not_end_the_table(tmp_path):
    entries = list(ZUCCHETTI_ENTRIES)
    entries.insert(-1, (None, "Conguaglio anno precedente", "12,34", None, None, None))
    path = tmp_path / "riga_conguaglio.pdf"
    build_zucchetti_pdf(path, entries=entries)
    codes = [e.code for e in run_extraction(path).entries]
    assert "F03020" in codes  # la riga dopo «Conguaglio …» è ancora letta


@pytest.mark.parametrize("rounding", ["-0,66", "0,66-", "- 0,66"])
def test_negative_rounding(tmp_path, rounding):
    path = tmp_path / "arrotondamento_negativo.pdf"
    build_zucchetti_pdf(path, rounding=rounding, net="1.569,68")  # 2.005 − 434,66 − 0,66
    result = run_extraction(path)
    assert result.fields["rounding"].value == -0.66
    assert result.status == "done", result.issues


def test_document_list_exposes_additional_payment(client, tmp_path, monkeypatch):
    """La lista documenti distingue la 14ª da un mensile dello stesso mese."""
    from app.workers.tasks import process_document
    from conftest import TEST_PASSWORD

    def broken_delay(*args, **kwargs):
        raise RuntimeError("broker non raggiungibile")

    monkeypatch.setattr(process_document, "delay", broken_delay)
    token = client.post(
        "/api/auth/login", json={"username": "admin", "password": TEST_PASSWORD}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    cases = [("giugno.pdf", "Giugno 2026"), ("quattordicesima.pdf", "Giugno 2026 AGG.")]
    for name, period in cases:
        path = tmp_path / name
        build_zucchetti_pdf(path, period=period)
        with open(path, "rb") as fh:
            assert (
                client.post(
                    "/api/payslips/upload", headers=headers, files={"file": (name, fh)}
                ).status_code
                == 201
            )
    flags = {
        d["filename"]: d["additional_payment"]
        for d in client.get("/api/payslips", headers=headers).json()
    }
    assert flags == {"giugno.pdf": False, "quattordicesima.pdf": True}


def test_fiscal_fields(zucchetti_pdf):
    v = _values(run_extraction(zucchetti_pdf))
    assert v["taxable_income"] == 1820.74
    assert v["income_tax"] == 250.0
    assert v["ytd_taxable_income"] == 8950.0
    assert v["ytd_income_tax"] == 1234.0
    assert v["employer_tax_code"] == "01234567890"  # quello dell'azienda, non del dipendente


def test_taxable_income_sums_every_imponibile_row(tmp_path):
    entries = [*ZUCCHETTI_ENTRIES, ("F02010", "Imponibile Tass.aut.", "100,00", None, None, None)]
    path = tmp_path / "z.pdf"
    build_zucchetti_pdf(path, entries=entries)
    assert _values(run_extraction(path))["taxable_income"] == 1920.74


def test_fiscal_fields_absent_without_rows(tmp_path):
    entries = [e for e in ZUCCHETTI_ENTRIES if "IRPEF" not in e[1]]
    path = tmp_path / "z.pdf"
    build_zucchetti_pdf(path, entries=entries, rounding="0,66", net="1.821,00", deductions="184,66")
    v = _values(run_extraction(path))
    assert "taxable_income" not in v and "income_tax" not in v
