"""Read-only query against a SQLite datasource: rows in, writes out."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from httpx import AsyncClient


def _seed_business_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO orders (id, name) VALUES (1, 'alpha')")
    conn.execute("INSERT INTO orders (id, name) VALUES (2, 'beta')")
    conn.commit()
    conn.close()


async def test_readonly_query_returns_rows_and_rejects_writes(
    client: AsyncClient, app_home: Path
) -> None:
    biz = app_home / "biz.db"
    _seed_business_db(biz)
    headers = {"X-API-Key": "test-key"}

    created = await client.post(
        "/api/v1/datasources",
        headers=headers,
        json={"name": "biz", "db_type": "sqlite", "database": str(biz)},
    )
    assert created.status_code == 200
    datasource_id = created.json()["data"]["id"]

    introspected = await client.post(
        f"/api/v1/datasources/{datasource_id}/introspect",
        headers=headers,
    )
    assert introspected.status_code == 200
    tables = introspected.json()["data"]["tables"]
    names = {table["name"] for table in tables}
    assert "orders" in names
    orders = next(table for table in tables if table["name"] == "orders")
    columns = {col["name"] for col in orders["columns"]}
    assert {"id", "name"} <= columns

    queried = await client.post(
        f"/api/v1/datasources/{datasource_id}/query",
        headers=headers,
        json={"sql": "SELECT id, name FROM orders ORDER BY id", "tables": ["orders"]},
    )
    assert queried.status_code == 200
    payload = queried.json()
    assert payload["code"] == "SUCCESS"
    assert payload["data"]["row_count"] == 2
    assert payload["data"]["columns"] == ["id", "name"]
    assert payload["data"]["rows"][0]["name"] == "alpha"

    denied = await client.post(
        f"/api/v1/datasources/{datasource_id}/query",
        headers=headers,
        json={"sql": "DELETE FROM orders", "tables": ["orders"]},
    )
    assert denied.status_code == 400

    outside = await client.post(
        f"/api/v1/datasources/{datasource_id}/query",
        headers=headers,
        json={"sql": "SELECT * FROM sqlite_master", "tables": ["orders"]},
    )
    assert outside.status_code == 400

    check = sqlite3.connect(biz)
    remaining = check.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    check.close()
    assert remaining == 2


async def test_sqlite_query_times_out(client: AsyncClient, app_home: Path) -> None:
    biz = app_home / "slow.db"
    sqlite3.connect(biz).close()
    headers = {"X-API-Key": "test-key"}
    created = await client.post(
        "/api/v1/datasources",
        headers=headers,
        json={"name": "slow", "db_type": "sqlite", "database": str(biz)},
    )
    datasource_id = created.json()["data"]["id"]
    timed_out = await client.post(
        f"/api/v1/datasources/{datasource_id}/query",
        headers=headers,
        json={
            "sql": (
                "WITH RECURSIVE c(x) AS ("
                "SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 100000000"
                ") SELECT max(x) FROM c"
            ),
            "tables": [],
            "timeout_seconds": 1,
        },
    )
    assert timed_out.status_code == 408


async def test_connection_probe(client: AsyncClient, app_home: Path) -> None:
    biz = app_home / "empty.db"
    sqlite3.connect(biz).close()
    headers = {"X-API-Key": "test-key"}

    probed = await client.post(
        "/api/v1/datasources/test",
        headers=headers,
        json={"db_type": "sqlite", "database": str(biz)},
    )
    assert probed.status_code == 200
    assert probed.json()["data"]["ok"] is True
