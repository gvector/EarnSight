"""Registro condiviso dei Page object: app.py li popola, le pagine li usano
per st.switch_page (richiede lo stesso oggetto Page passato a st.navigation,
non una stringa, perché le pagine sono definite da callable)."""

import streamlit as st

PAGES: dict[str, st.Page] = {}
