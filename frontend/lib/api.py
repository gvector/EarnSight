"""Client HTTP verso l'API EarnSight: un unico posto per auth e errori."""

from __future__ import annotations

import os

import httpx

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


class APIError(Exception):
    pass


def _client(token: str | None = None, timeout: float = 60.0) -> httpx.Client:
    headers = {"Authorization": f"Bearer {token}"} if token else None
    return httpx.Client(base_url=API_BASE_URL, timeout=timeout, headers=headers)


def _request(
    method: str,
    path: str,
    token: str | None = None,
    json: dict | None = None,
    data: dict | None = None,
    files: dict | None = None,
    timeout: float = 60.0,
):
    try:
        with _client(token, timeout) as client:
            response = client.request(
                method, path, json=json, data=data, files=files
            )
    except httpx.HTTPError as exc:
        raise APIError(f"API non raggiungibile: {exc}") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise APIError(str(detail))
    return response.json()


def login(username: str, password: str) -> dict:
    return _request("POST", "/api/auth/login", json={"username": username, "password": password})


def list_documents(token: str) -> list[dict]:
    return _request("GET", "/api/payslips", token=token)


def get_document(token: str, doc_id: str) -> dict:
    return _request("GET", f"/api/payslips/{doc_id}", token=token)


def upload_document(token: str, filename: str, content: bytes, doc_type: str) -> dict:
    return _request(
        "POST",
        "/api/payslips/upload",
        token=token,
        files={"file": (filename, content, "application/pdf")},
        data={"doc_type": doc_type},
    )


def correct_fields(token: str, doc_id: str, fields: dict) -> dict:
    return _request("PATCH", f"/api/payslips/{doc_id}/fields", token=token, json={"fields": fields})


def llm_resolve(token: str, doc_id: str) -> dict:
    return _request("POST", f"/api/payslips/{doc_id}/llm-resolve", token=token, timeout=180.0)


def get_settings(token: str) -> dict:
    return _request("GET", "/api/settings", token=token)


def update_settings(token: str, payload: dict) -> dict:
    return _request("PUT", "/api/settings", token=token, json=payload)
