"""Cedolini: lista documenti, dettaglio con metriche e voci di paga."""

import streamlit as st
from lib.api import APIError, get_document, list_documents
from lib.ui import DOC_TYPE_LABELS, format_eur, format_period, status_chip


def _entries_table(entries: list[dict], entry_type: str, label: str) -> None:
    rows = [
        {
            "Codice": e.get("code") or "",
            "Descrizione": e.get("description") or "",
            "Importo": format_eur(e.get("amount")),
        }
        for e in entries
        if e.get("entry_type") == entry_type
    ]
    if rows:
        st.markdown(f"**{label}**")
        st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_detail(doc: dict) -> None:
    extraction = doc.get("extraction") or {}
    fields = extraction.get("fields") or {}
    issues = extraction.get("issues") or []

    col1, col2, col3 = st.columns(3)
    col1.metric("Totale lordo", format_eur(doc.get("gross_pay")))
    col2.metric("Totale trattenute", format_eur(doc.get("total_deductions")))
    col3.metric("Netto da pagare", format_eur(doc.get("net_pay")))

    meta = st.container()
    with meta:
        period = format_period(doc.get("period_month"), doc.get("period_year"))
        label = DOC_TYPE_LABELS.get(doc.get("doc_type", ""), "—")
        chips = (
            status_chip(doc["status"])
            + "  "
            + "<span style='color:#64748b;font-size:12px'>"
            + f"{label} · periodo {period} · template {doc.get('template') or '—'} · "
            + "confidenze: "
            + ", ".join(
                f"{name} {field.get('confidence', 0):.0%}"
                for name, field in list(fields.items())[:6]
            )
            + "</span>"
        )
        st.markdown(chips, unsafe_allow_html=True)

    st.divider()
    entries = doc.get("entries") or []
    if entries:
        left, right = st.columns(2)
        with left:
            _entries_table(entries, "spettanza", "Competenze (spettanze)")
        with right:
            _entries_table(entries, "trattenuta", "Trattenute")
    else:
        st.caption("Nessuna voce riconosciuta in questo documento.")

    if issues:
        with st.expander("⚠️ Segnalazioni dalla validazione", expanded=True):
            for issue in issues:
                st.markdown(f"- **{issue.get('field') or 'documento'}**: {issue.get('message')}")

    with st.expander("Testo estratto"):
        st.text(doc.get("raw_text") or "—")
    with st.expander("JSON estrazione"):
        st.json(extraction)


def render() -> None:
    st.title("Cedolini")
    token = st.session_state["token"]

    try:
        docs = list_documents(token)
    except APIError as exc:
        st.error(str(exc))
        return
    if not docs:
        st.info("Nessun documento elaborato. Partiamo dall'upload?")
        return

    options = {
        f"{d['filename']} · {format_period(d.get('period_month'), d.get('period_year'))}": d["id"]
        for d in docs
    }
    default_id = st.session_state.pop("selected_document", None)
    default = next((k for k, v in options.items() if v == default_id), None)
    choice = st.selectbox(
        "Documento",
        options.keys(),
        index=list(options.keys()).index(default) if default else 0,
    )

    try:
        doc = get_document(token, options[choice])
    except APIError as exc:
        st.error(str(exc))
        return

    if doc["status"] in ("pending", "processing"):
        st.info("Documento in elaborazione: torna a quando ha finito.")
        return
    if doc["status"] == "failed":
        st.error(doc.get("error") or "Elaborazione fallita.")
        return
    if doc["status"] == "needs_ocr":
        st.warning("PDF senza layer di testo: richiede OCR (componente futura).")
        return

    _render_detail(doc)
