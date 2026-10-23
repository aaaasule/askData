"""Datasource CRUD, connect test, introspect, structure — stubs."""

from __future__ import annotations

from typing import Any


class DatasourceService:
    """TODO: wire AsyncSession + drivers (asyncpg / aiomysql / etc.)."""

    async def list_all(self) -> list[dict[str, Any]]:
        return []

    async def get(self, datasource_id: str) -> dict[str, Any] | None:
        _ = datasource_id
        return None

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        _ = payload
        raise NotImplementedError("create datasource")

    async def update(self, datasource_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ = datasource_id, payload
        raise NotImplementedError("update datasource")

    async def delete(self, datasource_id: str) -> None:
        _ = datasource_id
        raise NotImplementedError("delete datasource")

    async def test_connection(self, datasource_id: str | None, payload: dict[str, Any] | None) -> dict[str, Any]:
        _ = datasource_id, payload
        return {"ok": False, "message": "not implemented"}

    async def introspect(self, datasource_id: str) -> dict[str, Any]:
        _ = datasource_id
        raise NotImplementedError("introspect")

    async def get_structure(self, datasource_id: str) -> dict[str, Any] | None:
        _ = datasource_id
        return None

    async def execute_read_only_query(
        self,
        datasource_id: str,
        sql: str,
        allowed_tables: set[str],
        max_rows: int = 200,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        """Return {columns, rows, row_count, sql} after sql_guard checks."""
        _ = datasource_id, sql, allowed_tables, max_rows, timeout_seconds
        raise NotImplementedError("execute_read_only_query")
