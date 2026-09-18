import streamlit as st

st.set_page_config(page_title="EarnSight", page_icon="💼", layout="wide")

st.title("EarnSight")
st.caption("Analisi cedolini paga — Fase 2 in arrivo: login, upload e visualizzazione.")

st.info(
    "L'API backend è disponibile su `/api` (FastAPI). "
    "Questa UI verrà completata nella Fase 2 del piano.",
    icon="🚧",
)
