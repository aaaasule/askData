"""Datasource CRUD, connection test, introspect, and read-only query."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import AigcDatasource
from app.schemas.datasource import DatasourceOut
from app.security.secrets import SecretError, open_secret, seal_secret
from app.services.catalog import authorized_tables
from app.services.sql_guard import clamp_execution_limits, prepare_read_only_sql
from app.services.target_db import (
    ConnInfo,
    QueryExecutionError,
    QueryTimeoutError,
    dialect_name,
    execute_select,
    introspect_schema,
    probe_connection,
)

_UPDATABLE = {
    "name",
    "db_type",
    "host",
    "port",
    "database",
    "username",
    "password",
    "jdbc_url",
    "extra",
    "structure_json",
}


class DatasourceNotFoundError(LookupError):
    """No datasource row for the given id."""


class DatasourceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(AigcDatasource).order_by(AigcDatasource.created_at.desc(), AigcDatasource.id)
        )
        return [_to_out(row) for row in result.scalars().all()]

    async def get(self, datasource_id: str) -> dict[str, Any] | None:
        row = await self._get_row(datasource_id)
        if row is None:
            return None
        return _to_out(row)

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = AigcDatasource(
            name=payload["name"],
            db_type=payload.get("db_type") or "sqlite",
            host=payload.get("host") or "",
            port=payload.get("port"),
            database=payload.get("database") or "",
            username=payload.get("username") or "",
            password=seal_secret(payload.get("password") or ""),
            jdbc_url=payload.get("jdbc_url"),
            extra=payload.get("extra"),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return _to_out(row)

    async def update(self, datasource_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = await self._require(datasource_id)
        for key, value in payload.items():
            if key not in _UPDATABLE:
                continue
            if key == "password":
                row.password = seal_secret("" if value is None else str(value))
                continue
            setattr(row, key, value)
        row.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(row)
        return _to_out(row)

    async def delete(self, datasource_id: str) -> None:
        row = await self._require(datasource_id)
        await self.session.delete(row)
        await self.session.commit()

    async def test_connection(
        self,
        datasource_id: str | None,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if datasource_id:
            row = await self._require(datasource_id)
            try:
                info = await self._conn_from_row(row)
            except SecretError as exc:
                return {"ok": False, "message": str(exc), "latency_ms": None}
            return await probe_connection(info)
        if not payload:
            return {"ok": False, "message": "missing connection payload", "latency_ms": None}
        return await probe_connection(_conn_from_payload(payload))

    async def introspect(self, datasource_id: str) -> dict[str, Any]:
        row = await self._require(datasource_id)
        structure = await introspect_schema(await self._conn_from_row(row))
        row.structure_json = structure
        row.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(row)
        return structure

    async def get_structure(self, datasource_id: str) -> dict[str, Any] | None:
        row = await self._require(datasource_id)
        return row.structure_json

    async def save_structure(self, datasource_id: str, structure: dict[str, Any]) -> dict[str, Any]:
        """Replace structure_json only. Connection fields stay untouched."""
        row = await self._require(datasource_id)
        row.structure_json = structure
        row.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(row)
        return row.structure_json or {}

    async def execute_read_only_query(
        self,
        datasource_id: str,
        sql: str,
        allowed_tables: set[str],
        max_rows: int = 200,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        """Return {columns, rows, row_count, sql} after sql_guard checks.

        `analysis_runtime` can call this once the NL→SQL loop exists.
        """
        row = await self._require(datasource_id)
        settings = get_settings()
        capped_rows, capped_timeout = clamp_execution_limits(
            max_rows,
            timeout_seconds,
            max_rows_cap=settings.sql_max_rows,
            timeout_cap=settings.sql_timeout_seconds,
        )
        safe_sql = prepare_read_only_sql(
            sql,
            allowed_tables,
            max_rows=capped_rows,
            dialect=dialect_name(row.db_type),
        )
        return await execute_select(
            await self._conn_from_row(row),
            safe_sql,
            max_rows=capped_rows,
            timeout_seconds=capped_timeout,
        )

    async def _get_row(self, datasource_id: str) -> AigcDatasource | None:
        return await self.session.get(AigcDatasource, datasource_id)

    async def _require(self, datasource_id: str) -> AigcDatasource:
        row = await self._get_row(datasource_id)
        if row is None:
            raise DatasourceNotFoundError(datasource_id)
        return row

    async def _conn_from_row(self, row: AigcDatasource) -> ConnInfo:
        password = _reveal_password(row)
        if row in self.session.dirty:
            row.updated_at = datetime.now(UTC)
            await self.session.commit()
        return ConnInfo(
            db_type=row.db_type,
            host=row.host or "",
            port=row.port,
            database=row.database or "",
            username=row.username or "",
            password=password,
            jdbc_url=row.jdbc_url,
        )


def enabled_table_names(structure: dict[str, Any] | None) -> set[str]:
    """Tables marked imported and enabled inside structure_json."""
    names: set[str] = set()
    for table in authorized_tables(structure):
        name = table.get("name") or table.get("tableName")
        if name:
            names.add(str(name))
    return names


def _to_out(row: AigcDatasource) -> dict[str, Any]:
    return DatasourceOut.model_validate(row).model_dump(mode="json")


def _reveal_password(row: AigcDatasource) -> str:
    plain, legacy = open_secret(row.password or "")
    if legacy and row.password:
        row.password = seal_secret(plain)
    return plain


def _conn_from_payload(payload: dict[str, Any]) -> ConnInfo:
    return ConnInfo(
        db_type=str(payload.get("db_type") or "sqlite"),
        host=str(payload.get("host") or ""),
        port=payload.get("port"),
        database=str(payload.get("database") or ""),
        username=str(payload.get("username") or ""),
        password=str(payload.get("password") or ""),
        jdbc_url=payload.get("jdbc_url"),
    )


__all__ = [
    "DatasourceNotFoundError",
    "DatasourceService",
    "QueryExecutionError",
    "QueryTimeoutError",
    "enabled_table_names",
]
