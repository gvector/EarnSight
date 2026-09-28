"""Helper di presentazione: chip di stato, formattazione, tema."""

from __future__ import annotations

from collections import Counter

import streamlit as st

STATUS_STYLES: dict[str, tuple[str, str, str]] = {
    # status: (etichetta, foreground, background)
    "pending": ("In attesa", "#92400e", "#fef3c7"),
    "processing": ("In elaborazione", "#1d4ed8", "#dbeafe"),
    "done": ("Completato", "#065f46", "#d1fae5"),
    "needs_review": ("Da revisionare", "#9a3412", "#ffedd5"),
    "needs_ocr": ("Richiede OCR", "#581c87", "#f3e8ff"),
    "failed": ("Errore", "#991b1b", "#fee2e2"),
}

DOC_TYPE_LABELS = {"cedolino": "Cedolino", "cu": "CU"}


def status_chip(status: str) -> str:
    label, fg, bg = STATUS_STYLES.get(
        status, (status or "—", "#334155", "#f1f5f9")
    )
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 10px;"
        f"border-radius:999px;font-size:12px;font-weight:600'>{label}</span>"
    )


def format_eur(value) -> str:
    if value is None:
        return "—"
    formatted = f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"


def format_period(month: int | None, year: int | None) -> str:
    if not month or not year:
        return "—"
    return f"{month:02d}/{year}"


def document_options(docs: list[dict]) -> dict[str, str]:
    """Label → id con label univoche: due documenti con stesso nome e periodo
    non si nascondono a vicenda nella selectbox (aggiunge un suffisso)."""
    seen: Counter[str] = Counter()
    options: dict[str, str] = {}
    for doc in docs:
        base = f"{doc['filename']} · {format_period(doc.get('period_month'), doc.get('period_year'))}"
        label = base if seen[base] == 0 else f"{base} · #{seen[base] + 1}"
        seen[base] += 1
        options[label] = doc["id"]
    return options


def action_chip(action: str) -> str:
    if action == "user":
        return (
            "<span style='background:#ffedd5;color:#9a3412;padding:1px 8px;"
            "border-radius:999px;font-size:11px;font-weight:600'>utente</span>"
        )
    return (
        "<span style='background:#e0e7ff;color:#3730a3;padding:1px 8px;"
        "border-radius:999px;font-size:11px;font-weight:600'>LLM</span>"
    )
