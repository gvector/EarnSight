"""Cifratura a riposo per i segreti salvati dagli utenti (es. API key OpenAI).

La chiave Fernet deriva da SECRET_KEY: ruotare SECRET_KEY invalida i segreti
cifrati. I segreti non escono mai dal backend: vengono cifrati prima della
persistenza e decifrati solo alla costruzione del gateway LLM.
"""

from __future__ import annotations

import base64
import functools
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


@functools.lru_cache
def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()
