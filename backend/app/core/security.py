"""Password hashing and JWT issue/verify helpers for EarnSight auth."""

import hashlib
import hmac
import os
import time

import jwt

from app.core.config import settings

_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a plaintext password with scrypt and a fresh random salt.

    A new 16-byte salt is generated per call so identical passwords yield
    different digests; the salt is embedded in the returned string, making
    verification self-contained with no external salt storage.

    Parameters
    ----------
    password : str
        Plaintext password to hash.

    Returns
    -------
    str
        ``<salt-hex>$<digest-hex>`` produced with scrypt parameters
        ``n=2**14, r=8, p=1``.

    Dependencies
    -----------
    - hashlib.scrypt : memory-hard key derivation function.
    - os.urandom : per-password cryptographically random salt.

    Examples
    --------
    >>> hash_password("s3cret") != hash_password("s3cret")
    True
    """
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check a plaintext candidate against a stored ``salt$digest`` hash.

    A malformed stored value is treated as a mismatch rather than an
    error, so a corrupted row cannot crash the login flow. The final
    digest comparison is constant-time to prevent timing attacks.

    Parameters
    ----------
    password : str
        Plaintext candidate password.
    stored : str
        Hash string as produced by :func:`hash_password`.

    Returns
    -------
    bool
        True if the candidate matches the stored digest, False on any
        mismatch or malformed stored value.

    Dependencies
    -----------
    - hashlib.scrypt : recomputes the digest with the embedded salt.
    - hmac.compare_digest : constant-time comparison of the digests.
    """
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_access_token(username: str) -> str:
    """Issue a signed HS256 JWT for the given username.

    The token carries ``sub``, ``iat`` and an ``exp`` claim derived from
    ``settings.access_token_expire_minutes``; the signature binds it to
    the deployment's SECRET_KEY, so tokens do not survive a rotation.

    Parameters
    ----------
    username : str
        Identity embedded in the ``sub`` claim.

    Returns
    -------
    str
        Encoded JWT string (header.payload.signature).

    Dependencies
    -----------
    - app.core.config.settings : signing key and token lifetime.
    - jwt.encode : HS256 token signing.

    Examples
    --------
    >>> create_access_token("admin").count(".")  # doctest: +SKIP
    2
    """
    now = int(time.time())
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + settings.access_token_expire_minutes * 60,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """Verify a JWT's signature and expiry and return its claim set.

    Validation is delegated entirely to the library so that tampered
    signatures and expired tokens are rejected before any claim is
    trusted by the caller.

    Parameters
    ----------
    token : str
        JWT previously issued by :func:`create_access_token`.

    Returns
    -------
    dict
        Decoded claims (``sub``, ``iat``, ``exp``).

    Raises
    ------
    jwt.InvalidTokenError
        If the signature is invalid or the token is expired.

    Dependencies
    -----------
    - app.core.config.settings : verification key.
    - jwt.decode : signature and expiry validation.
    """
    return jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
