"""Year summaries for the «Anni» page: totals, missing months and the CU verdict."""

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.schemas.years import YearOut
from app.services.analytics.records import load_records
from app.services.analytics.years import year_summaries

router = APIRouter(prefix="/years", tags=["years"])


@router.get("", response_model=list[YearOut])
async def list_years(db: DB, user: CurrentUser) -> list:
    """One summary per year and employer of the user's documents, most recent first.

    Parameters
    ----------
    db : DB
        Async database session.
    user : CurrentUser
        Authenticated user: only their documents are read.

    Returns
    -------
    list of YearSummary
        Serialised as ``YearOut``; empty without documents.
    """
    payslips, cus = await load_records(db, user.id)
    return year_summaries(payslips, cus)
