"""API Key verification helpers."""

from fastapi import HTTPException, status


def verify_api_key(provided: str | None, expected: str) -> None:
    """Raise 401 if the provided key does not match settings.api_key."""
    if not provided or provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
