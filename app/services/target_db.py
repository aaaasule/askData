"""Connect, introspect, and run guarded SQL against a datasource.

SQLite uses the builtin aiosqlite driver. PostgreSQL and MySQL use SQLAlchemy
plus asyncpg / aiomysql when `askdata[db]` is installed; otherwise the call
fails with an explicit driver error before a connection is attempted.
"""

from __future__ import annotations

import asyncio
import importlib.util
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

_POSTGRES = {"postgres", "postgresql"}
_MYSQL = {"mysql", "mariadb"}
_SQLITE = {"sqlite", "sqlite3"}


class DatasourceDriverError(RuntimeError):
    """The optional database driver for this db_type is not installed."""


class QueryTimeoutError(TimeoutError):
    """The read-only statement exceeded the configured timeout."""


class QueryExecutionError(RuntimeError):
    """The target database rejected or failed the statement."""


@dataclass(frozen=True)
class ConnInfo:
    db_type: str
    host: str = ""
    port: int | None = None
    database: str = ""
    username: str = ""
    password: str = ""
    jdbc_url: str | None = None


def ensure_driver(db_type: str) -> None:
    normalized = (db_type or "").lower()
    if normalized in _POSTGRES:
        _require_module("asyncpg", "PostgreSQL requires asyncpg. Install it with: pip install 'askdata[db]'")
    elif normalized in _MYSQL:
        _require_module("aiomysql", "MySQL requires aiomysql. Install it with: pip install 'askdata[db]'")


def dialect_name(db_type: str) -> str:
    normalized = (db_type or "").lower()
    if normalized in _MYSQL:
        return "mysql"
    if normalized in _POSTGRES:
        return "postgres"
    return "sqlite"


def build_async_url(info: ConnInfo) -> str:
    """Build a SQLAlchemy async URL from structured fields, else jdbc_url."""
    if not (info.database or info.host) and info.jdbc_url:
        return _url_from_jdbc(info.jdbc_url, info.db_type)
    normalized = (info.db_type or "").lower()
    if normalized in _SQLITE:
        return _sqlite_url(info.database or ":memory:")
    if normalized in _POSTGRES:
        drivername = "postgresql+asyncpg"
        default_port = 5432
    elif normalized in _MYSQL:
        drivername = "mysql+aiomysql"
        default_port = 3306
    else:
        raise DatasourceDriverError(f"unsupported db_type: {info.db_type}")
    url = URL.create(
        drivername,
        username=info.username or None,
        password=info.password or None,
        host=info.host or None,
        port=info.port or default_port,
        database=info.database or None,
    )
    return url.render_as_string(hide_password=False)


async def probe_connection(info: ConnInfo) -> dict[str, Any]:
    """Run `SELECT 1`. Connection failures return ok=false instead of raising."""
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
    normalized = (db_type or "").lower()
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


def _sqlite_url(path: str) -> str:
    if path in {"", ":memory:"}:
        return "sqlite+aiosqlite:///:memory:"
    return URL.create("sqlite+aiosqlite", database=path).render_as_string(hide_password=False)


def _url_from_jdbc(jdbc_url: str, db_type: str) -> str:
    raw = jdbc_url.strip()
    if raw.startswith("jdbc:sqlite:"):
        return _sqlite_url(raw[len("jdbc:sqlite:") :])
    if raw.startswith("jdbc:"):
        raise DatasourceDriverError("jdbc_url is not a SQLAlchemy URL; set host, database, and db_type")
    return _ensure_async_driver(raw, db_type)


def _ensure_async_driver(url: str, db_type: str) -> str:
    if "+aiosqlite" in url or "+asyncpg" in url or "+aiomysql" in url:
        return url
    normalized = (db_type or "").lower()
    if url.startswith("sqlite"):
        return "sqlite+aiosqlite" + url[len("sqlite") :]
    if normalized in _POSTGRES or url.startswith("postgres"):
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url[len("postgresql://") :]
        if url.startswith("postgresql+"):
            rest = url.split("://", 1)[1]
            return "postgresql+asyncpg://" + rest
    if (normalized in _MYSQL or url.startswith("mysql")) and "://" in url:
        rest = url.split("://", 1)[1]
        return "mysql+aiomysql://" + rest
    return url


def _require_module(module: str, message: str) -> None:
    if importlib.util.find_spec(module) is None:
        raise DatasourceDriverError(message)


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
