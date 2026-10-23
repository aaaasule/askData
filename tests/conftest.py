"""Shared fixtures: migrate a temp SQLite app database and expose an API client."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]


def _alembic_executable() -> str:
    candidates = [
        shutil.which("alembic"),
        str(Path(sys.executable).with_name("alembic")),
        str(Path.home() / ".local/bin/alembic"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError("alembic executable not found; pip install alembic")


@pytest.fixture
def app_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "askdata.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("ASKDATA_SECRET_KEY", "test-secret-key-do-not-use")
    monkeypatch.setenv("SQL_MAX_ROWS", "200")
    monkeypatch.setenv("SQL_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("CONVERSATION_MAX_MESSAGES", "12")
    monkeypatch.setenv("CONVERSATION_MAX_CHARS", "12000")

    from app.config import get_settings

    get_settings.cache_clear()
    completed = subprocess.run(
        [_alembic_executable(), "upgrade", "head"],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed\n{completed.stdout}\n{completed.stderr}")
    return tmp_path


@pytest.fixture
async def client(app_home: Path) -> AsyncIterator[AsyncClient]:
    _ = app_home
    from app.config import get_settings
    from app.db.session import dispose_engine

    get_settings.cache_clear()
    await dispose_engine()
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await dispose_engine()
    get_settings.cache_clear()
