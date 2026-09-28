"""Encryption at rest for user-stored secrets (e.g. OpenAI API keys).

The Fernet key is derived from SECRET_KEY: rotating SECRET_KEY invalidates
previously encrypted secrets. Secrets never leave the backend in plaintext;
they are encrypted before persistence and decrypted only when constructing
the LLM gateway.
"""

from __future__ import annotations

import base64
import functools
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


@functools.lru_cache
def _fernet() -> Fernet:
    """Build and memoize the Fernet cipher derived from SECRET_KEY.

    The derivation is deterministic, so the cipher is computed once per
    process and served from the lru_cache afterwards; this is also why a
    SECRET_KEY rotation requires a restart to take effect.

    Returns
    -------
    Fernet
        Cipher initialized with the urlsafe base64-encoded SHA-256 of
        the master secret, as required by the Fernet key format.

    Dependencies
    -----------
    - app.core.config.settings : master secret used for derivation.
    - cryptography.fernet.Fernet : symmetric encryption primitive.
    """
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    """Encrypt a plaintext secret for storage at rest.

    Applied before any secret touches the database, so plaintext values
    (such as user-provided LLM API keys) are never persisted.

    Parameters
    ----------
    value : str
        Plaintext secret to encrypt.

    Returns
    -------
    str
        Printable Fernet token safe for a text column.

    Dependencies
    -----------
    - _fernet : the process-wide cipher instance.

    Examples
    --------
    >>> decrypt_secret(encrypt_secret("sk-123"))  # doctest: +SKIP
    'sk-123'
    """
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    """Decrypt a Fernet token back to the plaintext secret.

    Used only where the secret is actually consumed (LLM gateway
    construction), keeping decryption off the request path wherever
    possible.

    Parameters
    ----------
    value : str
        Fernet token as produced by :func:`encrypt_secret`.

    Returns
    -------
    str
        Original plaintext secret.

    Raises
    ------
    cryptography.fernet.InvalidToken
        If the token was encrypted under a different SECRET_KEY (e.g.
        after a rotation) or is otherwise malformed.

    Dependencies
    -----------
    - _fernet : the process-wide cipher instance.
    """
    return _fernet().decrypt(value.encode()).decode()
