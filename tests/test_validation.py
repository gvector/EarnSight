from app.services.extraction.validation import run_validation


def _fields(**overrides):
    base = {
        "gross_pay": {"value": 2500.0, "confidence": 0.9, "corrected": False},
        "total_deductions": {"value": 250.0, "confidence": 0.9, "corrected": False},
        "net_pay": {"value": 2250.0, "confidence": 0.9, "corrected": False},
        "period_month": {"value": 1, "confidence": 0.9, "corrected": False},
        "period_year": {"value": 2026, "confidence": 0.9, "corrected": False},
    }
    base.update(overrides)
    return base


def _entries():
    return [
        {"code": "101", "description": "Retribuzione", "amount": 2500.0, "entry_type": "spettanza"},
        {"code": "204", "description": "INPS", "amount": 250.0, "entry_type": "trattenuta"},
    ]


def test_consistent_data_passes():
    report = run_validation(_fields(), _entries())
    assert report["passed"] is True
    assert report["errors"] == []


def test_net_inconsistency_is_error_with_user_action():
    report = run_validation(
        _fields(net_pay={"value": 2100.0, "confidence": 0.9, "corrected": False}), _entries()
    )
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
    report = run_validation(
        _fields(period_month={"value": 13, "confidence": 0.9, "corrected": False}), _entries()
    )
    assert any(e["check"] == "period_valid" for e in report["errors"])


def test_entries_sum_mismatch_is_warning():
    entries = _entries()
    entries[0]["amount"] = 2400.0
    report = run_validation(_fields(), entries)
    assert report["passed"] is True
    assert any(w["check"] == "entries_sum" for w in report["warnings"])
