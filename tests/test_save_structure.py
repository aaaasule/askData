"""PUT /datasources/{id}/structure saves table authorization without a full update."""

from __future__ import annotations

import json
import sqlite3

from httpx import AsyncClient

from app.security.secrets import open_secret


def _headers() -> dict[str, str]:
    return {"X-API-Key": "test-key"}


async def _create(client: AsyncClient) -> str:
    created = await client.post(
        "/api/v1/datasources",
        headers=_headers(),
        json={
            "name": "orders-db",
            "db_type": "sqlite",
            "host": "localhost",
            "database": "/tmp/orders.db",
            "username": "reader",
            "password": "s3cret",
        },
    )
    assert created.status_code == 200
    return created.json()["data"]["id"]


def _stored_password(app_home, datasource_id: str) -> str:
    connection = sqlite3.connect(app_home / "askdata.db")
    try:
        row = connection.execute(
            "SELECT password FROM aigc_datasource WHERE id = ?",
            (datasource_id,),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    return row[0]


async def test_put_structure_accepts_langchat_json_string(client: AsyncClient, app_home) -> None:
    datasource_id = await _create(client)
    payload = {
        "tables": [
            {
                "tableName": "orders",
                "tableComment": "订单",
                "imported": True,
                "enabled": True,
                "columns": [{"name": "id", "type": "INTEGER"}],
            },
            {
                "tableName": "secrets",
                "imported": True,
                "enabled": False,
                "columns": [{"name": "token", "type": "TEXT"}],
            },
        ]
    }

    saved = await client.put(
        f"/api/v1/datasources/{datasource_id}/structure",
        headers=_headers(),
        json={"structureJson": json.dumps(payload, ensure_ascii=False)},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["code"] == "SUCCESS"
    assert body["data"]["tables"][0]["tableName"] == "orders"

    fetched = await client.get(
        f"/api/v1/datasources/{datasource_id}/structure",
        headers=_headers(),
    )
    assert fetched.status_code == 200
    assert fetched.json()["data"]["tables"][1]["enabled"] is False

    detail = await client.get(f"/api/v1/datasources/{datasource_id}", headers=_headers())
    item = detail.json()["data"]
    assert item["name"] == "orders-db"
    assert item["database"] == "/tmp/orders.db"
    assert item["username"] == "reader"
    assert "password" not in item
    stored_password = _stored_password(app_home, datasource_id)
    assert stored_password != "s3cret"
    assert open_secret(stored_password)[0] == "s3cret"

    catalog = await client.get(
        "/api/v1/core/data-analysis/catalog",
        headers=_headers(),
        params={"datasourceId": datasource_id},
    )
    names = {table["name"] for table in catalog.json()["data"]["tables"]}
    assert names == {"orders"}


async def test_put_structure_accepts_object_and_snake_case(client: AsyncClient) -> None:
    datasource_id = await _create(client)
    structure = {"tables": [{"name": "orders", "imported": True, "enabled": True, "columns": []}]}
    saved = await client.put(
        f"/api/v1/datasources/{datasource_id}/structure",
        headers=_headers(),
        json={"structure_json": structure},
    )
    assert saved.status_code == 200
    assert saved.json()["data"] == structure

    replaced = await client.put(
        f"/api/v1/datasources/{datasource_id}/structure",
        headers=_headers(),
        json={"structureJson": {"tables": []}},
    )
    assert replaced.status_code == 200
    assert replaced.json()["data"] == {"tables": []}


async def test_put_structure_rejects_bad_json_missing_and_anonymous(
    client: AsyncClient,
) -> None:
    datasource_id = await _create(client)

    invalid = await client.put(
        f"/api/v1/datasources/{datasource_id}/structure",
        headers=_headers(),
        json={"structureJson": "not-json"},
    )
    assert invalid.status_code == 400

    not_object = await client.put(
        f"/api/v1/datasources/{datasource_id}/structure",
        headers=_headers(),
        json={"structureJson": "[1, 2]"},
    )
    assert not_object.status_code == 400

    missing = await client.put(
        "/api/v1/datasources/missing-id/structure",
        headers=_headers(),
        json={"structureJson": {"tables": []}},
    )
    assert missing.status_code == 404

    anonymous = await client.put(
        f"/api/v1/datasources/{datasource_id}/structure",
        json={"structureJson": {"tables": []}},
    )
    assert anonymous.status_code == 401
