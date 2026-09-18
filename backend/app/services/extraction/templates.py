"""Rilevamento template: ogni software paghe ha una firma riconoscibile nel testo.

I marker sono configurabili: aggiungere un template = aggiungere una voce al
registro (in codice o via configurazione) con le stringhe caratteristiche.
"""

from __future__ import annotations

TEMPLATES: dict[str, list[str]] = {
    # marker case-insensitive; il template "generic" è sempre il fallback
    "zucchetti": ["zucchetti"],
    "teamsystem": ["teamsystem"],
}
GENERIC_TEMPLATE = "generic"


def detect_template(text: str) -> str:
    lowered = text.lower()
    for name, markers in TEMPLATES.items():
        if name == GENERIC_TEMPLATE or not markers:
            continue
        if all(marker.lower() in lowered for marker in markers):
            return name
    return GENERIC_TEMPLATE
