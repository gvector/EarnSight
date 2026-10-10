import asyncio
import os
import tempfile

# Le impostazioni vanno fissate prima di ogni import di app.*: pydantic-settings
# cachea la configurazione al primo import (e i valori d'ambiente vincono sul .env).
# sqlite+aiosqlite rende l'API testabile (lifespan + TestClient) senza Postgres;
# credenziali e SECRET_KEY espliciti perché il .env di sviluppo non influenzi
# il seed né il fail-fast sul segreto placeholder.
# Tutto in una dir temporanea: nessun file sqlite lasciato in tests/.
_tmp_dir = tempfile.mkdtemp(prefix="earnsight-test-")
TEST_PASSWORD = "test-password-not-for-production"
_test_db = os.path.join(_tmp_dir, "api.sqlite3")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_test_db}")
os.environ.setdefault("DATA_DIR", _tmp_dir)
os.environ.setdefault("AUTH_USERNAME", "admin")
os.environ.setdefault("AUTH_PASSWORD", TEST_PASSWORD)
os.environ.setdefault("SECRET_KEY", "test-secret-key-above-32-chars-not-for-production")

import app.models.payslip  # noqa: E402,F401  (registra i modelli su Base.metadata)
import app.models.setting  # noqa: E402,F401
import app.models.user  # noqa: E402,F401
import pymupdf as fitz  # noqa: E402
import pytest  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

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


# Cedolino Zucchetti sintetico: coordinate dal layout reale, dati inventati.
# Le etichette riproducono il text layer reale, che mette «s» al posto degli
# spazi («TOTALEsCOMPETENZE»). Totali: 2.005,00 − 434,66 + 0,66 = 1.571,00.
ZUCCHETTI_ENTRIES = [
    # (codice, descrizione, importo base, riferimento, trattenuta, competenza)
    ("000014", "Retribuzione", "80,00000", "26,00000 GG", None, "1.993,00"),
    ("001201", "Ente Bilaterale Commercio", None, None, None, "12,00"),
    ("ZP9960", "Arrotond. mese pr.", None, None, "0,40", None),
    ("Z00000", "Contributo IVS", "2.005,00", "9,19000 %", "184,26", None),
    # quota a carico ditta: importo tra parentesi, informativo, fuori dai totali
    ("002400", "Contributo Previras", "C/Ditta", "1,55000 %", None, "( 31,10 )"),
    ("F02000", "Imponibile IRPEF", "1.820,74", None, None, None),  # solo informativa
    ("F03020", "Ritenute IRPEF", None, None, "250,00", None),
]


def _put(page, x, y, text, size=8):
    page.insert_text((x, y), text, fontname="helv", fontsize=size)


def _zucchetti_payslip_page(doc, period, entries, rounding, net, deductions):
    page = doc.new_page(width=595, height=842)
    _put(page, 86, 28, "RagionesSociale", 5)
    _put(page, 85, 38, "AZIENDA ESEMPIO S.P.A.")
    _put(page, 28, 78, "CodicesFiscale", 5)  # CF azienda: non va confuso col dipendente
    _put(page, 120, 82, "Sede", 5)
    _put(page, 26, 88, "01234567890")
    _put(page, 433, 102, "PERIODOsDIsRETRIBUZIONE", 5)
    _put(page, 430, 114, period)
    for x, label in [(31, "Codicesdipendente"), (98, "COGNOMEsEsNOME"),
                     (448, "CodicesFiscale"), (549, "sMatricola")]:  # fmt: skip
        _put(page, x, 137, label, 5)
    for x, value in [(29, "0000123"), (99, "ROSSI MARIO"), (449, "RSSMRA80A01H501U")]:
        _put(page, x, 148, value)
    _put(page, 520, 257, "TOTALE", 6)
    _put(page, 525, 270, "1.900,00000")  # paga base mensile: non è il lordo
    for x, label in [(86, "VOCIsVARIABILIsDELsMESE"), (251, "IMPORTOsBASE"),
                     (352, "RIFERIMENTO"), (448, "TRATTENUTE"), (518, "COMPETENZE")]:  # fmt: skip
        _put(page, x, 282, label, 5)
    y = 296
    for code, desc, base, ref, tratt, comp in entries:
        if code:
            _put(page, 39, y, code)
        _put(page, 69, y, desc)
        for x, value in [(281, base), (368, ref), (462, tratt), (537, comp)]:
            if value:
                _put(page, x, y, value)
        y += 10.4
    _put(page, 28, 616, "CONGUAGLIO", 5)
    _put(page, 28, 652, "PROGRESSIVI", 5)
    # sottoetichette (parole separate, come nel text layer reale), allineate a destra
    for right, first, second in [(129, "Imp.", "INPS"), (205, "Imp.", "INAIL"),
                                 (281, "Imp.", "IRPEF"), (357, "IRPEF", "pagata")]:  # fmt: skip
        width = fitz.get_text_length(second, fontname="helv", fontsize=5)
        _put(page, right - width, 656, second, 5)
        _put(
            page,
            right - width - 3 - fitz.get_text_length(first, fontname="helv", fontsize=5),
            656,
            first,
            5,
        )
    # progressivi (fuori dalla tabella voci): valori allineati a destra all'etichetta
    for right, value in [
        (129, "9.876,00"),
        (205, "9.876,00"),
        (281, "8.950,00"),
        (357, "1.236,00"),
    ]:
        _put(page, right - fitz.get_text_length(value, fontname="helv", fontsize=8), 668, value)
    for y, label, value in [(703, "TOTALEsCOMPETENZE", "2.005,00"),
                            (717, "TOTALEsTRATTENUTE", deductions),
                            (729, "ARROTONDAMENTO", rounding)]:  # fmt: skip
        _put(page, 425, y, label, 6)
        _put(page, 547, y, value)
    _put(page, 487, 736, "NETTOsDELsMESE", 5)
    _put(page, 510, 748, f"{net} €", 10)
    _put(page, 187, 818, "Zucchetti spa, Autorizzazione Inail n. 299 del 15/01/2009")


