"""Catalog keeps imported and enabled tables from structure_json."""

from __future__ import annotations

from httpx import AsyncClient

from app.services.catalog import authorized_tables, build_catalog

_STRUCTURE = {
    "tables": [
        {
            "name": "orders",
            "comment": "订单",
            "imported": True,
            "enabled": True,
            "columns": [{"name": "id", "type": "INTEGER"}],
        },
        {"name": "secrets", "imported": True, "enabled": False, "columns": []},
        {"name": "draft", "imported": False, "enabled": True, "columns": []},
        {"name": "off", "imported": "true", "enabled": "false", "columns": []},
        {"tableName": "legacy", "columns": [{"name": "x", "type": "TEXT"}]},
        {"comment": "nameless", "imported": True, "enabled": True},
    ]
}


def test_catalog_parsing_keeps_authorized_tables_only() -> None:
    names = [table.get("name") or table.get("tableName") for table in authorized_tables(_STRUCTURE)]
    assert names == ["orders", "legacy"]

    catalog = build_catalog("ds-1", _STRUCTURE)
    assert catalog["datasourceId"] == "ds-1"
    assert [table["name"] for table in catalog["tables"]] == ["orders", "legacy"]
    assert catalog["tables"][0]["comment"] == "订单"
    assert catalog["tables"][0]["imported"] is True
    assert catalog["tables"][0]["enabled"] is True
    assert catalog["tables"][0]["columns"][0]["name"] == "id"
    assert build_catalog("ds-1", None)["tables"] == []


async def test_catalog_endpoint_reads_saved_structure(client: AsyncClient) -> None:
    headers = {"X-API-Key": "test-key"}
    created = await client.post(
        "/api/v1/datasources",
        headers=headers,
        json={"name": "biz", "db_type": "sqlite", "database": "/tmp/unused.db"},
    )
    datasource_id = created.json()["data"]["id"]
    updated = await client.put(
        f"/api/v1/datasources/{datasource_id}",
        headers=headers,
        json={"structure_json": _STRUCTURE},
    )
    assert updated.status_code == 200

    listed = await client.get(
        "/api/v1/core/data-analysis/catalog",
        headers=headers,
        params={"datasourceId": datasource_id},
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["code"] == "SUCCESS"
    assert [table["name"] for table in body["data"]["tables"]] == ["orders", "legacy"]

    missing = await client.get(
        "/api/v1/core/data-analysis/catalog",
        headers=headers,
        params={"datasourceId": "missing"},
    )
    assert missing.status_code == 404

    anonymous = await client.get(
        "/api/v1/core/data-analysis/catalog",
        params={"datasourceId": datasource_id},
    )
    assert anonymous.status_code == 401
