"""Fernet at rest: roundtrip, mask, and legacy plaintext rows."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.security.api_key import mask_api_key
from app.security.secrets import PREFIX, SecretError, open_secret, seal_secret


def test_roundtrip_and_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASKDATA_SECRET_KEY", "unit-test-key")
    monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
    get_settings.cache_clear()
    sealed = seal_secret("s3cret-value")
    assert sealed.startswith(PREFIX)
    assert sealed != "s3cret-value"
    plain, legacy = open_secret(sealed)
    assert plain == "s3cret-value"
    assert legacy is False
    assert seal_secret("") == ""
    assert open_secret("") == ("", False)
    assert open_secret(None) == ("", False)
    again = seal_secret("s3cret-value")
    assert again != sealed
    assert open_secret(again)[0] == "s3cret-value"


def test_legacy_plaintext_and_wrong_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASKDATA_SECRET_KEY", "first-key")
    get_settings.cache_clear()
    assert open_secret("legacy-plain") == ("legacy-plain", True)
    sealed = seal_secret("kept")
    monkeypatch.setenv("ASKDATA_SECRET_KEY", "second-key")
    get_settings.cache_clear()
    with pytest.raises(SecretError):
        open_secret(sealed)
    masked = mask_api_key("sk-live-secret-1234")
    assert masked.startswith("sk-")
    assert "****" in masked
    assert "live-secret" not in masked


def _headers() -> dict[str, str]:
    return {"X-API-Key": "test-key"}


async def test_plaintext_password_and_api_key_migrate_on_read(
    client: AsyncClient, app_home: Path
) -> None:
    created = await client.post(
        "/api/v1/datasources",
        headers=_headers(),
        json={"name": "legacy", "db_type": "sqlite", "database": ":memory:", "password": "temp"},
    )
    assert created.status_code == 200
    datasource_id = created.json()["data"]["id"]
    assert "password" not in created.json()["data"]
    assert "temp" not in created.text

    model = await client.post(
        "/api/v1/aigc/models",
        headers=_headers(),
        json={"name": "legacy", "model": "gpt-test", "api_key": "sk-temp"},
    )
    assert model.status_code == 200
    model_id = model.json()["data"]["id"]

    connection = sqlite3.connect(app_home / "askdata.db")
    connection.execute(
        "UPDATE aigc_datasource SET password = ? WHERE id = ?",
        ("legacy-pass", datasource_id),
    )
    connection.execute(
        "UPDATE aigc_model SET api_key = ? WHERE id = ?",
        ("sk-legacy-plaintext-9999", model_id),
    )
    connection.commit()
    connection.close()

    tested = await client.post(f"/api/v1/datasources/{datasource_id}/test", headers=_headers())
    assert tested.status_code == 200
    fetched = await client.get(f"/api/v1/aigc/models/{model_id}", headers=_headers())
    assert fetched.status_code == 200
    masked = fetched.json()["data"]["api_key"]
    assert masked == "sk-****9999"
    assert "sk-legacy-plaintext-9999" not in fetched.text

    connection = sqlite3.connect(app_home / "askdata.db")
    password = connection.execute(
        "SELECT password FROM aigc_datasource WHERE id = ?",
        (datasource_id,),
    ).fetchone()[0]
    api_key = connection.execute(
        "SELECT api_key FROM aigc_model WHERE id = ?",
        (model_id,),
    ).fetchone()[0]
    connection.close()
    assert password.startswith(PREFIX)
    assert open_secret(password) == ("legacy-pass", False)
    assert api_key.startswith(PREFIX)
    assert open_secret(api_key) == ("sk-legacy-plaintext-9999", False)
