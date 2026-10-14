"""Response schemas of ``GET /api/years``: the year summaries of the query engine.

Pydantic mirrors of the frozen dataclasses in ``services/analytics/years.py``
(built with ``from_attributes``); amounts are ``Decimal`` and serialise as strings,
like the document totals. The front end's twin types live in ``frontend/src/api.ts``.
"""

import uuid
from decimal import Decimal

from pydantic import BaseModel

_FROM_ATTRIBUTES = {"from_attributes": True}


class PayslipRefOut(BaseModel):
    """A payslip counted on a card."""

    id: uuid.UUID
    month: int | None
    additional_payment: bool

    model_config = _FROM_ATTRIBUTES


class TotalsOut(BaseModel):
    """Sums over the payslips counted (``None`` where no payslip has the value)."""

    gross_pay: Decimal | None
    net_pay: Decimal | None
    total_deductions: Decimal | None
    taxable_income: Decimal | None
    income_tax: Decimal | None

    model_config = _FROM_ATTRIBUTES


class CompletenessOut(BaseModel):
    """``complete`` / ``incomplete`` / ``no_fiscal_data`` and the year-to-date gaps."""

    status: str
    taxable_diff: Decimal | None
    tax_diff: Decimal | None

    model_config = _FROM_ATTRIBUTES


class CuVerdictOut(BaseModel):
    """The CU against the payslips: ``match``, ``mismatch``, ``no_payslips``,
    ``no_fiscal_data`` or ``to_review``, with the differences CU − payslips."""

    id: uuid.UUID
    status: str
    taxable_diff: Decimal | None
    tax_diff: Decimal | None

    model_config = _FROM_ATTRIBUTES


class YearOut(BaseModel):
    """One card of the «Anni» page: a year with one employer.

    Attributes
    ----------
    year : int
        Tax year.
    employer_tax_code : str or None
        Employer's tax code; ``None`` for documents without one.
    template : str or None
        Payroll software of the most recent payslip.
    payslips : list of PayslipRefOut
        Payslips counted, in year-to-date order.
    missing_months : list of int
        Ordinary months missing.
    duplicates, to_review : list of uuid.UUID
        Re-uploads discarded; documents not ``done``, left out of every sum.
    totals : TotalsOut
    completeness : CompletenessOut
    cu : CuVerdictOut or None
        ``None`` when no CU was uploaded for the year (the CU is optional).
    """

    year: int
    employer_tax_code: str | None
    template: str | None
    payslips: list[PayslipRefOut]
    missing_months: list[int]
    duplicates: list[uuid.UUID]
    to_review: list[uuid.UUID]
    totals: TotalsOut
    completeness: CompletenessOut
    cu: CuVerdictOut | None

    model_config = _FROM_ATTRIBUTES
