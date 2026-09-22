"""Revisione: campi segnalati dalla validazione → correzione manuale o LLM."""

import streamlit as st
from lib.api import (
    APIError,
    correct_fields,
    get_document,
    get_settings,
    list_documents,
    llm_resolve,
)
from lib.ui import format_period, status_chip

# campi dove il valore va convertito in numero prima dell'invio
NUMERIC_FIELDS = {"gross_pay", "net_pay", "total_deductions"}
INT_FIELDS = {"period_month", "period_year"}


def _convert(field: str, raw: str):
    if field in NUMERIC_FIELDS:
        return float(raw.replace(".", "").replace(",", ".").replace(" ", ""))
    if field in INT_FIELDS:
        return int(raw)
    return raw


def _render_revision(doc: dict, provider_configured: bool) -> None:
    extraction = doc.get("extraction") or {}
    fields = extraction.get("fields") or {}
    issues = [i for i in (extraction.get("issues") or []) if i.get("field")]

    st.markdown(
        f"{status_chip(doc['status'])}  "
        f"<span style='color:#64748b;font-size:12px'>"
        f"periodo {format_period(doc.get('period_month'), doc.get('period_year'))}</span>",
        unsafe_allow_html=True,
    )
    st.caption("Correggi i valori segnalati: la rivalidazione è automatica.")

    st.divider()
    for issue in issues:
        field = issue["field"]
        current = (fields.get(field) or {}).get("value", "")
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(
                    f"**{field}** · {issue.get('message')}",
                    unsafe_allow_html=True,
                )
            with col2:
                st.markdown(f"azione suggerita: {issue.get('action')}", unsafe_allow_html=True)
            st.text_input(f"Valore corretto — {field}", value=str(current), key=f"val-{field}")

    left, right = st.columns(2)
    token = st.session_state["token"]
    with left:
        if st.button("Salva correzioni", type="primary", use_container_width=True):
            corrections = {}
            for issue in issues:
                field = issue["field"]
                raw = st.session_state.get(f"val-{field}")
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    corrections[field] = _convert(field, str(raw))
                except (ValueError, TypeError):
                    st.error(f"{field}: valore non valido («{raw}»)")
                    corrections = {}
                    break
            if corrections:
                try:
                    correct_fields(token, doc["id"], corrections)
                except APIError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()
    with right:
        button_disabled = not provider_configured or not issues
        help_text = None if provider_configured else "Configura un provider LLM nelle Impostazioni"
        if st.button(
            "✨ Risolvi con LLM",
            disabled=button_disabled,
            help=help_text,
            use_container_width=True,
        ):
            try:
                llm_resolve(token, doc["id"])
            except APIError as exc:
                st.error(str(exc))
            else:
                st.rerun()


def render() -> None:
    st.title("Revisione")
    st.caption("I documenti con segnalazioni arrivano qui: correzione manuale o richiesta all'LLM.")
    token = st.session_state["token"]

    try:
        docs = list_documents(token)
        app_settings = get_settings(token)
    except APIError as exc:
        st.error(str(exc))
        return

    provider_configured = bool(app_settings.get("llm_provider"))
    candidates = [d for d in docs if d["status"] in ("needs_review", "failed", "needs_ocr")]

    if not candidates:
        st.success("Nessun documento da revisionare. Tutto pulito. ✅")
        return

    options = {
        f"{d['filename']} · {format_period(d.get('period_month'), d.get('period_year'))}": d["id"]
        for d in candidates
    }
    choice = st.selectbox("Documento da revisionare", options.keys())
    try:
        doc = get_document(token, options[choice])
    except APIError as exc:
        st.error(str(exc))
        return

    if doc["status"] == "failed":
        st.error(doc.get("error") or "Elaborazione fallita: riprova con «Rielabora».")
        return
    if doc["status"] == "needs_ocr":
        st.warning("PDF senza layer di testo: richiede OCR (componente futura).")
        return

    _render_revision(doc, provider_configured)
