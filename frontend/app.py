"""EarnSight — UI Streamlit: navigation, login e gate di autenticazione."""

import streamlit as st
from lib.api import APIError, login
from lib.nav import PAGES
from pages import documents, home, review, settings

st.set_page_config(
    page_title="EarnSight",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .block-container { padding-top: 1.6rem; }
        h1 { letter-spacing: -0.02em; }
        [data-testid="stMetric"] { background: #ffffff; border: 1px solid #e7e5e4;
            border-radius: 12px; padding: 12px 16px; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.dialog("Accedi a EarnSight")
def login_modal() -> None:
    with st.form("login-form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Entra", type="primary", use_container_width=True)
    if submitted:
        try:
            token = login(username, password)
        except APIError as exc:
            st.error(str(exc))
        else:
            st.session_state["token"] = token["access_token"]
            st.session_state["username"] = username
            st.rerun()


def render_login_backdrop() -> None:
    st.markdown(
        """
        <div style="text-align:center; padding: 4rem 0 1rem 0">
          <h1 style="margin-bottom:0.2rem">💼 EarnSight</h1>
          <p style="color:#64748b">Analisi cedolini paga — estrazione, validazione e revisione</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    if "token" not in st.session_state:
        # login modale: la finestra appare davanti e blocca la navigazione
        render_login_backdrop()
        login_modal()
        st.stop()

    with st.sidebar:
        st.markdown("### 💼 EarnSight")
        st.caption(f"👤 {st.session_state.get('username', '')}")
        if st.button("Esci", use_container_width=True):
            st.session_state.clear()
            st.rerun()
        st.divider()

    PAGES["home"] = st.Page(
        home.render, title="Documenti", icon="🏠", url_path="home", default=True
    )
    PAGES["documents"] = st.Page(
        documents.render, title="Cedolini", icon="📄", url_path="documents"
    )
    PAGES["review"] = st.Page(review.render, title="Revisione", icon="✏️", url_path="review")
    PAGES["settings"] = st.Page(
        settings.render, title="Impostazioni", icon="⚙️", url_path="settings"
    )

    nav = st.navigation(list(PAGES.values()))
    nav.run()


main()
