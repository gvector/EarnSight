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
