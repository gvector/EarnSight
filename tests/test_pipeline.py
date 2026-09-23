import pytest
from app.services.extraction.pipeline import run_extraction
from app.services.extraction.result import DocumentStatus, ExtractionResult


def test_extraction_done_on_consistent_payslip(payslip_pdf):
    result = run_extraction(payslip_pdf)
    assert result.status == DocumentStatus.DONE
    assert result.validation.passed is True
    assert result.fields["net_pay"].value == 2250.0
    assert len(result.entries) == 2
    assert result.raw_text
    assert result.template == "generic"


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
    assert result.status == DocumentStatus.NEEDS_REVIEW
    assert result.validation.passed is False
    assert any(i.check == "net_consistency" for i in result.issues)
    assert result.fields["net_pay"].confidence <= 0.3


def test_extraction_needs_ocr_for_scans(blank_pdf):
    result = run_extraction(blank_pdf)
    assert result.status == DocumentStatus.NEEDS_OCR
    assert result.fields == {}


def test_user_correction_repairs_and_revalidates(payslip_pdf):
    result = run_extraction(payslip_pdf)
    assert result.status == DocumentStatus.DONE

    result.apply_user_correction({"net_pay": 2100.0})
    assert result.status == DocumentStatus.NEEDS_REVIEW
    assert result.fields["net_pay"].corrected is True
    assert result.fields["net_pay"].confidence == 1.0

    result.apply_user_correction({"net_pay": 2250.0})
    assert result.status == DocumentStatus.DONE
    assert result.issues == []


def test_llm_corrections_set_llm_provenance(tmp_path):
    from conftest import build_pdf

    path = tmp_path / "llm.pdf"
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
    assert result.status == DocumentStatus.NEEDS_REVIEW
    assert result.issue_fields() == ["net_pay"]

    result.apply_llm_corrections({"net_pay": 2250.0})
    field = result.fields["net_pay"]
    assert field.value == 2250.0
    assert field.source == "llm"
    assert field.confidence == 0.7
    assert result.status == DocumentStatus.DONE


def test_to_jsonb_from_jsonb_roundtrip(payslip_pdf):
    result = run_extraction(payslip_pdf)
    data = result.to_jsonb()

    assert set(data) == {"fields", "entries", "issues", "validation"}
    rebuilt = ExtractionResult.from_jsonb(data)
    assert rebuilt.fields["net_pay"].value == result.fields["net_pay"].value
    assert rebuilt.validation.passed is True

    rebuilt2 = ExtractionResult.from_jsonb(data)
    rebuilt2.revalidate()
    assert rebuilt2.status == DocumentStatus.DONE


def test_from_document_preserves_template_and_raw_text(payslip_pdf):
    """Regression: le correzioni non devono azzerare template e raw_text."""
    from app.models.payslip import PayslipDocument

    result = run_extraction(payslip_pdf)
    doc = PayslipDocument(
        extraction=result.to_jsonb(),
        template=result.template,
        raw_text=result.raw_text,
        doc_type="cedolino",
    )

    rebuilt = ExtractionResult.from_document(doc)
    assert rebuilt.template == "generic"
    assert rebuilt.raw_text == result.raw_text
    assert rebuilt.doc_type == "cedolino"

    # una correzione passa da from_document → apply_to_document senza perdite
    rebuilt.apply_user_correction({"net_pay": 2250.0})
    assert rebuilt.raw_text == result.raw_text
    assert rebuilt.template == "generic"


def test_column_values_mirror_dedicated_columns(payslip_pdf):
    from decimal import Decimal

    result = run_extraction(payslip_pdf)
    values = result.column_values()
    assert values["gross_pay"] == Decimal("2500.0")
    assert values["net_pay"] == Decimal("2250.0")
    assert values["period_month"] == 1
    assert values["period_year"] == 2026


def test_from_jsonb_handles_missing_data():
    result = ExtractionResult.from_jsonb(None)
    assert result.fields == {}
    assert result.status == DocumentStatus.PENDING


@pytest.mark.parametrize("passed,expected", [(True, "done"), (False, "needs_review")])
def test_status_from_validation(passed, expected):
    from app.services.extraction.result import status_from_validation

    assert status_from_validation(passed) == DocumentStatus(expected)


class TestCoerceCorrectionValue:
    def test_int_fields_accept_numbers(self):
        from app.services.extraction.result import coerce_correction_value

        assert coerce_correction_value("period_month", 3) == 3
        assert coerce_correction_value("period_year", "2026") == 2026
        assert coerce_correction_value("period_month", "03") == 3

    def test_numeric_fields_accept_decimal_strings(self):
        from app.services.extraction.result import coerce_correction_value

        assert coerce_correction_value("net_pay", "2250.50") == 2250.5
        assert coerce_correction_value("net_pay", 2250) == 2250.0

    def test_garbage_raises_value_error(self):
        from app.services.extraction.result import coerce_correction_value

        with pytest.raises(ValueError, match="period_month"):
            coerce_correction_value("period_month", "marzo")
        with pytest.raises(ValueError, match="net_pay"):
            coerce_correction_value("net_pay", "tante cose")
        with pytest.raises(ValueError, match="period_year"):
            coerce_correction_value("period_year", 2026.5)

    def test_text_fields_pass_through(self):
        from app.services.extraction.result import coerce_correction_value

        assert coerce_correction_value("company_name", "Acme Srl") == "Acme Srl"
