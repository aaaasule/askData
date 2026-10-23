"""API Key verification helpers."""

from fastapi import HTTPException, status


def mask_api_key(value: str | None) -> str:
    """Mask a secret for list/get responses. Empty stays empty."""
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return "****"
    return f"{raw[:3]}****{raw[-4:]}"


def verify_api_key(provided: str | None, expected: str) -> None:
    """Raise 401 if the provided key does not match settings.api_key."""
    if not provided or provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
