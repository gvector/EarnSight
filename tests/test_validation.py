import pytest
from app.services.extraction.result import DocumentStatus, FieldProvenance
from app.services.extraction.validation import run_validation


def _fields(**overrides):
    base = {
        "gross_pay": FieldProvenance(value=2500.0),
        "total_deductions": FieldProvenance(value=250.0),
        "net_pay": FieldProvenance(value=2250.0),
        "period_month": FieldProvenance(value=1),
        "period_year": FieldProvenance(value=2026),
    }
    base.update(overrides)
    return base


def _entries():
    from app.services.extraction.result import Entry

    return [
        Entry(code="101", description="Retribuzione", amount=2500.0, entry_type="spettanza"),
        Entry(code="204", description="INPS", amount=250.0, entry_type="trattenuta"),
    ]


def test_consistent_data_passes():
    report = run_validation(_fields(), _entries())
    assert report["passed"] is True
    assert report["errors"] == []


def test_net_inconsistency_is_error_with_user_action():
    report = run_validation(_fields(net_pay=FieldProvenance(value=2100.0)), _entries())
    assert report["passed"] is False
    check = next(e for e in report["errors"] if e["check"] == "net_consistency")
    assert check["field"] == "net_pay"
    assert check["action"] == "user"


def test_missing_field_suggests_llm():
    fields = _fields()
    del fields["net_pay"]
    report = run_validation(fields, _entries())
    assert report["passed"] is False
    check = next(e for e in report["errors"] if e["check"] == "missing_field")
    assert check["action"] == "llm"


def test_invalid_period_is_error():
    report = run_validation(_fields(period_month=FieldProvenance(value=13)), _entries())
    assert any(e["check"] == "period_valid" for e in report["errors"])


def test_garbage_period_produces_issue_not_exception():
    # input non numerico arrivato chissà come: la validazione non esplode mai
    report = run_validation(_fields(period_month=FieldProvenance(value="marzo")), _entries())
    assert any(e["check"] == "period_valid" for e in report["errors"])


def _cu_fields(**overrides):
    fields = {
        "period_year": FieldProvenance(value=2025),
        "taxable_income": FieldProvenance(value=25000.0),
        "income_tax": FieldProvenance(value=5000.0),
    }
    fields.update(overrides)
    return {k: v for k, v in fields.items() if v is not None}


def test_cu_requires_year_taxable_income_and_tax():
    assert run_validation(_cu_fields(), [], doc_type="cu")["passed"] is True
    report = run_validation(_cu_fields(taxable_income=None), [], doc_type="cu")
    assert {(e["field"], e["check"], e["action"]) for e in report["errors"]} == {
        ("taxable_income", "missing_field", "llm")
    }
    report = run_validation(_cu_fields(period_year=FieldProvenance(value=None)), [], doc_type="cu")
    assert any(
        e["check"] == "period_valid" and e["field"] == "period_year" for e in report["errors"]
    )


@pytest.mark.parametrize("taxable, tax", [(1000.0, 2000.0), (-1.0, 0.0), (1000.0, -5.0)])
def test_cu_tax_consistency(taxable, tax):
    fields = _cu_fields(
        taxable_income=FieldProvenance(value=taxable), income_tax=FieldProvenance(value=tax)
    )
    report = run_validation(fields, [], doc_type="cu")
    assert any(e["check"] == "tax_consistency" and e["action"] == "user" for e in report["errors"])


def test_entries_sum_mismatch_is_warning():
    entries = _entries()
    entries[0].amount = 2400.0
    report = run_validation(_fields(), entries)
    assert report["passed"] is True
    assert any(w["check"] == "entries_sum" for w in report["warnings"])


def test_field_provenance_correction_semantics():
    field = FieldProvenance.parsed(2100.0, source="riga cedolino")
    field.penalize()
    assert field.confidence == 0.3

    field.apply_user_correction(2250.0)
    assert field.corrected is True
    assert field.confidence == 1.0

    field.penalize()
    assert field.confidence == 1.0  # le correzioni utente non vengono declassate

    field.apply_llm_correction(2250.0)
    assert field.corrected is False
    assert field.confidence == 0.7
    assert field.source == "llm"


def test_document_status_enum_matches_db_strings():
    assert {s.value for s in DocumentStatus} == {
        "pending",
        "processing",
        "done",
        "needs_review",
        "needs_ocr",
        "failed",
    }


def test_rounding_closes_the_net_equation():
    """Zucchetti: lordo − trattenute + arrotondamento = netto (2500 − 250 + 0,40)."""
    fields = _fields(net_pay=FieldProvenance(value=2250.40), rounding=FieldProvenance(value=0.40))
    report = run_validation(fields, _entries())
    assert report["passed"] is True, report["errors"]


def test_rounding_mismatch_is_still_an_error():
    fields = _fields(net_pay=FieldProvenance(value=2251.00), rounding=FieldProvenance(value=0.40))
    report = run_validation(fields, _entries())
    check = next(e for e in report["errors"] if e["check"] == "net_consistency")
    assert "arrotondamento" in check["message"]
