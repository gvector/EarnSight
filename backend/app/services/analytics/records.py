"""Typed records for the query engine: the only place that reads documents from the DB.

The engine (``years.py``) works on immutable records rather than ORM rows, so its
functions stay pure — testable without a database and callable as tools by the
analyst agent (phase 4). Amounts are ``Decimal``; values absent from the document
stay ``None``. The year-to-date figures and ``additional_payment`` live in the
JSONB ``extraction``, everything else in the dedicated columns.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.models.payslip import PayslipDocument


@dataclass(frozen=True)
class PayslipRecord:
    """A payslip as the query engine sees it.

    Attributes
    ----------
    id : uuid.UUID
        Document id.
    period_year, period_month : int, int or None
        Pay period; the month may be missing on an unreadable payslip.
    additional_payment : bool
        True for a 13th/14th month payslip.
    status : str
        Document status (only ``done`` documents enter the sums).
    employer_tax_code, template : str or None
        Employer's tax code and payroll software.
    gross_pay, net_pay, total_deductions, taxable_income, income_tax : Decimal or None
        The month's amounts.
    ytd_taxable_income, ytd_income_tax : Decimal or None
        Year-to-date figures printed on the payslip.
    created_at : datetime
        Upload time (the most recent of two duplicates wins).
    """

    id: uuid.UUID
    period_year: int
    period_month: int | None
    additional_payment: bool
    status: str
    employer_tax_code: str | None
    template: str | None
    gross_pay: Decimal | None
    net_pay: Decimal | None
    total_deductions: Decimal | None
    taxable_income: Decimal | None
    income_tax: Decimal | None
    ytd_taxable_income: Decimal | None
    ytd_income_tax: Decimal | None
    created_at: datetime


@dataclass(frozen=True)
class CuRecord:
    """A CU (Certificazione Unica) as the query engine sees it.

    Attributes
    ----------
    id : uuid.UUID
        Document id.
    period_year : int
        Tax year certified.
    status : str
        Document status.
    employer_tax_code : str or None
        The withholding agent's tax code.
    taxable_income, income_tax : Decimal or None
        Points 1 + 2 and point 21.
    created_at : datetime
        Upload time.
    """

    id: uuid.UUID
    period_year: int
    status: str
    employer_tax_code: str | None
    taxable_income: Decimal | None
    income_tax: Decimal | None
    created_at: datetime


def _jsonb_value(doc: Any, name: str) -> Any:
    fields = (doc.extraction or {}).get("fields") or {}
    return (fields.get(name) or {}).get("value")


def _decimal(value: Any) -> Decimal | None:
    # i float del JSONB passano da str: Decimal(0.1) porterebbe con sé l'errore binario
    if value is None or isinstance(value, bool):
        return None
    return Decimal(str(value))


def record_from_document(doc: Any) -> PayslipRecord | CuRecord:
    """Build the engine record of a document.

    Parameters
    ----------
    doc : PayslipDocument
        ORM row (or any object with the same attributes) with a ``period_year``.

    Returns
    -------
    PayslipRecord or CuRecord
        ``CuRecord`` for ``doc_type == "cu"``, ``PayslipRecord`` otherwise.

    Examples
    --------
    >>> from types import SimpleNamespace
    >>> doc = SimpleNamespace(id=None, doc_type="cu", period_year=2025, status="done",
    ...     employer_tax_code=None, taxable_income=None, income_tax=None,
    ...     created_at=None)
    >>> type(record_from_document(doc)).__name__
    'CuRecord'
    """
    if doc.doc_type == "cu":
        return CuRecord(
            id=doc.id,
            period_year=doc.period_year,
            status=doc.status,
            employer_tax_code=doc.employer_tax_code,
            taxable_income=doc.taxable_income,
            income_tax=doc.income_tax,
            created_at=doc.created_at,
        )
    return PayslipRecord(
        id=doc.id,
        period_year=doc.period_year,
        period_month=doc.period_month,
        additional_payment=_jsonb_value(doc, "additional_payment") is True,
        status=doc.status,
        employer_tax_code=doc.employer_tax_code,
        template=doc.template,
        gross_pay=doc.gross_pay,
        net_pay=doc.net_pay,
        total_deductions=doc.total_deductions,
        taxable_income=doc.taxable_income,
        income_tax=doc.income_tax,
        ytd_taxable_income=_decimal(_jsonb_value(doc, "ytd_taxable_income")),
        ytd_income_tax=_decimal(_jsonb_value(doc, "ytd_income_tax")),
        created_at=doc.created_at,
    )


async def load_records(
    db: AsyncSession, user_id: int
) -> tuple[list[PayslipRecord], list[CuRecord]]:
    """Load the user's documents as engine records.

    Documents without a year (an unreadable period) are skipped: they cannot be
    placed on any year card. The entries are not loaded.

    Parameters
    ----------
    db : AsyncSession
        Database session.
    user_id : int
        Owner of the documents.

    Returns
    -------
    tuple of (list of PayslipRecord, list of CuRecord)
        Payslips and CUs, in no particular order.
    """
    rows = await db.scalars(
        select(PayslipDocument)
        .where(PayslipDocument.user_id == user_id, PayslipDocument.period_year.is_not(None))
        .options(noload(PayslipDocument.entries))
    )
    payslips: list[PayslipRecord] = []
    cus: list[CuRecord] = []
    for doc in rows:
        record = record_from_document(doc)
        (cus if isinstance(record, CuRecord) else payslips).append(record)
    return payslips, cus
