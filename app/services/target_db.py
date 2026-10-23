"""Connect, introspect, and run guarded SQL against a datasource.

SQLite uses the builtin aiosqlite driver. PostgreSQL and MySQL use SQLAlchemy
plus asyncpg / aiomysql when ``askdata[db]`` is installed. Oracle
(``askdata[db-oracle]``, python-oracledb) and SQL Server
(``askdata[db-mssql]``, aioodbc) follow the same path and fail with an
explicit driver error before a connection is attempted.

Oracle and SQL Server have no portable session-level ``READ ONLY`` that is
safe to send before the first statement. Writes are still rejected by
``sql_guard``, the transaction is rolled back, and the client timeout is
applied when the driver exposes one.
"""

from __future__ import annotations

import asyncio
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.services.db_url import (
    ConnInfo,
    DatasourceDriverError,
    apply_driver_timeout,
    build_async_url,
    dialect_name,
    ensure_driver,
    normalize_db_type,
)

_POSTGRES = {"postgres"}
_MYSQL = {"mysql"}
_SQLITE = {"sqlite"}
_ORACLE = {"oracle"}
_SQLSERVER = {"sqlserver"}


class QueryTimeoutError(TimeoutError):
    """The read-only statement exceeded the configured timeout."""


class QueryExecutionError(RuntimeError):
    """The target database rejected or failed the statement."""


async def probe_connection(info: ConnInfo) -> dict[str, Any]:
    """Run ``SELECT 1``. Connection failures return ok=false instead of raising."""
    started = time.perf_counter()
    try:
        ensure_driver(info.db_type)
        engine = create_async_engine(build_async_url(info), poolclass=NullPool)
    except (DatasourceDriverError, SQLAlchemyError, OSError, ValueError) as exc:
        return {"ok": False, "message": _public_error(exc, info), "latency_ms": None}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        return {"ok": False, "message": _public_error(exc, info), "latency_ms": None}
    finally:
        await engine.dispose()
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {"ok": True, "message": "connected", "latency_ms": latency_ms}


async def introspect_schema(info: ConnInfo) -> dict[str, Any]:
    """Reflect user tables and columns. SQLite internal tables are skipped."""
    ensure_driver(info.db_type)
    engine = create_async_engine(build_async_url(info), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            tables = await conn.run_sync(_reflect_tables)
    except SQLAlchemyError as exc:
        raise QueryExecutionError(_public_error(exc, info)) from exc
    finally:
        await engine.dispose()
    return {"tables": tables}


async def execute_select(
    info: ConnInfo,
    sql: str,
    *,
    max_rows: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Execute already-guarded SQL and return columns, rows, row_count, sql."""
    ensure_driver(info.db_type)
    engine = create_async_engine(build_async_url(info), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await _apply_readonly_session(conn, info.db_type, timeout_seconds)
            try:
                result = await _execute_with_timeout(conn, sql, timeout_seconds)
            except TimeoutError as exc:
                raise QueryTimeoutError(f"query exceeded {timeout_seconds}s") from exc
            columns = list(result.keys())
            materialised = result.mappings().fetchmany(max_rows)
            rows = [{key: _jsonable(value) for key, value in row.items()} for row in materialised]
            await conn.rollback()
            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "sql": sql,
            }
    except (QueryTimeoutError, QueryExecutionError):
        raise
    except SQLAlchemyError as exc:
        if "interrupted" in str(exc).lower():
            raise QueryTimeoutError(f"query exceeded {timeout_seconds}s") from exc
        raise QueryExecutionError(_public_error(exc, info)) from exc
    finally:
        await engine.dispose()


async def _execute_with_timeout(conn: Any, sql: str, timeout_seconds: int) -> Any:
    return await asyncio.wait_for(conn.execute(text(sql)), timeout=timeout_seconds)


async def _apply_readonly_session(conn: Any, db_type: str, timeout_seconds: int) -> None:
    normalized = normalize_db_type(db_type)
    timeout_ms = int(timeout_seconds) * 1000
    if normalized in _SQLITE:
        await conn.exec_driver_sql("PRAGMA query_only = ON")
        await _install_sqlite_progress_handler(conn, timeout_seconds)
        return
    if normalized in _POSTGRES:
        await conn.exec_driver_sql("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        await conn.exec_driver_sql(f"SET statement_timeout = {timeout_ms}")
        return
    if normalized in _MYSQL:
        await conn.exec_driver_sql("SET SESSION TRANSACTION READ ONLY")
        await conn.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {timeout_ms}")
        return
    if normalized in _ORACLE or normalized in _SQLSERVER:
        await _apply_driver_timeout(conn, normalized, timeout_seconds)


async def _apply_driver_timeout(conn: Any, db_type: str, timeout_seconds: int) -> None:
    getter = getattr(conn, "get_raw_connection", None)
    if getter is None:
        return
    try:
        raw = await getter()
    except (SQLAlchemyError, OSError, AttributeError, TypeError):
        return
    driver = getattr(raw, "driver_connection", None)
    apply_driver_timeout(driver, db_type, timeout_seconds)


async def _install_sqlite_progress_handler(conn: Any, timeout_seconds: int) -> None:
    """Abort a long SQLite query from the aiosqlite thread once the deadline passes."""
    raw = await conn.get_raw_connection()
    driver = getattr(raw, "driver_connection", None)
    setter = getattr(driver, "set_progress_handler", None)
    if setter is None:
        return
    deadline = time.monotonic() + timeout_seconds

    def progress() -> int:
        return 1 if time.monotonic() >= deadline else 0

    await setter(progress, 1000)


def _reflect_tables(sync_conn: Any) -> list[dict[str, Any]]:
    inspector = inspect(sync_conn)
    reflected: list[dict[str, Any]] = []
    for name in inspector.get_table_names():
        if name.startswith("sqlite_"):
            continue
        columns = [
            {
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": bool(column.get("nullable", True)),
                "comment": column.get("comment"),
            }
            for column in inspector.get_columns(name)
        ]
        comment = _table_comment(inspector, name)
        reflected.append(
            {
                "name": name,
                "comment": comment,
                "imported": True,
                "enabled": True,
                "columns": columns,
            }
        )
    return reflected


def _table_comment(inspector: Any, name: str) -> str | None:
    try:
        payload = inspector.get_table_comment(name)
    except (NotImplementedError, SQLAlchemyError):
        return None
    if not payload:
        return None
    return payload.get("text")


def _public_error(exc: Exception, info: ConnInfo) -> str:
    message = str(exc)
    if info.password:
        message = message.replace(info.password, "***")
    return message


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


__all__ = [
    "ConnInfo",
    "DatasourceDriverError",
    "QueryExecutionError",
    "QueryTimeoutError",
    "build_async_url",
    "dialect_name",
    "ensure_driver",
    "execute_select",
    "introspect_schema",
    "probe_connection",
]
