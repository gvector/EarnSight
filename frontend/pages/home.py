"""Home: upload dei PDF e stato dell'elaborazione."""

import time

import streamlit as st
from lib.api import APIError, list_documents, upload_document
from lib.nav import PAGES
from lib.ui import DOC_TYPE_LABELS, format_eur, format_period, status_chip

AUTO_REFRESH_STATUSES = ("pending", "processing")


def _document_card(doc: dict) -> None:
    period = format_period(doc.get("period_month"), doc.get("period_year"))
    label = DOC_TYPE_LABELS.get(doc.get("doc_type", ""), doc.get("doc_type", "—"))
    with st.container(border=True):
        col1, col2, col3, col4 = st.columns([3, 1.2, 1.4, 1.4])
        with col1:
            st.markdown(f"**{doc['filename']}**  \n{label} · periodo {period}")
        with col2:
            st.markdown(status_chip(doc["status"]), unsafe_allow_html=True)
        with col3:
            if doc.get("status") == "done":
                st.caption(f"Netto: **{format_eur(doc.get('net_pay'))}**")
        with col4:
            if st.button("Apri", key=f"open-{doc['id']}"):
                st.session_state["selected_document"] = doc["id"]
                st.switch_page(PAGES["documents"])


def render() -> None:
    st.title("Documenti")
    st.caption("Carica cedolini o Certificazioni Uniche (PDF): l'elaborazione è asincrona.")

    with st.container(border=True):
        uploaded = st.file_uploader(
            "PDF da elaborare",
            type=["pdf"],
            accept_multiple_files=True,
        )
        doc_type = st.radio(
            "Tipo documento",
            ["cedolino", "cu"],
            format_func=lambda v: DOC_TYPE_LABELS[v],
            horizontal=True,
        )
        if st.button(
            "Carica ed elabora",
            type="primary",
            disabled=not uploaded,
            use_container_width=True,
        ):
            token = st.session_state["token"]
            for file in uploaded:
                try:
                    upload_document(token, file.name, file.getvalue(), doc_type)
                except APIError as exc:
                    st.error(f"{file.name}: {exc}")
            st.rerun()

    try:
        docs = list_documents(st.session_state["token"])
    except APIError as exc:
        st.error(str(exc))
        return

    st.subheader("Caricamenti recenti")
    if not docs:
        st.info("Nessun documento: carica il primo PDF qui sopra.")
        return

    for doc in docs[:8]:
        _document_card(doc)

    busy = [d for d in docs if d["status"] in AUTO_REFRESH_STATUSES]
    if busy:
        time.sleep(2)
        st.rerun()
