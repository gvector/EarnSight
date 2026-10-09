"""Regression test API payslips: copre i difetti emersi dalla code review.

- correzioni che non azzerano template/raw_text (round-trip su Document)
- 422 (non 500) su input non numerico
- 502 gestito su risposta LLM malformata
- scoping per utente: documenti di altri utenti invisibili, user_id obbligatorio
- limite dimensione upload (413)
- dispatch inline funzionante fuori da Postgres (sqlite, senza session factory iniettata)
- firma %PDF obbligatoria sull'upload
- messaggio esplicito se il provider OpenAI non ha API key
"""

import asyncio
import uuid

import pytest
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.payslip import PayslipDocument
from app.models.user import User
from app.workers.tasks import process_document
from conftest import TEST_PASSWORD
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def inline_processing(monkeypatch):
    """Il broker non è raggiungibile: il dispatch deve elaborare inline."""

    def broken_delay(*args, **kwargs):
        raise RuntimeError("broker non raggiungibile")

    monkeypatch.setattr(process_document, "delay", broken_delay)


@pytest.fixture
def token(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _upload(client, token, pdf_path, doc_type="cedolino"):
    with open(pdf_path, "rb") as fh:
        resp = client.post(
            "/api/payslips/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("cedolino.pdf", fh, "application/pdf")},
            data={"doc_type": doc_type},
        )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_upload_processes_inline_and_returns_done(client, token, payslip_pdf, inline_processing):
    doc = _upload(client, token, payslip_pdf)
    assert doc["status"] == "done"
    assert doc["template"] == "generic"
    assert doc["period_month"] == 1
    assert float(doc["net_pay"]) == 2250.0


def test_upload_rejects_oversized_file(client, token, payslip_pdf, inline_processing, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_mb", 0, raising=False)
    with open(payslip_pdf, "rb") as fh:
        resp = client.post(
            "/api/payslips/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("cedolino.pdf", fh, "application/pdf")},
        )
    assert resp.status_code == 413


def test_upload_rejects_non_pdf(client, token):
    resp = client.post(
        "/api/payslips/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("cedolino.txt", b"testo", "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_rejects_pdf_name_without_pdf_signature(client, token):
    resp = client.post(
        "/api/payslips/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("cedolino.pdf", b"<html>non un pdf</html>", "application/pdf")},
    )
    assert resp.status_code == 400
    assert "PDF" in resp.json()["detail"]


def test_llm_resolve_openai_without_key_explains_missing_key(
    client, token, payslip_pdf, inline_processing
):
    from conftest import build_pdf

    path = payslip_pdf.parent / "bad.pdf"
    build_pdf(
        path,
        lambda net: [
            "Compenso Lordo: 2.500,00",
            "Totale Trattenute: 250,00",
            f"Netto da pagare: {net}",
        ],
        net_value="1.900,00",
    )
    doc_id = _upload(client, token, path)["id"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.put("/api/settings", headers=headers, json={"llm_provider": "openai"}).is_success

    resp = client.post(f"/api/payslips/{doc_id}/llm-resolve", headers=headers)
    assert resp.status_code == 400
    assert "API key" in resp.json()["detail"]


def test_patch_correction_preserves_template_and_raw_text(
    client, token, payslip_pdf, inline_processing
):
    doc_id = _upload(client, token, payslip_pdf)["id"]
    detail = client.get(f"/api/payslips/{doc_id}", headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200
    raw_text_before = detail.json()["raw_text"]
    assert raw_text_before

    resp = client.patch(
        f"/api/payslips/{doc_id}/fields",
        headers={"Authorization": f"Bearer {token}"},
        json={"fields": {"net_pay": 2250.0}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["raw_text"] == raw_text_before
    assert body["template"] == "generic"
    assert body["status"] == "done"


def test_patch_non_numeric_field_returns_422(client, token, payslip_pdf, inline_processing):
    doc_id = _upload(client, token, payslip_pdf)["id"]
    resp = client.patch(
        f"/api/payslips/{doc_id}/fields",
        headers={"Authorization": f"Bearer {token}"},
        json={"fields": {"period_month": "marzo"}},
    )
    assert resp.status_code == 422
    assert "marzo" in resp.json()["detail"]


def test_llm_resolve_with_malformed_response_is_handled(
    client, token, payslip_pdf, inline_processing, monkeypatch
):
    import app.api.routes.payslips as payslips_route

    class _GarbageGateway:
        def resolve_fields(self, raw_text, field_names, issues):
            assert raw_text, "il prompt deve contenere il testo del documento"
            return {"period_month": "marzo", "net_pay": "nan"}

    async def _fake_gateway(db, user):
        return _GarbageGateway()

    monkeypatch.setattr(payslips_route, "get_gateway_for_user", _fake_gateway)

    # crea un documento con un problema su cui l'LLM verrà interrogato
    from conftest import build_pdf

    path = payslip_pdf.parent / "bad.pdf"
    build_pdf(
        path,
        lambda net: [
            "Compenso Lordo: 2.500,00",
            "Totale Trattenute: 250,00",
            f"Netto da pagare: {net}",
        ],
        net_value="1.900,00",
    )
    doc_id = _upload(client, token, path)["id"]

    resp = client.post(
        f"/api/payslips/{doc_id}/llm-resolve", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 502
    # il documento resta intatto: raw_text e template non azzerati
    detail = client.get(f"/api/payslips/{doc_id}", headers={"Authorization": f"Bearer {token}"})
    assert detail.json()["raw_text"]
    assert detail.json()["template"] == "generic"


def test_documents_of_another_user_are_invisible(client, token):
    async def _insert_foreign_doc():
        async with AsyncSessionLocal() as db:
            other = User(username="altro", password_hash=hash_password("altra-password"))
            db.add(other)
            await db.flush()
            doc = PayslipDocument(
                id=uuid.uuid4(),
                user_id=other.id,
                filename="altrui.pdf",
                stored_path="/tmp/altrui.pdf",
                status="done",
            )
            db.add(doc)
            await db.commit()
            return doc.id

    foreign_id = asyncio.run(_insert_foreign_doc())

    resp = client.get("/api/payslips", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert all(doc["id"] != str(foreign_id) for doc in resp.json())

    resp = client.get(f"/api/payslips/{foreign_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_document_without_owner_is_rejected_by_the_database(client):
    async def _insert_orphan_doc():
        async with AsyncSessionLocal() as db:
            db.add(
                PayslipDocument(
                    id=uuid.uuid4(),
                    user_id=None,
                    filename="orfano.pdf",
                    stored_path="/tmp/orfano.pdf",
                    status="done",
                )
            )
            await db.commit()

    with pytest.raises(IntegrityError):
        asyncio.run(_insert_orphan_doc())


def test_upload_requires_auth(client):
    resp = client.post("/api/payslips/upload", files={"file": ("a.pdf", b"x", "application/pdf")})
    assert resp.status_code == 401
