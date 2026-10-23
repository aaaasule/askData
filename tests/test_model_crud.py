"""aigc_model CRUD. List and get never return the raw api_key."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from httpx import AsyncClient


def _headers() -> dict[str, str]:
    return {"X-API-Key": "test-key"}


def _stored_key(app_home: Path) -> str:
    conn = sqlite3.connect(app_home / "askdata.db")
    try:
        row = conn.execute("SELECT api_key FROM aigc_model").fetchone()
    finally:
        conn.close()
    assert row is not None
    return str(row[0])


async def test_model_crud_masks_api_key(client: AsyncClient, app_home: Path) -> None:
    secret = "sk-test-secret-value"
    unauth = await client.get("/api/v1/aigc/models")
    assert unauth.status_code == 401

    empty = await client.get("/api/v1/aigc/models", headers=_headers())
    assert empty.status_code == 200
    assert empty.json()["data"] == []

    created = await client.post(
        "/api/v1/aigc/models",
        headers=_headers(),
        json={
            "name": "默认对话",
            "provider": "openai-compatible",
            "model": "gpt-4o-mini",
            "type": "chat",
            "base_url": "https://api.example/v1",
            "endpoint": "",
            "api_key": secret,
            "temperature": 0.2,
            "top_p": 0.9,
            "max_token": 1024,
            "config_json": {"timeout": 30},
            "enabled": True,
        },
    )
    assert created.status_code == 200
    item = created.json()["data"]
    assert item["model"] == "gpt-4o-mini"
    assert item["model_name"] == "gpt-4o-mini"
    assert item["type"] == "chat"
    assert item["temperature"] == 0.2
    assert item["top_p"] == 0.9
    assert item["max_token"] == 1024
    assert item["config_json"] == {"timeout": 30}
    assert item["api_key"] != secret
    assert item["api_key"].startswith("sk-")
    assert "****" in item["api_key"]
    assert secret not in created.text
    model_id = item["id"]
    assert _stored_key(app_home) == secret

    listed = await client.get("/api/v1/aigc/models", headers=_headers())
    assert secret not in listed.text
    assert listed.json()["data"][0]["id"] == model_id

    fetched = await client.get(f"/api/v1/aigc/models/{model_id}", headers=_headers())
    assert fetched.status_code == 200
    assert secret not in fetched.text
    assert fetched.json()["data"]["base_url"] == "https://api.example/v1"

    echoed = await client.put(
        f"/api/v1/aigc/models/{model_id}",
        headers=_headers(),
        json={"name": "已改名", "api_key": item["api_key"]},
    )
    assert echoed.status_code == 200
    assert echoed.json()["data"]["name"] == "已改名"
    assert secret not in echoed.text
    assert _stored_key(app_home) == secret

    rotated = "sk-rotated-new-value"
    updated = await client.put(
        f"/api/v1/aigc/models/{model_id}",
        headers=_headers(),
        json={"api_key": rotated, "enabled": False},
    )
    assert rotated not in updated.text
    assert updated.json()["data"]["enabled"] is False
    assert _stored_key(app_home) == rotated

    missing = await client.get("/api/v1/aigc/models/missing", headers=_headers())
    assert missing.status_code == 404

    deleted = await client.delete(f"/api/v1/aigc/models/{model_id}", headers=_headers())
    assert deleted.status_code == 200
    assert deleted.json()["code"] == "SUCCESS"
    gone = await client.get(f"/api/v1/aigc/models/{model_id}", headers=_headers())
    assert gone.status_code == 404


async def test_create_model_requires_model_id(client: AsyncClient) -> None:
    rejected = await client.post(
        "/api/v1/aigc/models",
        headers=_headers(),
        json={"name": "no-model"},
    )
    assert rejected.status_code == 422
