import asyncio
from decimal import Decimal

import app.models.payslip  # noqa: F401
import app.models.user  # noqa: F401
import pytest
from app.db.base import Base
from app.models.payslip import PayslipDocument, PayslipEntry
from app.services.extraction.runner import process_document_sync
from app.workers.dispatch import dispatch_processing
from app.workers.tasks import process_document
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _make_document(session_factory, stored_path) -> object:
    with session_factory() as db:
        doc = PayslipDocument(
            filename="cedolino.pdf",
            stored_path=str(stored_path),
            status="pending",
        )
        db.add(doc)
        db.commit()
        return doc.id


def test_process_document_persists_extracted_result(session_factory, payslip_pdf):
    doc_id = _make_document(session_factory, payslip_pdf)

    process_document_sync(str(doc_id), session_factory=session_factory)

    with session_factory() as db:
        doc = db.get(PayslipDocument, doc_id)
        assert doc.status == "done"
        assert doc.template == "generic"
        assert doc.period_month == 1
        assert doc.period_year == 2026
        assert doc.gross_pay == Decimal("2500.0")
        assert doc.net_pay == Decimal("2250.0")
        assert doc.total_deductions == Decimal("250.0")
        assert doc.extraction["validation"]["passed"] is True
        assert doc.extraction["fields"]["net_pay"]["value"] == 2250.0
        entries = db.query(PayslipEntry).filter_by(document_id=doc_id).all()
        assert len(entries) == 2
        types = {e.entry_type for e in entries}
        assert types == {"spettanza", "trattenuta"}


def test_process_document_marks_scan_as_needs_ocr(session_factory, blank_pdf):
    doc_id = _make_document(session_factory, blank_pdf)

    process_document_sync(str(doc_id), session_factory=session_factory)

    with session_factory() as db:
        doc = db.get(PayslipDocument, doc_id)
        assert doc.status == "needs_ocr"
        assert doc.gross_pay is None


def test_process_document_repairs_inconsistent_payslip(tmp_path, session_factory):
    from conftest import build_pdf

    path = tmp_path / "bad.pdf"
    build_pdf(
        path,
        lambda net: [
            "Compenso Lordo: 2.500,00",
            "Totale Trattenute: 250,00",
            f"Netto da pagare: {net}",
        ],
        net_value="1.900,00",
    )
    doc_id = _make_document(session_factory, path)

    process_document_sync(str(doc_id), session_factory=session_factory)

    with session_factory() as db:
        doc = db.get(PayslipDocument, doc_id)
        assert doc.status == "needs_review"
        assert any(i["check"] == "net_consistency" for i in doc.extraction["issues"])


def test_invalid_doc_id_is_a_noop(session_factory):
    process_document_sync("not-a-uuid", session_factory=session_factory)


def test_dispatch_inline_fallback_when_broker_down(session_factory, payslip_pdf, monkeypatch):
    doc_id = _make_document(session_factory, payslip_pdf)

    def broken_delay(*args, **kwargs):
        raise RuntimeError("broker non raggiungibile")

    monkeypatch.setattr(process_document, "delay", broken_delay)
    queued = asyncio.run(dispatch_processing(doc_id, session_factory=session_factory))

    assert queued is False
    with session_factory() as db:
        doc = db.get(PayslipDocument, doc_id)
        assert doc.status == "done"
