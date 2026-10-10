"""Cedolino Ranocchi sintetico: geometria del modulo reale, dati inventati.

Le coordinate sono i bordi inferiori misurati sul modulo reale (pt, origine in
alto a sinistra, pagina 595×842): etichette in Helvetica 4–5 pt, valori in
Courier 7,6 pt allineati al bordo destro della cella, codice e descrizione
delle voci in Courier 5,8 pt. Ai margini il testo ruotato con la firma del
software e, a destra, il calendario presenze (con importi in ore) da scartare
prima del parsing. Conti di default:
competenze 2.141,77 − trattenute voci 12,48 − contributi 196,57 −
IRPEF 335,42 + arrot. att. 0,07 − arrot. prec. 0,37 = 1.597,00.
Importi scelti fuori dai valori dei cedolini reali (``make privacy-check``).
"""

import pymupdf as fitz

LABEL, VALUE = "helv", "cour"
# PyMuPDF: bordo inferiore della parola ≈ linea di base + 0,3 × corpo
_DESCENT = 0.3


def _label(page, x, bottom, text, size=4.0):
    """Etichetta prestampata, a sinistra in ``x``, con il bordo inferiore in ``bottom``."""
    page.insert_text((x, bottom - _DESCENT * size), text, fontname=LABEL, fontsize=size)


def _text(page, x, bottom, text, size=7.6):
    """Valore allineato a sinistra (testata, anagrafica, descrizioni)."""
    page.insert_text((x, bottom - _DESCENT * size), text, fontname=VALUE, fontsize=size)


def _value(page, right, bottom, text, size=7.6):
    """Valore allineato a destra su ``right`` (come gli importi stampati sul modulo)."""
    width = fitz.get_text_length(text, fontname=VALUE, fontsize=size)
    _text(page, right - width, bottom, text, size)


ENTRIES = [
    # (codice, descrizione, quantità, competenza, trattenuta, figurativa)
    ("1", "RETRIBUZIONE ORDINARIA", "8,00", "2.037,15", None, None),
    ("1001", "ASSENZE (ore)", "8,00", None, "12,48", None),
    ("202", "FERIE GODUTE", "8,00", "104,62", None, None),
    ("2272", "BUONI PASTO", "8,00", None, None, "157,31"),  # figurativa: fuori dai totali
]


