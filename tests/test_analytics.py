"""Motore delle schede annuali (services/analytics) su record costruiti a mano.

Funzioni pure: nessun PDF, nessun database. Importi inventati.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.services.analytics.records import CuRecord, PayslipRecord, record_from_document
from app.services.analytics.years import (
    cu_check,
    dedupe_payslips,
    last_payslip,
    missing_months,
    year_summaries,
    year_totals,
    ytd_check,
)

EMPLOYER = "01234567890"
T0 = datetime(2026, 1, 1)


def D(value):
    return None if value is None else Decimal(str(value))


def payslip(month, *, taxable=1000, tax=200, ytd=None, ytd_tax=None, additional=False,
            status="done", employer=EMPLOYER, year=2025, gross=1500, net=1100,
            deductions=400, uploaded=0, template="ranocchi"):  # fmt: skip
    """Cedolino sintetico; ``ytd`` di default: imponibile × mesi trascorsi."""
    return PayslipRecord(
        id=uuid.uuid4(),
        period_year=year,
        period_month=month,
        additional_payment=additional,
        status=status,
        employer_tax_code=employer,
        template=template,
        gross_pay=D(gross),
        net_pay=D(net),
        total_deductions=D(deductions),
        taxable_income=D(taxable),
        income_tax=D(tax),
        ytd_taxable_income=D(ytd),
        ytd_income_tax=D(ytd_tax),
        created_at=T0 + timedelta(minutes=uploaded),
    )


def cu(*, taxable=3000, tax=600, status="done", employer=EMPLOYER, year=2025, uploaded=0):
    return CuRecord(
        id=uuid.uuid4(),
        period_year=year,
        status=status,
        employer_tax_code=employer,
        taxable_income=D(taxable),
        income_tax=D(tax),
        created_at=T0 + timedelta(minutes=uploaded),
    )


def chain(months, start_ytd=0):
    """Cedolini consecutivi con progressivi coerenti (imponibile 1000, IRPEF 200 al mese)."""
    out, ytd, ytd_tax = [], start_ytd, start_ytd // 5
    for month in months:
        ytd, ytd_tax = ytd + 1000, ytd_tax + 200
        out.append(payslip(month, ytd=ytd, ytd_tax=ytd_tax))
    return out


# --- record_from_document -------------------------------------------------------------


def test_record_from_document_reads_columns_and_jsonb():
    doc = SimpleNamespace(
        id=uuid.uuid4(), doc_type="cedolino", period_year=2025, period_month=9, status="done",
        employer_tax_code=EMPLOYER, template="ranocchi", gross_pay=Decimal("1500.00"),
        net_pay=Decimal("1100.00"), total_deductions=Decimal("400.00"),
        taxable_income=Decimal("1013.00"), income_tax=Decimal("200.00"), created_at=T0,
        extraction={"fields": {"ytd_taxable_income": {"value": 9000.5},
                               "ytd_income_tax": {"value": 1800.25},
                               "additional_payment": {"value": True}}},
    )  # fmt: skip
    record = record_from_document(doc)
    assert isinstance(record, PayslipRecord)
    assert record.ytd_taxable_income == Decimal("9000.5")
    assert record.ytd_income_tax == Decimal("1800.25")
    assert record.additional_payment is True


def test_record_from_document_without_fiscal_jsonb():
    # documento caricato prima della Spec 1: niente progressivi nel JSONB
    doc = SimpleNamespace(
        id=uuid.uuid4(), doc_type="cedolino", period_year=2025, period_month=9, status="done",
        employer_tax_code=None, template="zucchetti", gross_pay=None, net_pay=None,
        total_deductions=None, taxable_income=None, income_tax=None, created_at=T0,
        extraction=None,
    )  # fmt: skip
    record = record_from_document(doc)
    assert record.ytd_taxable_income is None and record.additional_payment is False


def test_record_from_document_cu():
    doc = SimpleNamespace(
        id=uuid.uuid4(), doc_type="cu", period_year=2025, period_month=None, status="done",
        employer_tax_code=EMPLOYER, template=None, gross_pay=None, net_pay=None,
        total_deductions=None, taxable_income=Decimal("3000.00"), income_tax=Decimal("600.00"),
        created_at=T0, extraction={"fields": {}},
    )  # fmt: skip
    assert isinstance(record_from_document(doc), CuRecord)


# --- funzioni elementari ----------------------------------------------------------------


def test_dedupe_keeps_the_most_recent_upload():
    old = payslip(9, uploaded=0)
    new = payslip(9, uploaded=5)
    other = payslip(9, additional=True)  # la 13ª dello stesso mese non è un doppione
    kept, discarded = dedupe_payslips([old, new, other])
    assert set(kept) == {new, other}
    assert discarded == [old]


def test_missing_months_between_and_never_after():
    payslips = chain([3, 4, 5, 7, 8])
    payslips[0] = payslip(3, ytd=1000, ytd_tax=200)  # nessun reddito prima di marzo
    assert missing_months(payslips) == [6]


def test_missing_months_before_the_first_when_ytd_carries_earlier_income():
    assert missing_months(chain([9, 10, 11, 12], start_ytd=8000)) == [1, 2, 3, 4, 5, 6, 7, 8]


def test_additional_payments_create_no_gap():
    payslips = [*chain([5, 6]), payslip(6, additional=True, ytd=3000, ytd_tax=600)]
    payslips[0] = payslip(5, ytd=1000, ytd_tax=200)
    assert missing_months(payslips) == []


def test_only_additional_payment():
    assert missing_months([payslip(12, additional=True, ytd=1000, ytd_tax=200)]) == []


def test_last_payslip_is_the_highest_ytd_not_the_latest_month():
    ordinary_dec = payslip(12, ytd=5000, ytd_tax=1000)
    thirteenth = payslip(12, additional=True, ytd=4000, ytd_tax=800)
    november = payslip(11, ytd=3000, ytd_tax=600)
    assert last_payslip([thirteenth, ordinary_dec, november]) is ordinary_dec
    assert last_payslip([payslip(1)]) is None  # nessun progressivo


def test_year_totals_sum_present_values_only():
    totals = year_totals([payslip(1, gross=100, net=None), payslip(2, gross=50, net=None)])
    assert totals.gross_pay == Decimal("150")
    assert totals.net_pay is None


# --- completezza ------------------------------------------------------------------------


def test_ytd_check_complete():
    payslips = chain([1, 2, 3])
    result = ytd_check(payslips)
    assert result.status == "complete"
    assert result.taxable_diff == Decimal("0") and result.tax_diff == Decimal("0")


def test_ytd_check_incomplete_reports_the_income_not_loaded():
    result = ytd_check(chain([9, 10], start_ytd=8000))
    assert result.status == "incomplete"
    assert result.taxable_diff == Decimal("8000")
    assert result.tax_diff == Decimal("1600")


def test_missing_ytd_gives_no_fiscal_data():
    assert ytd_check([payslip(1), payslip(2)]).status == "no_fiscal_data"
    assert ytd_check([]).status == "no_fiscal_data"


def test_monthly_value_missing_gives_no_fiscal_data():
    payslips = chain([1, 2])
    payslips[0] = payslip(1, taxable=None, ytd=1000, ytd_tax=200)
    assert ytd_check(payslips).status == "no_fiscal_data"


# --- verdetto CU ------------------------------------------------------------------------


def test_cu_check_match_within_a_cent():
    payslips = chain([1, 2, 3])
    assert cu_check(cu(taxable="3000.01", tax=600), payslips).status == "match"


def test_cu_check_mismatch_reports_both_differences():
    verdict = cu_check(cu(taxable=2900, tax=650), chain([1, 2, 3]))
    assert verdict.status == "mismatch"
    assert verdict.taxable_diff == Decimal("-100")
    assert verdict.tax_diff == Decimal("50")


def test_cu_check_other_states():
    assert cu_check(cu(status="needs_review"), chain([1])).status == "to_review"
    assert cu_check(cu(), []).status == "no_payslips"
    assert cu_check(cu(), [payslip(1)]).status == "no_fiscal_data"


# --- composizione -----------------------------------------------------------------------


def test_year_summaries_compose_a_card_per_year_and_employer():
    p2025 = chain([11, 12], start_ytd=10000)
    p2026 = [
        payslip(3, year=2026, employer="09876543210", ytd=1000, ytd_tax=200, template="zucchetti")
    ]
    certificate = cu(taxable=12000, tax=2400)
    cards = year_summaries([*p2025, *p2026], [certificate])
    assert [(c.year, c.employer_tax_code) for c in cards] == [
        (2026, "09876543210"),
        (2025, EMPLOYER),
    ]
    card = cards[1]
    assert card.template == "ranocchi"
    assert [p.month for p in card.payslips] == [11, 12]
    assert card.missing_months == list(range(1, 11))
    assert card.totals.gross_pay == Decimal("3000")
    assert card.completeness.status == "incomplete"
    assert card.cu.id == certificate.id and card.cu.status == "match"
    assert cards[0].cu is None  # la CU è facoltativa: nessun errore


def test_not_done_documents_are_to_review():
    processing = payslip(4, status="processing")
    cards = year_summaries([*chain([1, 2, 3]), processing], [])
    assert cards[0].to_review == [processing.id]
    assert [p.month for p in cards[0].payslips] == [1, 2, 3]
    assert cards[0].completeness.status == "complete"


def test_duplicates_are_listed_and_left_out():
    first = chain([1])[0]
    again = payslip(1, ytd=1000, ytd_tax=200, uploaded=10)
    card = year_summaries([first, again], [])[0]
    assert card.duplicates == [first.id]
    assert [p.id for p in card.payslips] == [again.id]


def test_most_recent_done_cu_counts_others_are_duplicates():
    old, new, broken = cu(uploaded=0), cu(uploaded=5), cu(uploaded=9, status="failed")
    card = year_summaries(chain([1, 2, 3]), [old, new, broken])[0]
    assert card.cu.id == new.id
    assert set(card.duplicates) == {old.id}
    assert card.to_review == [broken.id]


def test_cu_without_payslips_still_has_its_card():
    card = year_summaries([], [cu()])[0]
    assert card.cu.status == "no_payslips"
    assert card.payslips == [] and card.completeness.status == "no_fiscal_data"


def test_cu_without_employer():
    cards = year_summaries(chain([1, 2, 3]), [cu(employer=None)])
    assert {(c.employer_tax_code, c.cu is None) for c in cards} == {(EMPLOYER, True), (None, False)}
    unknown = next(c for c in cards if c.employer_tax_code is None)
    assert unknown.cu.status == "no_payslips"  # mai abbinata ai cedolini di un altro datore
