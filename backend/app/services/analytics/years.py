"""Year summaries: payslips present and missing, totals, and the CU cross-check.

Pure functions over the records of ``records.py`` — no I/O, no SQL — shared by the
API (the «Anni» page) and, in phase 4, by the analyst agent. One summary per
``(year, employer)``. Rules, from the specification:

- re-uploads (the same employer, year, month and kind; for the CU, the same year
  and employer) are removed before anything else: the most recent copy counts and
  the older ones are ``duplicates``;
- only ``done`` documents enter sums, gaps and checks; the others are listed as
  ``to_review`` (a most recent copy not ``done`` included);
- the "last payslip" of a year is the one with the highest year-to-date taxable
  income, not the latest month (an additional month may precede an ordinary one);
- completeness compares the sum of the monthly figures with the last payslip's
  year-to-date ones; the CU verdict compares the CU with those same year-to-date
  figures; every comparison allows 0.01 €;
- the CU is optional: no CU is ``cu=None``, never an error.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.services.analytics.records import CuRecord, PayslipRecord

TOLERANCE = Decimal("0.01")
DONE = "done"


@dataclass(frozen=True)
class PayslipRef:
    """A payslip counted on a card: its id, month and kind."""

    id: uuid.UUID
    month: int | None
    additional_payment: bool


@dataclass(frozen=True)
class Totals:
    """Sums over the payslips counted; ``None`` where no payslip has the value."""

    gross_pay: Decimal | None
    net_pay: Decimal | None
    total_deductions: Decimal | None
    taxable_income: Decimal | None
    income_tax: Decimal | None


@dataclass(frozen=True)
class Completeness:
    """Monthly sums against the last payslip's year-to-date figures.

    Attributes
    ----------
    status : str
        ``complete``, ``incomplete`` or ``no_fiscal_data``.
    taxable_diff, tax_diff : Decimal or None
        Year-to-date minus the sum of the months loaded: the income and the tax of
        the payslips not loaded. ``None`` with ``no_fiscal_data``.
    """

    status: str
    taxable_diff: Decimal | None
    tax_diff: Decimal | None


@dataclass(frozen=True)
class CuVerdict:
    """The CU against the last payslip's year-to-date figures.

    Attributes
    ----------
    id : uuid.UUID
        The CU compared.
    status : str
        ``match``, ``mismatch``, ``no_payslips``, ``no_fiscal_data`` or ``to_review``.
    taxable_diff, tax_diff : Decimal or None
        CU minus payslips, with ``match``/``mismatch``.
    """

    id: uuid.UUID
    status: str
    taxable_diff: Decimal | None
    tax_diff: Decimal | None


@dataclass(frozen=True)
class YearSummary:
    """One card of the «Anni» page: a year with one employer."""

    year: int
    employer_tax_code: str | None
    template: str | None
    payslips: list[PayslipRef]
    missing_months: list[int]
    duplicates: list[uuid.UUID]
    to_review: list[uuid.UUID]
    totals: Totals
    completeness: Completeness
    cu: CuVerdict | None


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= TOLERANCE


def _dedupe[R: (PayslipRecord, CuRecord)](
    records: Iterable[R], key: Callable[[R], Hashable]
) -> tuple[list[R], list[R]]:
    """Keep the most recent record per key; return ``(kept, discarded)``."""
    latest: dict[Hashable, R] = {}
    discarded: list[R] = []
    for record in sorted(records, key=lambda r: r.created_at):
        k = key(record)
        if k in latest:
            discarded.append(latest[k])
        latest[k] = record
    return list(latest.values()), discarded


def dedupe_payslips(
    payslips: Iterable[PayslipRecord],
) -> tuple[list[PayslipRecord], list[PayslipRecord]]:
    """Drop re-uploads: one payslip per employer, year, month and kind, the most recent.

    Parameters
    ----------
    payslips : iterable of PayslipRecord

    Returns
    -------
    tuple of (list of PayslipRecord, list of PayslipRecord)
        The payslips kept and the older copies discarded.
    """
    return _dedupe(
        payslips,
        lambda p: (p.employer_tax_code, p.period_year, p.period_month, p.additional_payment),
    )


def ytd_order(payslips: Iterable[PayslipRecord]) -> list[PayslipRecord]:
    """Payslips in year-to-date order (payslips without the figure first, by month)."""
    return sorted(
        payslips,
        key=lambda p: (
            p.ytd_taxable_income is not None,
            p.ytd_taxable_income or Decimal(0),
            p.period_month or 0,
        ),
    )


def last_payslip(payslips: Iterable[PayslipRecord]) -> PayslipRecord | None:
    """The payslip with the highest year-to-date taxable income, or None without any.

    Examples
    --------
    >>> last_payslip([]) is None
    True
    """
    with_ytd = [p for p in payslips if p.ytd_taxable_income is not None]
    return max(with_ytd, key=lambda p: p.ytd_taxable_income) if with_ytd else None


def missing_months(payslips: Iterable[PayslipRecord]) -> list[int]:
    """Ordinary months missing from a year of one employer.

    A month is missing between the first and the last ordinary payslip when no
    ordinary payslip covers it, and before the first one when that payslip's
    year-to-date taxable income exceeds its own (income earned earlier in the
    year). Months after the last payslip never count: the year may be running.
    Additional payments neither create nor fill a gap.

    Parameters
    ----------
    payslips : iterable of PayslipRecord
        The payslips counted for the card.

    Returns
    -------
    list of int
        Missing months (1–12), ascending.
    """
    ordinary = [p for p in payslips if not p.additional_payment and p.period_month]
    months = {p.period_month for p in ordinary}
    if not months:
        return []
    first, last = min(months), max(months)
    missing = [m for m in range(first, last + 1) if m not in months]
    opening = next(p for p in ordinary if p.period_month == first)
    if (
        opening.ytd_taxable_income is not None
        and opening.taxable_income is not None
        and opening.ytd_taxable_income - opening.taxable_income > TOLERANCE
    ):
        missing = list(range(1, first)) + missing
    return missing


def _sum(values: Iterable[Decimal | None]) -> Decimal | None:
    present = [v for v in values if v is not None]
    return sum(present, Decimal(0)) if present else None


def year_totals(payslips: list[PayslipRecord]) -> Totals:
    """Sum the month's amounts over the payslips given, present values only."""
    return Totals(
        gross_pay=_sum(p.gross_pay for p in payslips),
        net_pay=_sum(p.net_pay for p in payslips),
        total_deductions=_sum(p.total_deductions for p in payslips),
        taxable_income=_sum(p.taxable_income for p in payslips),
        income_tax=_sum(p.income_tax for p in payslips),
    )


