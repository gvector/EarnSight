import pytest
from app.core.crypto import decrypt_secret, encrypt_secret
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with TestClient(app) as test_client:  # esegue lifespan: create_all + seed utente
        yield test_client


def _login(test_client: TestClient) -> str:
    resp = test_client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_crypto_roundtrip():
    secret = "sk-proj-abc123"
    encrypted = encrypt_secret(secret)
    assert encrypted != secret
    assert decrypt_secret(encrypted) == secret


def test_settings_default_is_empty(client):
    token = _login(client)
    resp = client.get("/api/settings", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_provider"] is None
    assert data["openai_api_key_set"] is False


def test_settings_roundtrip_with_encrypted_api_key(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "llm_provider": "openai",
        "openai_model": "gpt-4o-mini",
        "openai_api_key": "sk-test-1234567890",
    }
    resp = client.put("/api/settings", headers=headers, json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_provider"] == "openai"
    assert data["openai_api_key_set"] is True

    fetched = client.get("/api/settings", headers=headers).json()
    assert fetched["openai_api_key_set"] is True
    assert "openai_api_key" not in fetched  # la chiave non torna mai all'utente
    assert "openai_api_key_encrypted" not in fetched


def test_settings_provider_validation(client):
    token = _login(client)
    resp = client.put(
        "/api/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"llm_provider": "invalid-provider"},
    )
    assert resp.status_code == 400


def test_settings_clear_api_key(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.put(
        "/api/settings",
        headers=headers,
        json={"llm_provider": "openai", "openai_api_key": "sk-xyz"},
    )
    resp = client.put(
        "/api/settings", headers=headers, json={"llm_provider": "ollama", "openai_api_key": ""}
    )
    assert resp.status_code == 200
    assert resp.json()["openai_api_key_set"] is False


def test_settings_requires_auth(client):
    assert client.get("/api/settings").status_code == 401
