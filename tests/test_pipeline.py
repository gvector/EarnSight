from app.services.extraction.pipeline import revalidate, run_extraction


def test_extraction_done_on_consistent_payslip(payslip_pdf):
    result = run_extraction(payslip_pdf)
    assert result["status"] == "done"
    assert result["validation"]["passed"] is True
    assert result["fields"]["net_pay"]["value"] == 2250.0
    assert len(result["entries"]) == 2
    assert result["raw_text"]


def test_extraction_needs_review_on_inconsistent_payslip(tmp_path):
    from conftest import build_pdf

    path = tmp_path / "bad.pdf"
    build_pdf(
        path,
        lambda net: [
            "Compenso Lordo: 2.500,00",
            "Totale Trattenute: 250,00",
            f"Netto da pagare: {net}",
        ],
        net_value="1.900,00",
    )
    result = run_extraction(path)
    assert result["status"] == "needs_review"
    assert result["validation"]["passed"] is False
    assert any(i["check"] == "net_consistency" for i in result["issues"])
    # il campo in errore viene declassato
    assert result["fields"]["net_pay"]["confidence"] <= 0.3


def test_extraction_needs_ocr_for_scans(blank_pdf):
    result = run_extraction(blank_pdf)
    assert result["status"] == "needs_ocr"
    assert result["fields"] == {}


def test_revalidate_after_user_correction(payslip_pdf):
    result = run_extraction(payslip_pdf)
    fields = result["fields"]
    # simula una correzione utente che sistema il netto
    fields["net_pay"].update(value=2250.0, confidence=1.0, corrected=True)
    updated = revalidate(fields, result["entries"])
    assert updated["validation"]["passed"] is True
