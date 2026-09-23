import pytest
from app.core.crypto import decrypt_secret, encrypt_secret
from fastapi.testclient import TestClient


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


def test_sync_database_url_maps_known_drivers():
    from app.core.config import Settings

    postgres = Settings(database_url="postgresql+asyncpg://u:p@h:5432/db", secret_key="x" * 40)
    assert postgres.sync_database_url == "postgresql+psycopg://u:p@h:5432/db"

    sqlite = Settings(database_url="sqlite+aiosqlite:///./test.db", secret_key="x" * 40)
    assert sqlite.sync_database_url == "sqlite+pysqlite:///./test.db"


def test_sync_database_url_fails_loudly_on_unknown_driver():
    from app.core.config import Settings

    exotic = Settings(database_url="postgresql+psycopg2://u:p@h/db", secret_key="x" * 40)
    with pytest.raises(ValueError, match="psycopg2"):
        _ = exotic.sync_database_url


def test_placeholder_secret_key_is_detected():
    from app.core.config import Settings

    assert Settings(secret_key="dev-secret-change-me").secret_key_is_placeholder is True
    assert (
        Settings(secret_key="change-me-with-a-long-random-string").secret_key_is_placeholder is True
    )
    assert Settings(secret_key="short").secret_key_is_placeholder is True
    assert Settings(secret_key="x" * 40).secret_key_is_placeholder is False
