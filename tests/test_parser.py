from app.services.extraction.parser import parse_amount, parse_payslip
from app.services.extraction.templates import detect_template
from app.services.extraction.text_layer import extract_lines


def test_parse_amount_italian_format():
    assert parse_amount("1.234,56") == 1234.56
    assert parse_amount("250,00") == 250.0
    assert parse_amount("2.500,00") == 2500.0


def test_detect_template_falls_back_to_generic():
    assert detect_template("Cedolino senza firma nota") == "generic"


def test_parse_payslip_fields(payslip_pdf):
    lines = extract_lines(payslip_pdf)
    fields, _ = parse_payslip(lines)

    assert fields["fiscal_code"].value == "RSSMRA80A01H501U"
    assert fields["employee_name"].value == "ROSSI MARIO"
    assert fields["company_name"].value == "ESEMPIO SRL"
    assert fields["matricola"].value == "12345"
    assert fields["period_month"].value == 1
    assert fields["period_year"].value == 2026
    assert fields["gross_pay"].value == 2500.0
    assert fields["total_deductions"].value == 250.0
    assert fields["net_pay"].value == 2250.0
    for field in fields.values():
        assert field.confidence >= 0.9
        assert field.source
        assert field.corrected is False


def test_parse_payslip_entries_column_assignment(payslip_pdf):
    lines = extract_lines(payslip_pdf)
    _, entries = parse_payslip(lines)

    by_type = {e["entry_type"]: e for e in entries}
    assert by_type["spettanza"]["amount"] == 2500.0
    assert by_type["spettanza"]["code"] == "101"
    assert by_type["spettanza"]["description"] == "Retribuzione mensile"
    assert by_type["trattenuta"]["amount"] == 250.0
    assert by_type["trattenuta"]["description"] == "Contributo INPS"


def test_parse_payslip_missing_net(payslip_pdf):
    lines = extract_lines(payslip_pdf)
    filtered = [line for line in lines if "Netto" not in line.text]
    fields, _ = parse_payslip(filtered)
    assert "net_pay" not in fields
