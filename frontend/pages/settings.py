"""Impostazioni: provider LLM e API key (cifrata a riposo sul backend)."""

import streamlit as st
from lib.api import APIError, get_settings, update_settings

PROVIDERS = {
    "Ollama (locale)": "ollama",
    "OpenAI (esterno)": "openai",
    "Nessuno": "",
}


def render() -> None:
    st.title("Impostazioni")
    st.caption(
        "Il provider LLM viene usato per risolvere i campi segnalati dalla validazione. "
        "Con Ollama locale nessun dato esce dalla macchina."
    )
    token = st.session_state["token"]

    try:
        current = get_settings(token)
    except APIError as exc:
        st.error(str(exc))
        return

    with st.container(border=True):
        provider_values = list(PROVIDERS.values())
        current_provider = current.get("llm_provider") or ""
        default_index = (
            provider_values.index(current_provider) if current_provider in provider_values else 0
        )
        provider_label = st.radio(
            "Provider LLM",
            PROVIDERS.keys(),
            index=default_index,
            horizontal=True,
        )
        provider = PROVIDERS[provider_label]

        ollama_base_url = ollama_model = openai_model = None
        openai_api_key = None

        if provider == "ollama":
            col1, col2 = st.columns(2)
            ollama_base_url = col1.text_input(
                "URL Ollama",
                value=current.get("ollama_base_url") or "http://host.docker.internal:11434",
            )
            ollama_model = col2.text_input(
                "Modello",
                value=current.get("ollama_model") or "llama3.1:8b",
            )
        elif provider == "openai":
            col1, col2 = st.columns(2)
            openai_model = col1.text_input(
                "Modello OpenAI",
                value=current.get("openai_model") or "gpt-4o-mini",
            )
            key_set = current.get("openai_api_key_set")
            openai_api_key = col2.text_input(
                "API key OpenAI",
                type="password",
                value="",
                placeholder="••••• salvata" if key_set else "sk-…",
                help="Lascia vuoto per mantenere quella salvata: viene cifrata a riposo.",
            ).strip()

        payload = {
            "llm_provider": provider,
            "ollama_base_url": ollama_base_url,
            "ollama_model": ollama_model,
            "openai_model": openai_model,
        }
        if openai_api_key:  # vuota = non cambia; l'utente la cancella via form vuoto
            payload["openai_api_key"] = openai_api_key

        if st.button("Salva impostazioni", type="primary"):
            try:
                update_settings(token, payload)
            except APIError as exc:
                st.error(str(exc))
            else:
                st.success("Impostazioni salvate.")

    with st.expander("Come funziona la privacy", expanded=False):
        st.markdown(
            "- Estrazione e validazione girano **solo in locale**.\n"
            "- Con **Ollama** nessun dato lascia la macchina.\n"
            "- Con **OpenAI** la chiave è cifrata a riposo e i dati PII "
            "saranno anonimizzati (Fase 4)."
        )
