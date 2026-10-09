"""Prontezza del provider LLM: una sola regola (get_gateway_for_user) per API e UI.

- rotazione di SECRET_KEY: la API key salvata non è più decifrabile → 400 chiaro, non 500
- impostazioni mai salvate: vale il provider del .env, e GET /settings lo dice
"""

import pytest
from app.core import crypto
from app.core.config import settings
from conftest import TEST_PASSWORD, build_pdf


@pytest.fixture
def headers(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def rotate_secret_key(monkeypatch):
    """Cambia SECRET_KEY (e la chiave Fernet derivata) come dopo una rotazione."""

    def _rotate():
        monkeypatch.setattr(
            settings, "secret_key", "una-secret-key-nuova-ruotata-lunga-48-caratteri"
        )
        crypto._fernet.cache_clear()

    yield _rotate
    monkeypatch.undo()
    crypto._fernet.cache_clear()


def _needs_review_doc(client, headers, tmp_path, monkeypatch):
    from app.workers.tasks import process_document

    def broken_delay(*args, **kwargs):
        raise RuntimeError("broker non raggiungibile")

    monkeypatch.setattr(process_document, "delay", broken_delay)
    path = tmp_path / "bad.pdf"
    build_pdf(
        path,
        lambda net: [
            "Compenso Lordo: 2.500,00",
            "Totale Trattenute: 250,00",
            f"Netto da pagare: {net}",
        ],
        net_value="1.900,00",
    )
    with open(path, "rb") as fh:
        resp = client.post(
            "/api/payslips/upload",
            headers=headers,
            files={"file": ("bad.pdf", fh, "application/pdf")},
        )
    assert resp.json()["status"] == "needs_review"
    return resp.json()["id"]


def test_no_provider_is_not_ready(client, headers):
    data = client.get("/api/settings", headers=headers).json()
    assert data["llm_ready"] is False
    assert "Nessun provider" in data["llm_detail"]


def test_env_provider_applies_when_settings_never_saved(client, headers, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    data = client.get("/api/settings", headers=headers).json()
    assert data["llm_ready"] is True  # niente salvato, ma il .env fornisce un provider
    assert ".env" in data["llm_detail"]
    # il form mostra i valori effettivi, non «Nessuno»
    assert data["llm_provider"] == "ollama"
    assert data["ollama_model"] == settings.ollama_model


def test_saving_untouched_form_keeps_env_provider_working(client, headers, monkeypatch):
    """Salvare il form così com'è (valori dal .env) non deve disattivare il provider."""
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    shown = client.get("/api/settings", headers=headers).json()
    payload = {k: shown[k] for k in ("llm_provider", "ollama_base_url", "ollama_model")}
    saved = client.put("/api/settings", headers=headers, json=payload).json()
    assert saved["llm_ready"] is True
    assert "impostazioni utente" in saved["llm_detail"]


def test_openai_without_own_key_uses_env_key(client, headers, monkeypatch):
    """Come modello e URL, la key mancante ricade sul .env (OPENAI_API_KEY)."""
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-dal-env")
    saved = client.put("/api/settings", headers=headers, json={"llm_provider": "openai"}).json()
    assert saved["llm_ready"] is True


def test_saved_settings_override_env(client, headers, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    client.put("/api/settings", headers=headers, json={"llm_provider": ""})
    data = client.get("/api/settings", headers=headers).json()
    assert data["llm_ready"] is False


def test_openai_with_key_is_ready(client, headers):
    resp = client.put(
        "/api/settings",
        headers=headers,
        json={"llm_provider": "openai", "openai_api_key": "sk-test-123"},
    )
    assert resp.json()["llm_ready"] is True


def test_rotated_secret_key_reports_unreadable_key(
    client, headers, rotate_secret_key, tmp_path, monkeypatch
):
    client.put(
        "/api/settings",
        headers=headers,
        json={"llm_provider": "openai", "openai_api_key": "sk-test-123"},
    )
    doc_id = _needs_review_doc(client, headers, tmp_path, monkeypatch)
    rotate_secret_key()
    # la rotazione invalida anche i JWT (firmati con SECRET_KEY): nuovo login
    resp = client.post("/api/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    data = client.get("/api/settings", headers=headers).json()
    assert data["llm_ready"] is False
    assert "reinseriscila" in data["llm_detail"]

    resp = client.post(f"/api/payslips/{doc_id}/llm-resolve", headers=headers)
    assert resp.status_code == 400
    assert "reinseriscila" in resp.json()["detail"]

    # reinserire la chiave la cifra con la SECRET_KEY nuova: torna pronta
    resp = client.put(
        "/api/settings",
        headers=headers,
        json={"llm_provider": "openai", "openai_api_key": "sk-test-123"},
    )
    assert resp.json()["llm_ready"] is True


def test_saved_row_shows_env_values_for_fields_left_empty(client, headers, monkeypatch):
    """GET /settings mostra gli stessi valori che userebbe il gateway (row or .env)."""
    monkeypatch.setattr(settings, "ollama_base_url", "http://ollama-dal-env:11434")
    data = client.put("/api/settings", headers=headers, json={"llm_provider": "ollama"}).json()
    assert data["ollama_base_url"] == "http://ollama-dal-env:11434"
    assert data["ollama_model"] == settings.ollama_model
    assert data["openai_model"] == settings.openai_model