def ytd_check(payslips: list[PayslipRecord]) -> Completeness:
    """Compare the monthly sums with the last payslip's year-to-date figures.

    ``no_fiscal_data`` when no payslip counts, when the last one lacks the
    year-to-date figures, or when a payslip lacks its monthly ones (the sum would
    be short for the wrong reason).

    Parameters
    ----------
    payslips : list of PayslipRecord
        The payslips counted for the card.

    Returns
    -------
    Completeness
    """
    last = last_payslip(payslips)
    monthly_missing = any(p.taxable_income is None or p.income_tax is None for p in payslips)
    if last is None or last.ytd_income_tax is None or monthly_missing:
        return Completeness("no_fiscal_data", None, None)
    taxable_diff = last.ytd_taxable_income - sum((p.taxable_income for p in payslips), Decimal(0))
    tax_diff = last.ytd_income_tax - sum((p.income_tax for p in payslips), Decimal(0))
    complete = abs(taxable_diff) <= TOLERANCE and abs(tax_diff) <= TOLERANCE
    return Completeness("complete" if complete else "incomplete", taxable_diff, tax_diff)


def cu_check(cu: CuRecord, payslips: list[PayslipRecord]) -> CuVerdict:
    """Compare a CU with the last payslip of its year and employer.

    Parameters
    ----------
    cu : CuRecord
        The CU (points 1 + 2 as ``taxable_income``, point 21 as ``income_tax``).
    payslips : list of PayslipRecord
        The ``done`` payslips of the same year and employer.

    Returns
    -------
    CuVerdict
        ``to_review`` (the CU is not ``done``), ``no_payslips``, ``no_fiscal_data``
        (no year-to-date figures to compare), or ``match``/``mismatch`` with the
        differences CU − payslips.
    """
    if cu.status != DONE:
        return CuVerdict(cu.id, "to_review", None, None)
    if not payslips:
        return CuVerdict(cu.id, "no_payslips", None, None)
    last = last_payslip(payslips)
    if last is None or last.ytd_income_tax is None or None in (cu.taxable_income, cu.income_tax):
        return CuVerdict(cu.id, "no_fiscal_data", None, None)
    taxable_diff = cu.taxable_income - last.ytd_taxable_income
    tax_diff = cu.income_tax - last.ytd_income_tax
    match = _close(cu.taxable_income, last.ytd_taxable_income) and _close(
        cu.income_tax, last.ytd_income_tax
    )
    return CuVerdict(cu.id, "match" if match else "mismatch", taxable_diff, tax_diff)


def _summary(
    year: int, employer: str | None, payslips: list[PayslipRecord], cus: list[CuRecord]
) -> YearSummary:
    # prima i duplicati: conta la copia più recente, anche se non è done
    kept, duplicates = dedupe_payslips(payslips)
    counted = [p for p in kept if p.status == DONE]
    to_review = [p.id for p in kept if p.status != DONE]
    # la CU che conta è la più recente; se non è done, cu_check la dà da rivedere
    cu = None
    if cus:
        cu = max(cus, key=lambda c: c.created_at)
        duplicates += [c for c in cus if c is not cu]
        if cu.status != DONE:
            to_review.append(cu.id)
    newest = max(counted, key=lambda p: p.created_at, default=None)
    return YearSummary(
        year=year,
        employer_tax_code=employer,
        template=newest.template if newest else None,
        payslips=[
            PayslipRef(p.id, p.period_month, p.additional_payment) for p in ytd_order(counted)
        ],
        missing_months=missing_months(counted),
        duplicates=[d.id for d in duplicates],
        to_review=to_review,
        totals=year_totals(counted),
        completeness=ytd_check(counted),
        cu=cu_check(cu, counted) if cu else None,
    )


def year_summaries(payslips: Iterable[PayslipRecord], cus: Iterable[CuRecord]) -> list[YearSummary]:
    """Compose one summary per year and employer, most recent year first.

    A CU without payslips still gets its card. A missing employer tax code is its
    own group ("unknown employer"), never merged with another employer.

    Parameters
    ----------
    payslips : iterable of PayslipRecord
    cus : iterable of CuRecord

    Returns
    -------
    list of YearSummary
        Sorted by year (descending), then employer (unknown last).

    Examples
    --------
    >>> year_summaries([], [])
    []
    """
    groups: dict[tuple[int, str | None], tuple[list[PayslipRecord], list[CuRecord]]] = {}
    for p in payslips:
        groups.setdefault((p.period_year, p.employer_tax_code), ([], []))[0].append(p)
    for c in cus:
        groups.setdefault((c.period_year, c.employer_tax_code), ([], []))[1].append(c)
    keys = sorted(groups, key=lambda k: (-k[0], k[1] is None, k[1] or ""))
    return [_summary(year, employer, *groups[(year, employer)]) for year, employer in keys]