def build_ranocchi_pdf(path, *, month="Dicembre 2025", thirteenth=False, conguaglio=None,
                       empty=(), entries=ENTRIES, net="1.597,00"):  # fmt: skip
    """Scrive il PDF; ``empty`` elenca le celle da lasciare vuote (es. {"irpef"}).

    ``conguaglio`` è il TOTALE IRPEF CONGUAGLIO come stampato (segno in coda,
    es. ``"52,16-"`` per un rimborso).
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # margini ruotati: la firma del software, da scartare prima del parsing
    page.insert_text((20, 490), "Realizzazione Grafica Ranocchi Software S.r.l.", fontsize=6,
                     rotate=90)  # fmt: skip
    page.insert_text((582, 800), "Ranocchi Software, Autorizzazione Inail", fontsize=6, rotate=90)
    # calendario presenze a destra: giorno e ore, sulle stesse righe del modulo
    for k in range(29):
        _label(page, 448.9, 320.9 + 12 * k, str(k + 1), 5)
        _value(page, 485.2, 320.1 + 12 * k, "8,00")
    # testata della ditta (senza etichette)
    _label(page, 319.6, 32.2, "CODICE", 5)  # codice della ditta: non è il dipendente
    _label(page, 364.9, 32.2, "FOGLIO N.", 5)
    _text(page, 22.99, 36.2, "DITTA SINTETICA SRL")  # bordo reale appena sotto 23 pt
    _value(page, 355.6, 48.2, "000777")
    _label(page, 319.6, 56.2, "SEDE", 5)
    _label(page, 364.9, 56.2, "MESE", 5)
    if thirteenth:
        _text(page, 381.6, 60.3, "13^ mens.")
    _text(page, 22.99, 72.3, "CF:01234567890")
    _text(page, 360.0, 72.3, month)
    # anagrafica
    _label(page, 28.3, 107.0, "CODICE", 5)
    _label(page, 93.4, 107.0, "COGNOME E NOME", 5)
    _label(page, 319.4, 108.8, "ELEMENTI DELLA RETRIBUZIONE", 5)
    _value(page, 83.5, 120.4, "0042")
    _text(page, 92.1, 120.4, "ROSSI MARIO")
    _text(page, 316.8, 120.4, "MINIMO")
    _label(page, 28.3, 132.4, "COD. FISC.", 5)
    _text(page, 70.5, 132.4, "RSSMRA80A01H501U")
    # tabella voci
    for x, text in [(28.7, "VOCE"), (87.7, "DESCRIZIONE"), (167.2, "% MAGG."), (208.8, "Q.TA'"),
                    (255.0, "BASE"), (295.3, "COMPETENZA"), (347.2, "TRATTENUTA"),
                    (402.5, "FIGURATIVA")]:  # fmt: skip
        _label(page, x, 312.0, text, 5)
    for k, (code, desc, qty, comp, tratt, fig) in enumerate(entries):
        _value(page, 43.7, 319.5 + 12 * k, code, 5.8)
        _text(page, 50.4, 319.5 + 12 * k, desc, 5.8)
        for right, amount in [(234.7, qty), (338.4, comp), (394.5, tratt), (446.4, fig)]:
            if amount:
                _value(page, right, 320.1 + 12 * k, amount)
    _value(page, 337.6, 512.5, "2.141,77")  # riga totali senza etichetta
    _value(page, 393.8, 512.5, "12,48")
    # griglia in basso: contributi
    _label(page, 24.0, 522.1, "ENTE-VOCE", 5)
    _label(page, 81.7, 521.7, "IMPONIBILE")
    _label(page, 318.0, 521.7, "CONTRIBUTI")
    _label(page, 378.8, 521.7, "TOTALE CONTRIBUTI")
    _value(page, 138.9, 536.6, "2.141,77")
    _value(page, 376.5, 536.6, "196,57")  # sottocolonna contributi: non va sommata
    _value(page, 445.6, 560.7, "196,57")
    # IRPEF del mese
    _label(page, 140.3, 569.5, "IMPONIBILE IRPEF")
    _label(page, 197.8, 569.5, "IRPEF LORDA")
    _label(page, 256.2, 569.5, "DETRAZIONI")
    _label(page, 378.8, 569.5, "TOTALE IRPEF MESE")
    if "irpef" not in empty:
        _value(page, 195.1, 584.7, "1.932,72")
        _value(page, 251.2, 584.7, "444,63")
        _value(page, 316.0, 584.7, "109,21")
        _value(page, 445.6, 584.7, "335,42")
    _label(page, 140.3, 593.2, "IMPONIBILE IRPEF CONG.")
    _label(page, 318.0, 593.2, "IRPEF GIA' PAGATA")
    _label(page, 378.8, 592.9, "TOTALE IRPEF CONGUAGLIO")
    if conguaglio:
        _value(page, 445.6, 608.8, conguaglio)
    _label(page, 378.8, 641.2, "TOT. ADDIZIONALI")
    # trattenute e netto
    _label(page, 256.2, 665.2, "TRATTENUTE DA VOCI")  # subtotale: non va sommato
    _label(page, 318.0, 665.2, "ARROTOND. PREC.")
    _label(page, 378.8, 665.2, "ALTRE TRATTENUTE")  # subtotale: non va sommato
    _value(page, 316.0, 680.9, "12,48")
    _value(page, 376.5, 680.9, "0,37")
    _value(page, 445.6, 680.9, "531,99")
    _label(page, 318.0, 689.2, "ARROTOND. ATT.")
    _label(page, 378.8, 688.9, "NETTO")
    _value(page, 376.5, 696.6, "0,07")
    _value(page, 445.6, 696.6, net)
    # progressivi annui (nessuna etichetta «PROGRESSIVI» sul modulo)
    for x, text in [(24.0, "IMPONIBILE CONTRIBUTI"), (81.7, "CONTRIBUTI"),
                    (139.8, "IMPONIBILE INAIL"), (197.8, "IMPONIBILE IRPEF"),
                    (256.2, "ONERI DEDUCIBILI"), (317.5, "DETRAZIONI"),
                    (378.8, "IRPEF PAGATA")]:  # fmt: skip
        _label(page, x, 750.8, text)
    for right, amount in [(78.4, "21.417,70"), (138.9, "1.965,70"), (195.1, "21.417,70"),
                          (251.2, "19.327,20"), (376.5, "1.092,10"),
                          (445.6, "3.354,20")]:  # fmt: skip
        _value(page, right, 768.8, amount)
    doc.save(path)
    doc.close()
