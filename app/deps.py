"""FastAPI dependencies: auth, settings, DB session placeholders."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header

from app.config import Settings, get_settings
from app.security.api_key import verify_api_key


async def require_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Accept Authorization: Bearer <key> or X-API-Key: <key>."""
    provided: str | None = None
    if x_api_key:
        provided = x_api_key.strip()
    elif authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided = parts[1].strip()
        else:
            provided = authorization.strip()
    verify_api_key(provided, settings.api_key)


# Placeholder: wire SQLAlchemy AsyncSession later
async def get_db() -> AsyncGenerator[None, None]:
    """Yield a DB session once models/engine are wired."""
    yield None