def _zucchetti_attendance_page(doc, period):
    page = doc.new_page(width=595, height=842)
    _put(page, 52, 432, "PERIODOsDIsRIFERIMENTO", 5)
    _put(page, 49, 444, period)
    for x, label in [(48, "GIORNO"), (150, "ORE"), (360, "GIUSTIFICATIVI"), (700, "TIMBRATURE")]:
        _put(page, x * 595 / 910, 470, label, 5)
    for day in range(1, 23):
        _put(page, 46, 480 + day * 11.6, f"LU {day}   8,00")
    _put(page, 187, 818, "Zucchetti spa, Autorizzazione Inail n. 301 del 15/01/2009")


def build_zucchetti_pdf(
    path,
    period="Aprile 2026",
    attendance_period=None,
    entries=ZUCCHETTI_ENTRIES,
    rounding="0,66",
    net="1.571,00",
    deductions="434,66",
):
    """Cedolino Zucchetti; con attendance_period antepone il foglio presenze."""
    doc = fitz.open()
    if attendance_period:
        _zucchetti_attendance_page(doc, attendance_period)
    _zucchetti_payslip_page(doc, period, entries, rounding, net, deductions)
    doc.save(path)
    doc.close()


def _cu_pages(doc, header, point1, point21, year, point2=None):
    page = doc.new_page(width=595, height=842)
    _put(page, 372, 14, header, 5)
    _put(page, 200, 60, "CERTIFICAZIONE UNICA", 9)
    _put(page, 300, 74, f"RELATIVA ALL’ANNO {year}", 6)
    _put(page, 121, 136, "Codice fiscale", 5)
    _put(page, 122, 144, "1", 5)
    _put(page, 128, 146, "01234567890", 10)  # a x 126 PyMuPDF lo fonde col numero del punto
    _put(page, 400, 136, "Codice fiscale", 5)  # del percipiente: non è il datore
    _put(page, 400, 146, "RSSMRA80A01H501U", 10)
    page = doc.new_page(width=595, height=842)
    _put(page, 372, 14, header, 5)
    # esca: stesso numero di punto sotto un'altra etichetta, prima nell'ordine di lettura
    _put(page, 125, 34, "Redditi di pensione", 5)
    _put(page, 122, 46, "1", 5)
    _put(
        page,
        219 - fitz.get_text_length("77.777,00", fontname="helv", fontsize=10),
        45,
        "77.777,00",
        10,
    )
    _put(page, 40, 60, "DATI FISCALI", 7)
    # punti 1 e 2: lavoro dipendente a tempo indeterminato e determinato (stessa intestazione)
    _put(page, 125, 84, "Redditi di lavoro dipendente e assimilati", 5)
    _put(page, 234, 84, "Redditi di lavoro dipendente e assimilati", 5)
    _put(page, 125, 92, "con contratto a tempo indeterminato", 5)
    _put(page, 234, 92, "con contratto a tempo determinato", 5)
    _put(page, 122, 102, "1", 5)
    _put(page, 232, 102, "2", 5)
    _put(page, 342, 102, "3", 5)
    for right, value in [(219, point1), (330, point2)]:
        if value:
            _put(
                page,
                right - fitz.get_text_length(value, fontname="helv", fontsize=10),
                101,
                value,
                10,
            )
    _put(page, 125, 210, "Ritenute Irpef", 5)
    _put(page, 209, 210, "Addizionale regionale all’Irpef", 5)
    for x, number in [(122, "21"), (209, "22"), (301, "26"), (388, "27")]:
        _put(page, x, 221, number, 5)
    if point21:
        _put(
            page,
            199 - fitz.get_text_length(point21, fontname="helv", fontsize=10),
            220,
            point21,
            10,
        )
    _put(
        page, 280 - fitz.get_text_length("300,00", fontname="helv", fontsize=10), 220, "300,00", 10
    )


def build_cu_pdf(path, *, point1="25.000,00", point21="5.000,00", copy=True, year="2025",
                 copy_point1=None, point2=None):  # fmt: skip
    """CU sul modello ministeriale (dati inventati): originale + copia per il percipiente."""
    doc = fitz.open()
    _cu_pages(doc, "ORIGINALE PER IL PERCIPIENTE", point1, point21, year, point2)
    page = doc.new_page(width=595, height=842)
    _put(page, 72, 72, "Istruzioni: il punto 1 indica i redditi di lavoro dipendente", 8)
    # seconda riga: senza, la media parole/pagina scende sotto la soglia del text layer
    _put(page, 72, 86, "Il punto 21 indica le ritenute Irpef operate dal sostituto d’imposta", 8)
    if copy:
        _cu_pages(doc, "COPIA PER IL PERCIPIENTE", copy_point1 or point1, point21, year, point2)
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
def cu_pdf(tmp_path):
    path = tmp_path / "cu.pdf"
    build_cu_pdf(path)
    return path


@pytest.fixture
def blank_pdf(tmp_path):
    path = tmp_path / "scan.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def client():
    """TestClient con schema creato esplicitamente: lo schema nasce da
    Alembic in produzione, il lifespan non fa più create_all."""

    async def _create_schema():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)  # isolamento fra test
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create_schema())
    with TestClient(app) as test_client:  # il lifespan fa il seed dell'utente
        yield test_client
