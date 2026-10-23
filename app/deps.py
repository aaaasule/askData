"""FastAPI dependencies: auth, settings, DB session."""

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.session import get_db
from app.security.api_key import verify_api_key
from app.services.analysis_runtime import AnalysisRuntime
from app.services.datasource_service import DatasourceService


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


def get_datasource_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DatasourceService:
    return DatasourceService(session)


def get_analysis_runtime(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AnalysisRuntime:
    return AnalysisRuntime(session)
