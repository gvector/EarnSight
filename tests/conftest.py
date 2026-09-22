import os

# Le impostazioni vanno fissate prima di ogni import di app.*: pydantic-settings
# cachea la configurazione al primo import (e i valori d'ambiente vincono sul .env).
# sqlite+aiosqlite rende l'API testabile (lifespan + TestClient) senza Postgres;
# credenziali di test esplicite perché il .env di sviluppo non influenzi il seed.
_test_db = os.path.join(os.path.dirname(__file__), f".test-api-{os.getpid()}.sqlite3")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_test_db}")
os.environ.setdefault("AUTH_USERNAME", "admin")
os.environ.setdefault("AUTH_PASSWORD", "admin")

import pymupdf as fitz  # noqa: E402
import pytest  # noqa: E402

HEADER_ROWS = [
    "AZIENDA ESEMPIO SRL",
    "Via Roma 1 - 20100 Milano",
    "DIPENDENTE: ROSSI MARIO",
    "Codice Fiscale: RSSMRA80A01H501U",
    "Matricola: 12345",
    "Periodo di paga: 01/2026",
]


def build_pdf(path, extra_rows, net_value="2.250,00"):
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for text in HEADER_ROWS:
        page.insert_text((72, y), text, fontname="helv", fontsize=9)
        y += 14
    # header tabella con colonne a x fisse
    page.insert_text((72, y), "Voce", fontname="helv", fontsize=9)
    page.insert_text((120, y), "Descrizione", fontname="helv", fontsize=9)
    page.insert_text((300, y), "Spettanze", fontname="helv", fontsize=9)
    page.insert_text((420, y), "Trattenute", fontname="helv", fontsize=9)
    y += 14
    # righe voci: importi allineati alle colonne
    page.insert_text((72, y), "101", fontname="helv", fontsize=9)
    page.insert_text((120, y), "Retribuzione mensile", fontname="helv", fontsize=9)
    page.insert_text((305, y), "2.500,00", fontname="helv", fontsize=9)
    y += 14
    page.insert_text((72, y), "204", fontname="helv", fontsize=9)
    page.insert_text((120, y), "Contributo INPS", fontname="helv", fontsize=9)
    page.insert_text((425, y), "250,00", fontname="helv", fontsize=9)
    y += 14
    for text in extra_rows(net_value):
        page.insert_text((72, y), text, fontname="helv", fontsize=9)
        y += 14
    doc.save(path)
    doc.close()


@pytest.fixture
def payslip_pdf(tmp_path):
    path = tmp_path / "cedolino.pdf"
    build_pdf(
        path,
        lambda net: [
            "Compenso Lordo: 2.500,00",
            "Totale Trattenute: 250,00",
            f"Netto da pagare: {net}",
        ],
    )
    return path


@pytest.fixture
def blank_pdf(tmp_path):
    path = tmp_path / "scan.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    return path
