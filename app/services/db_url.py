"""Async SQLAlchemy URLs for target databases.

URL shapes follow LangChat ``DatasourceType``: Oracle uses the thin service
form ``jdbc:oracle:thin:@//host:port/service``, SQL Server uses
``jdbc:sqlserver://host:port;databaseName=...``. Credentials stay on the
datasource fields (``username`` / ``password``), not inside the JDBC string.
"""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.engine import URL

_POSTGRES = {"postgres", "postgresql", "pg"}
_MYSQL = {"mysql", "mariadb"}
_SQLITE = {"sqlite", "sqlite3"}
_ORACLE = {"oracle"}
_SQLSERVER = {"sqlserver", "mssql"}

_JDBC_ORACLE_SERVICE = re.compile(
    r"^jdbc:oracle:thin:@//(?P<host>[^:/]+):(?P<port>\d+)/(?P<service>.+)$",
    re.IGNORECASE,
)
_JDBC_ORACLE_SID = re.compile(
    r"^jdbc:oracle:thin:@(?P<host>[^:/]+):(?P<port>\d+):(?P<sid>[^/;]+)$",
    re.IGNORECASE,
)
_JDBC_SQLSERVER = re.compile(
    r"^jdbc:sqlserver://(?P<server>[^;]+)(?P<props>;.*)?$",
    re.IGNORECASE,
)


class DatasourceDriverError(RuntimeError):
    """The optional database driver for this db_type is not installed."""


@dataclass(frozen=True)
class ConnInfo:
    db_type: str
    host: str = ""
    port: int | None = None
    database: str = ""
    username: str = ""
    password: str = ""
    jdbc_url: str | None = None


