"""Async engine and session bound to DATABASE_URL."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Create the application engine on first use so tests can point at a temp DB."""
    global _engine, _sessionmaker
    if _engine is None:
        url = get_settings().database_url
        pool_kwargs: dict[str, object] = {}
        if url.startswith("sqlite"):
            pool_kwargs["poolclass"] = NullPool
        else:
            pool_kwargs["pool_pre_ping"] = True
        _engine = create_async_engine(url, **pool_kwargs)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    if _sessionmaker is None:
        raise RuntimeError("database session factory was not initialized")
    return _sessionmaker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a session. Callers commit their own unit of work."""
    maker = get_sessionmaker()
    async with maker() as session:
        yield session


async def dispose_engine() -> None:
    """Drop the cached engine (tests and shutdown)."""
    global _engine, _sessionmaker
    engine = _engine
    _engine = None
    _sessionmaker = None
    if engine is not None:
        await engine.dispose()
