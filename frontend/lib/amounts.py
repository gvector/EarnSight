"""Parsing degli importi digitati dall'utente: tollerante sul formato.

Accetta italiano ('2.250,50'), inglese ('2,250.50') e i casi ambigui con
un solo separatore: '2250.50' è un decimale, '2.250' sono migliaia.
"""

from __future__ import annotations

import re

# solo gruppi di migliaia italiani: '2.250', '25.000' (non '2250.50')
_MIGLIAIA_RE = re.compile(r"^\d{1,3}(?:\.\d{3})+$")


def parse_amount_input(raw: str) -> float:
    """Converte l'input utente in float; ValueError se non è un importo."""
    text = str(raw).strip().replace(" ", "").replace("€", "")
    if not text:
        raise ValueError("importo vuoto")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):  # italiano: 2.250,50
            text = text.replace(".", "").replace(",", ".")
        else:  # inglese: 2,250.50
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")  # decimale italiano: 250,00
    elif _MIGLIAIA_RE.match(text):
        text = text.replace(".", "")  # migliaia italiane: 2.250
    return float(text)  # ValueError per tutto il resto ('marzo', '1.2.3', ...)