def normalize_db_type(db_type: str) -> str:
    text = (db_type or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if text in {"postgresql", "pg"}:
        return "postgres"
    if text == "sqlite3":
        return "sqlite"
    if text == "mssql":
        return "sqlserver"
    return text


def dialect_name(db_type: str) -> str:
    """sqlglot dialect used when rendering a guarded statement."""
    normalized = normalize_db_type(db_type)
    if normalized in _MYSQL:
        return "mysql"
    if normalized in _POSTGRES:
        return "postgres"
    if normalized in _ORACLE:
        return "oracle"
    if normalized in _SQLSERVER:
        return "tsql"
    return "sqlite"


def ensure_driver(db_type: str) -> None:
    normalized = normalize_db_type(db_type)
    if normalized in _POSTGRES:
        _require_module(
            "asyncpg",
            "PostgreSQL requires asyncpg. Install it with: pip install 'askdata[db]'",
        )
    elif normalized in _MYSQL:
        _require_module(
            "aiomysql",
            "MySQL requires aiomysql. Install it with: pip install 'askdata[db]'",
        )
    elif normalized in _ORACLE:
        _require_module(
            "oracledb",
            "Oracle requires oracledb. Install it with: pip install 'askdata[db-oracle]'",
        )
    elif normalized in _SQLSERVER:
        _require_module(
            "aioodbc",
            "SQL Server requires aioodbc. Install it with: pip install 'askdata[db-mssql]'",
        )


def build_async_url(info: ConnInfo) -> str:
    """Build a SQLAlchemy async URL from structured fields, else jdbc_url."""
    if not (info.database or info.host) and info.jdbc_url:
        return _url_from_jdbc(info)
    normalized = normalize_db_type(info.db_type)
    if normalized in _SQLITE:
        return _sqlite_url(info.database or ":memory:")
    if normalized in _POSTGRES:
        return _server_url(info, "postgresql+asyncpg", 5432)
    if normalized in _MYSQL:
        return _server_url(info, "mysql+aiomysql", 3306)
    if normalized in _ORACLE:
        return _oracle_service_url(info)
    if normalized in _SQLSERVER:
        return _sqlserver_url(info)
    raise DatasourceDriverError(f"unsupported db_type: {info.db_type}")


def apply_driver_timeout(driver: Any, db_type: str, timeout_seconds: int) -> None:
    """Best-effort client timeout. Oracle and SQL Server have no shared SET statement."""
    if driver is None:
        return
    normalized = normalize_db_type(db_type)
    try:
        if normalized in _ORACLE and hasattr(driver, "call_timeout"):
            driver.call_timeout = int(timeout_seconds) * 1000
        elif normalized in _SQLSERVER and hasattr(driver, "timeout"):
            driver.timeout = int(timeout_seconds)
    except (AttributeError, TypeError, ValueError):
        return


def _server_url(info: ConnInfo, drivername: str, default_port: int) -> str:
    url = URL.create(
        drivername,
        username=info.username or None,
        password=info.password or None,
        host=info.host or None,
        port=info.port or default_port,
        database=info.database or None,
    )
    return url.render_as_string(hide_password=False)


def _oracle_service_url(info: ConnInfo, *, port: int | None = None) -> str:
    """LangChat shape: ``jdbc:oracle:thin:@//host:port/database`` (service name)."""
    query = {"service_name": info.database} if info.database else None
    url = URL.create(
        "oracle+oracledb",
        username=info.username or None,
        password=info.password or None,
        host=info.host or None,
        port=port or info.port or 1521,
        query=query,
    )
    return url.render_as_string(hide_password=False)


def _oracle_sid_url(info: ConnInfo, sid: str, port: int) -> str:
    url = URL.create(
        "oracle+oracledb",
        username=info.username or None,
        password=info.password or None,
        host=info.host or None,
        port=port,
        database=sid,
    )
    return url.render_as_string(hide_password=False)


def _sqlserver_url(
    info: ConnInfo,
    *,
    port: int | None = None,
    encrypt: str = "no",
    trust: str = "yes",
) -> str:
    """LangChat shape: encrypt=false and trustServerCertificate=true by default."""
    url = URL.create(
        "mssql+aioodbc",
        username=info.username or None,
        password=info.password or None,
        host=info.host or None,
        port=port if port is not None else (info.port or 1433),
        database=info.database or None,
        query={
            "driver": "ODBC Driver 18 for SQL Server",
            "Encrypt": _odbc_flag(encrypt, default="no"),
            "TrustServerCertificate": _odbc_flag(trust, default="yes"),
        },
    )
    return url.render_as_string(hide_password=False)


def _sqlite_url(path: str) -> str:
    if path in {"", ":memory:"}:
        return "sqlite+aiosqlite:///:memory:"
    return URL.create("sqlite+aiosqlite", database=path).render_as_string(hide_password=False)


def _url_from_jdbc(info: ConnInfo) -> str:
    raw = (info.jdbc_url or "").strip()
    lowered = raw.lower()
    if lowered.startswith("jdbc:sqlite:"):
        return _sqlite_url(raw[len("jdbc:sqlite:") :])
    if lowered.startswith("jdbc:oracle:"):
        return _oracle_from_jdbc(raw, info)
    if lowered.startswith("jdbc:sqlserver:"):
        return _sqlserver_from_jdbc(raw, info)
    if lowered.startswith("jdbc:"):
        raise DatasourceDriverError(
            "jdbc_url is not a SQLAlchemy URL; set host, database, and db_type"
        )
    return _ensure_async_driver(raw, info.db_type)


def _oracle_from_jdbc(raw: str, info: ConnInfo) -> str:
    service = _JDBC_ORACLE_SERVICE.match(raw.strip())
    if service:
        return _oracle_service_url(
            ConnInfo(
                db_type="oracle",
                host=service.group("host"),
                port=int(service.group("port")),
                database=service.group("service"),
                username=info.username,
                password=info.password,
            )
        )
    sid = _JDBC_ORACLE_SID.match(raw.strip())
    if sid:
        return _oracle_sid_url(
            ConnInfo(
                db_type="oracle",
                host=sid.group("host"),
                username=info.username,
                password=info.password,
            ),
            sid.group("sid"),
            int(sid.group("port")),
        )
    raise DatasourceDriverError(
        "unsupported Oracle jdbc_url; expected thin @//host:port/service or @host:port:sid"
    )


def _sqlserver_from_jdbc(raw: str, info: ConnInfo) -> str:
    match = _JDBC_SQLSERVER.match(raw.strip())
    if match is None:
        raise DatasourceDriverError("unsupported SQL Server jdbc_url")
    host, port = _split_sqlserver_server(match.group("server"))
    props = _jdbc_props(match.group("props") or "")
    database = props.get("databasename") or info.database or ""
    return _sqlserver_url(
        ConnInfo(
            db_type="sqlserver",
            host=host,
            port=port,
            database=database,
            username=info.username,
            password=info.password,
        ),
        port=port,
        encrypt=props.get("encrypt", "false"),
        trust=props.get("trustservercertificate", "true"),
    )


def _split_sqlserver_server(server: str) -> tuple[str, int | None]:
    if "\\" in server:
        host, rest = server.split("\\", 1)
        if ":" in rest:
            instance, port_text = rest.rsplit(":", 1)
            return f"{host}\\{instance}", int(port_text)
        return server, None
    if ":" in server:
        host, port_text = server.rsplit(":", 1)
        if port_text.isdigit():
            return host, int(port_text)
    return server, None


def _jdbc_props(raw: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for part in raw.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        props[key.strip().lower()] = value.strip()
    return props


def _odbc_flag(value: str, *, default: str) -> str:
    text = (value or "").strip().lower()
    if text in {"true", "yes", "1", "mandatory"}:
        return "yes"
    if text in {"false", "no", "0", "optional", "disabled"}:
        return "no"
    return default if not text else value


_ASYNC_DRIVERS = ("+aiosqlite", "+asyncpg", "+aiomysql", "+oracledb", "+aioodbc")


def _ensure_async_driver(url: str, db_type: str) -> str:
    if any(token in url for token in _ASYNC_DRIVERS):
        return url
    normalized = normalize_db_type(db_type)
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
    if (normalized in _ORACLE or url.startswith("oracle")) and "://" in url:
        rest = url.split("://", 1)[1]
        return "oracle+oracledb://" + rest
    if (normalized in _SQLSERVER or url.startswith("mssql")) and "://" in url:
        rest = url.split("://", 1)[1]
        return "mssql+aioodbc://" + rest
    return url


def _require_module(module: str, message: str) -> None:
    if importlib.util.find_spec(module) is None:
        raise DatasourceDriverError(message)
