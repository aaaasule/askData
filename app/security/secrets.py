"""Fernet encryption for secrets stored in the application database.

Ciphertext lives in the existing string columns with an ``enc:v1:`` prefix.
Values without that prefix are legacy plaintext and can be re-saved on read.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

PREFIX = "enc:v1:"


class SecretError(ValueError):
    """A stored secret cannot be decrypted with the current key."""


def seal_secret(plain: str | None) -> str:
    """Encrypt a secret for storage. Empty stays empty."""
    text = plain or ""
    if text == "":
        return ""
    token = _fernet().encrypt(text.encode("utf-8")).decode("ascii")
    return PREFIX + token


def open_secret(stored: str | None) -> tuple[str, bool]:
    """Return ``(plaintext, legacy)``.

    ``legacy`` is true when ``stored`` was plaintext and should be rewritten.
    """
    text = stored or ""
    if text == "":
        return "", False
    if not text.startswith(PREFIX):
        return text, True
    try:
        plain = _fernet().decrypt(text[len(PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise SecretError(
            "stored secret cannot be decrypted; check ASKDATA_SECRET_KEY "
            "or re-save the value"
        ) from exc
    return plain, False


def _fernet() -> Fernet:
    return _fernet_for(_raw_key())


def _raw_key() -> str:
    settings = get_settings()
    configured = (settings.askdata_secret_key or settings.secret_encryption_key or "").strip()
    if configured:
        return configured
    # Stable across restarts for a local demo that never set a dedicated key.
    # Rotating API_KEY in this fallback mode cannot read older ciphertext.
    return f"askdata-dev:{settings.api_key}"


@lru_cache
def _fernet_for(secret: str) -> Fernet:
    raw = secret.encode("utf-8")
    try:
        return Fernet(raw)
    except (ValueError, TypeError):
        digest = hashlib.sha256(raw).digest()
        return Fernet(base64.urlsafe_b64encode(digest))
