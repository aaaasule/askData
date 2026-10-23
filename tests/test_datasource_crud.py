"""SQLite smoke: Alembic schema + datasource CRUD persists through the API."""

from __future__ import annotations

from httpx import AsyncClient


def _headers() -> dict[str, str]:
    return {"X-API-Key": "test-key"}


async def test_datasource_crud_persists(client: AsyncClient) -> None:
    missing = await client.get("/api/v1/datasources", headers=_headers())
    assert missing.status_code == 200
    body = missing.json()
    assert body["code"] == "SUCCESS"
    assert body["data"] == []

    unauth = await client.get("/api/v1/datasources")
    assert unauth.status_code == 401

    created = await client.post(
        "/api/v1/datasources",
        headers=_headers(),
        json={
            "name": "local",
            "db_type": "sqlite",
            "database": "/tmp/biz.db",
            "username": "unused",
            "password": "s3cret",
        },
    )
    assert created.status_code == 200
    created_body = created.json()
    assert created_body["code"] == "SUCCESS"
    item = created_body["data"]
    assert item["name"] == "local"
    assert item["db_type"] == "sqlite"
    assert item["id"]
    assert "password" not in item

    datasource_id = item["id"]

    listed = await client.get("/api/v1/datasources", headers=_headers())
    assert listed.json()["data"][0]["id"] == datasource_id

    fetched = await client.get(f"/api/v1/datasources/{datasource_id}", headers=_headers())
    assert fetched.status_code == 200
    assert fetched.json()["data"]["database"] == "/tmp/biz.db"

    updated = await client.put(
        f"/api/v1/datasources/{datasource_id}",
        headers=_headers(),
        json={"name": "renamed"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "renamed"
    assert "password" not in updated.json()["data"]

    deleted = await client.delete(
        f"/api/v1/datasources/{datasource_id}",
        headers=_headers(),
    )
    assert deleted.status_code == 200
    assert deleted.json()["code"] == "SUCCESS"

    gone = await client.get(f"/api/v1/datasources/{datasource_id}", headers=_headers())
    assert gone.status_code == 404

    empty = await client.get("/api/v1/datasources", headers=_headers())
    assert empty.json()["data"] == []
