"""Oracle and SQL Server URLs, driver hints, and mocked read-only execution."""

from __future__ import annotations

import importlib.util

import pytest

from app.services.db_url import (
    ConnInfo,
    apply_driver_timeout,
    build_async_url,
    dialect_name,
    ensure_driver,
)
from app.services.target_db import (
    DatasourceDriverError,
    execute_select,
    introspect_schema,
    probe_connection,
)


def test_structured_urls_follow_langchat_shapes() -> None:
    oracle = build_async_url(
        ConnInfo(
            db_type="oracle",
            host="db.internal",
            port=1521,
            database="FREEPDB1",
            username="app",
            password="secret",
        )
    )
    assert oracle.startswith("oracle+oracledb://app:secret@db.internal:1521")
    assert "service_name=FREEPDB1" in oracle

    jdbc_oracle = build_async_url(
        ConnInfo(
            db_type="oracle",
            username="app",
            password="secret",
            jdbc_url="jdbc:oracle:thin:@//db.internal:1521/FREEPDB1",
        )
    )
    assert "service_name=FREEPDB1" in jdbc_oracle
    assert jdbc_oracle.startswith("oracle+oracledb://")

    sid = build_async_url(
        ConnInfo(
            db_type="oracle",
            username="app",
            password="pw",
            jdbc_url="jdbc:oracle:thin:@db.internal:1521:ORCL",
        )
    )
    assert sid.startswith("oracle+oracledb://app:pw@db.internal:1521/ORCL")

    mssql = build_async_url(
        ConnInfo(
            db_type="sql_server",
            host="sql.internal",
            database="Adventure",
            username="app",
            password="pw",
        )
    )
    assert mssql.startswith("mssql+aioodbc://app:pw@sql.internal:1433/Adventure")
    assert "ODBC+Driver+18+for+SQL+Server" in mssql or "ODBC%20Driver%2018" in mssql
    assert "Encrypt=no" in mssql
    assert "TrustServerCertificate=yes" in mssql

    jdbc_mssql = build_async_url(
        ConnInfo(
            db_type="mssql",
            username="app",
            password="pw",
            jdbc_url=(
                "jdbc:sqlserver://sql.internal:1433;encrypt=false;"
                "trustServerCertificate=true;databaseName=Adventure"
            ),
        )
    )
    assert jdbc_mssql.startswith("mssql+aioodbc://app:pw@sql.internal:1433/Adventure")
    assert dialect_name("oracle") == "oracle"
    assert dialect_name("mssql") == "tsql"
    assert dialect_name("postgres") == "postgres"

    mysql = build_async_url(
        ConnInfo(db_type="mysql", host="localhost", database="app", username="u", password="p")
    )
    assert mysql.startswith("mysql+aiomysql://u:p@localhost:3306/app")


def test_missing_optional_drivers(monkeypatch: pytest.MonkeyPatch) -> None:
    real = importlib.util.find_spec

    def find_spec(name: str):
        if name in {"oracledb", "aioodbc", "asyncpg", "aiomysql"}:
            return None
        return real(name)

    monkeypatch.setattr("app.services.db_url.importlib.util.find_spec", find_spec)
    with pytest.raises(DatasourceDriverError, match="askdata\\[db-oracle\\]"):
        ensure_driver("oracle")
    with pytest.raises(DatasourceDriverError, match="askdata\\[db-mssql\\]"):
        ensure_driver("SQL Server")
    ensure_driver("sqlite")


def test_driver_timeout_attributes() -> None:
    oracle = type("Driver", (), {"call_timeout": 0})()
    apply_driver_timeout(oracle, "oracle", 3)
    assert oracle.call_timeout == 3000
    mssql = type("Driver", (), {"timeout": 0})()
    apply_driver_timeout(mssql, "sqlserver", 4)
    assert mssql.timeout == 4
    apply_driver_timeout(object(), "oracle", 1)


class _Result:
    def keys(self):
        return ["n"]

    def mappings(self):
        return self

    def fetchmany(self, count: int):
        assert count == 2
        return [{"n": 1}]


class _Conn:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.driver = type("Driver", (), {"call_timeout": 0, "timeout": 0})()

    async def execute(self, statement):
        self.statements.append(str(statement))
        return _Result()

    async def exec_driver_sql(self, sql: str):
        self.statements.append(sql)

    async def rollback(self):
        self.statements.append("rollback")

    async def get_raw_connection(self):
        return type("Raw", (), {"driver_connection": self.driver})()

    async def run_sync(self, fn, *args):
        return fn(self, *args)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _Engine:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    def connect(self):
        return self.conn

    async def dispose(self):
        return None


def _patch_engine(monkeypatch: pytest.MonkeyPatch, conn: _Conn, urls: list[str]) -> None:
    monkeypatch.setattr("app.services.target_db.ensure_driver", lambda _db_type: None)

    def create(url, **_kwargs):
        urls.append(str(url))
        return _Engine(conn)

    monkeypatch.setattr("app.services.target_db.create_async_engine", create)


async def test_oracle_probe_introspect_and_select_do_not_need_a_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _Conn()
    urls: list[str] = []
    _patch_engine(monkeypatch, conn, urls)
    info = ConnInfo(
        db_type="oracle",
        host="db.internal",
        database="FREEPDB1",
        username="app",
        password="secret",
    )
    probed = await probe_connection(info)
    assert probed["ok"] is True
    assert conn.statements == ["SELECT 1"]
    assert urls[0].startswith("oracle+oracledb://")

    monkeypatch.setattr(
        "app.services.target_db._reflect_tables",
        lambda _sync: [
            {
                "name": "ORDERS",
                "comment": None,
                "imported": True,
                "enabled": True,
                "columns": [],
            }
        ],
    )
    schema = await introspect_schema(info)
    assert schema["tables"][0]["name"] == "ORDERS"

    conn.statements.clear()
    selected = await execute_select(info, "SELECT 1 AS n FROM dual", max_rows=2, timeout_seconds=5)
    assert selected["columns"] == ["n"]
    assert selected["rows"] == [{"n": 1}]
    assert "rollback" in conn.statements
    assert conn.driver.call_timeout == 5000


async def test_sqlserver_select_sets_client_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn()
    urls: list[str] = []
    _patch_engine(monkeypatch, conn, urls)
    info = ConnInfo(db_type="mssql", host="sql.internal", database="app", username="u", password="p")
    await execute_select(info, "SELECT 1 AS n", max_rows=2, timeout_seconds=6)
    assert urls[0].startswith("mssql+aioodbc://")
    assert conn.driver.timeout == 6
    assert "rollback" in conn.statements
