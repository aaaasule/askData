"""Read-only SQL guard: SELECT/WITH only, table allowlist, row cap.

Statement timeout is enforced by the executor (`target_db`) using
`DEFAULT_TIMEOUT_SECONDS`. This module owns the policy constants and the
SQL checks that run before a driver sees the statement.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

DEFAULT_MAX_ROWS = 200
DEFAULT_TIMEOUT_SECONDS = 30

_PARSE_DIALECTS: tuple[str | None, ...] = ("sqlite", "mysql", "postgres", "oracle", "tsql", None)

_READ_TYPES = (exp.Select, exp.Union, exp.Intersect, exp.Except)

_FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.TruncateTable,
    exp.Merge,
    exp.Pragma,
    exp.Attach,
    exp.Detach,
    exp.Into,
)

# File / extension / sleep helpers that are still syntactically a SELECT.
_DANGEROUS_FUNCS = {
    "readfile",
    "writefile",
    "load_extension",
    "edit",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "lo_import",
    "lo_export",
    "load_file",
    "sleep",
    "pg_sleep",
    "benchmark",
    "utl_http",
    "utl_file",
    "utl_inaddr",
    "utl_tcp",
    "dbms_scheduler",
    "dbms_java",
    "xp_cmdshell",
    "openrowset",
    "opendatasource",
    "openquery",
}

# Package calls such as UTL_HTTP.REQUEST often parse as a plain function name.
_DANGEROUS_SNIPPETS = (
    "utl_http",
    "utl_file",
    "utl_inaddr",
    "utl_tcp",
    "dbms_scheduler",
    "dbms_java",
    "xp_cmdshell",
    "openrowset",
    "opendatasource",
    "openquery",
)


class SqlGuardError(ValueError):
    """Raised when a statement must not be executed."""


def assert_read_only(sql: str) -> str:
    """Return stripped SQL if it is a single read-only query; else raise."""
    cleaned = _strip_sql(sql)
    if not cleaned:
        raise SqlGuardError("empty SQL")
    expression = _unwrap(_parse_one(cleaned))
    _assert_read_expression(expression)
    return cleaned


def enforce_table_allowlist(sql: str, allowed_tables: set[str]) -> None:
    """Require every base table reference to be in `allowed_tables`.

    CTE names are not base tables and do not need to be listed. A query with
    no table references (for example `SELECT 1`) is allowed.
    """
    allowed = {_normalize_table_name(name) for name in allowed_tables}
    missing = sorted(referenced_tables(sql) - allowed)
    if missing:
        raise SqlGuardError("tables not in allowlist: " + ", ".join(missing))


def apply_max_rows(sql: str, max_rows: int = DEFAULT_MAX_ROWS, *, dialect: str = "sqlite") -> str:
    """Cap the statement at `max_rows`, rewriting LIMIT when it is higher or absent."""
    if max_rows <= 0:
        raise SqlGuardError("max_rows must be positive")
    cleaned = _strip_sql(sql)
    expression = _unwrap(_parse_one(cleaned))
    current = _limit_value(expression)
    if current is not None and current <= max_rows:
        return cleaned
    return expression.limit(max_rows).sql(dialect=dialect)


def prepare_read_only_sql(
    sql: str,
    allowed_tables: set[str],
    max_rows: int = DEFAULT_MAX_ROWS,
    *,
    dialect: str = "sqlite",
) -> str:
    """Validate, enforce the allowlist, and return SQL capped at `max_rows`."""
    cleaned = assert_read_only(sql)
    enforce_table_allowlist(cleaned, allowed_tables)
    return apply_max_rows(cleaned, max_rows, dialect=dialect)


def clamp_execution_limits(
    max_rows: int,
    timeout_seconds: int,
    *,
    max_rows_cap: int = DEFAULT_MAX_ROWS,
    timeout_cap: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int, int]:
    """Clamp caller limits to the guard policy (defaults 200 rows / 30s)."""
    if max_rows < 1 or timeout_seconds < 1:
        raise SqlGuardError("max_rows and timeout_seconds must be positive")
    if max_rows_cap < 1 or timeout_cap < 1:
        raise SqlGuardError("limit caps must be positive")
    return min(max_rows, max_rows_cap), min(timeout_seconds, timeout_cap)


def referenced_tables(sql: str) -> set[str]:
    """Base table names referenced by `sql`, lowercased, excluding CTE aliases."""
    expression = _unwrap(_parse_one(_strip_sql(sql)))
    cte_names = {cte.alias_or_name.lower() for cte in expression.find_all(exp.CTE)}
    names: set[str] = set()
    for table in expression.find_all(exp.Table):
        name = _normalize_table_name(table.name)
        if not name or name in cte_names:
            continue
        names.add(name)
    return names


def _strip_sql(sql: str) -> str:
    return (sql or "").strip().rstrip(";").strip()


def _normalize_table_name(name: str | None) -> str:
    text = (name or "").strip().strip('"').strip("`").strip("[]")
    if "." in text:
        text = text.split(".")[-1]
    return text.lower()


def _parse_one(sql: str) -> exp.Expression:
    """Parse with sqlite, then mysql, then postgres, so writes are recognized."""
    errors: list[str] = []
    for dialect in _PARSE_DIALECTS:
        try:
            statements = sqlglot.parse(sql, read=dialect)
        except SqlglotError as exc:
            errors.append(str(exc).splitlines()[0])
            continue
        statements = [statement for statement in statements if statement is not None]
        if not statements:
            continue
        if len(statements) != 1:
            raise SqlGuardError("multiple statements are not allowed")
        return statements[0]
    detail = errors[0] if errors else "could not parse SQL"
    raise SqlGuardError(f"invalid SQL: {detail}")


def _unwrap(expression: exp.Expression) -> exp.Expression:
    current = expression
    while isinstance(current, exp.Subquery):
        current = current.this
    return current


def _assert_read_expression(expression: exp.Expression) -> None:
    if not isinstance(expression, _READ_TYPES):
        raise SqlGuardError("only SELECT/WITH queries are allowed")
    rendered = expression.sql().lower()
    for snippet in _DANGEROUS_SNIPPETS:
        if snippet in rendered:
            raise SqlGuardError(f"function {snippet} is not allowed")
    for node in expression.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise SqlGuardError("write or administrative statements are not allowed")
        func_name = _func_name(node)
        if func_name in _DANGEROUS_FUNCS:
            raise SqlGuardError(f"function {func_name} is not allowed")


def _func_name(node: exp.Expression) -> str:
    if not isinstance(node, exp.Func):
        return ""
    if isinstance(node, exp.Anonymous):
        return str(node.name or "").lower()
    try:
        return str(node.sql_name() or "").lower()
    except (AttributeError, TypeError, ValueError):
        return str(getattr(node, "name", "") or "").lower()


def _limit_value(expression: exp.Expression) -> int | None:
    limit = expression.args.get("limit")
    if not isinstance(limit, exp.Limit):
        return None
    literal = limit.expression
    if isinstance(literal, exp.Literal) and literal.is_int:
        return int(literal.this)
    return None
