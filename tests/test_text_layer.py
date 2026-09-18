from app.services.extraction.text_layer import extract_lines, has_text_layer


def test_digital_pdf_has_text_layer(payslip_pdf):
    assert has_text_layer(payslip_pdf) is True


def test_blank_pdf_has_no_text_layer(blank_pdf):
    assert has_text_layer(blank_pdf) is False


def test_extract_lines_reconstructs_rows(payslip_pdf):
    lines = extract_lines(payslip_pdf)
    texts = [line.text for line in lines]
    assert any("Codice Fiscale: RSSMRA80A01H501U" in t for t in texts)
    assert any("Periodo di paga: 01/2026" in t for t in texts)
    assert any("Spettanze Trattenute" in t for t in texts)
