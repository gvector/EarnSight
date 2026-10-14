"""GET /api/years: le schede annuali calcolate sui documenti caricati via API.

PDF sintetici (dati inventati): un cedolino Ranocchi di dicembre e una CU dello
stesso datore, con i punti 1 e 21 uguali ai progressivi del cedolino.
"""

import asyncio
import uuid

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.payslip import PayslipDocument
from app.models.user import User
from conftest import build_cu_pdf
from ranocchi_pdf import build_ranocchi_pdf
from test_api_payslips import _upload

EMPLOYER = "01234567890"  # quello dei builder sintetici


def _years(client, token):
    resp = client.get("/api/years", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_years_card_with_matching_cu(client, token, tmp_path, inline_processing):
    payslip, certificate = tmp_path / "dic.pdf", tmp_path / "cu.pdf"
    build_ranocchi_pdf(payslip)
    build_cu_pdf(certificate, point1="19.327,20", point21="3.354,20")
    payslip_doc = _upload(client, token, payslip)
    cu_doc = _upload(client, token, certificate, doc_type="cu")
    assert (payslip_doc["status"], cu_doc["status"]) == ("done", "done")

    cards = _years(client, token)
    assert len(cards) == 1
    card = cards[0]
    assert (card["year"], card["employer_tax_code"]) == (2025, EMPLOYER)
    assert card["template"] == "ranocchi"
    assert card["payslips"] == [{"id": payslip_doc["id"], "month": 12, "additional_payment": False}]
    assert card["missing_months"] == list(range(1, 12))  # il progressivo porta reddito precedente
    assert card["duplicates"] == [] and card["to_review"] == []
    assert card["totals"]["gross_pay"] == "2141.77"
    assert card["completeness"] == {
        "status": "incomplete",
        "taxable_diff": "17394.48",
        "tax_diff": "3018.78",
    }
    assert card["cu"] == {
        "id": cu_doc["id"],
        "status": "match",
        "taxable_diff": "0.00",
        "tax_diff": "0.00",
    }


def test_years_without_documents(client, token):
    assert _years(client, token) == []


def test_years_are_per_user(client, token):
    async def _insert_foreign_doc():
        async with AsyncSessionLocal() as db:
            other = User(username="altro", password_hash=hash_password("altra-password"))
            db.add(other)
            await db.flush()
            db.add(
                PayslipDocument(
                    id=uuid.uuid4(),
                    user_id=other.id,
                    filename="altrui.pdf",
                    stored_path="/tmp/altrui.pdf",
                    status="done",
                    period_year=2025,
                    period_month=3,
                )
            )
            await db.commit()

    asyncio.run(_insert_foreign_doc())
    assert _years(client, token) == []


def test_years_require_auth(client):
    assert client.get("/api/years").status_code == 401
