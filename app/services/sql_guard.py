"""Read-only SQL guard: whitelist SELECT/WITH, table allowlist, max rows."""

from __future__ import annotations

# TODO: parse with sqlglot or sqlparse; reject INSERT/UPDATE/DELETE/DDL;
# TODO: enforce table allowlist from catalog; inject LIMIT if missing.


ALLOWED_PREFIXES = ("select", "with")


class SqlGuardError(ValueError):
    pass


def assert_read_only(sql: str) -> str:
    """Return stripped SQL if it looks like a read-only query; else raise."""
    cleaned = (sql or "").strip()
    if not cleaned:
        raise SqlGuardError("empty SQL")
    head = cleaned.lstrip("(").lstrip().lower()
    if not any(head.startswith(p) for p in ALLOWED_PREFIXES):
        raise SqlGuardError("only SELECT/WITH queries are allowed")
    # crude multi-statement block
    if ";" in cleaned.rstrip(";"):
        raise SqlGuardError("multiple statements are not allowed")
    return cleaned


def enforce_table_allowlist(sql: str, allowed_tables: set[str]) -> None:
    """TODO: extract table refs and ensure ⊆ allowed_tables."""
    _ = sql, allowed_tables
    raise NotImplementedError("table allowlist check not implemented yet")


def apply_max_rows(sql: str, max_rows: int = 200) -> str:
    """TODO: append or rewrite LIMIT; for now return unchanged."""
    _ = max_rows
    return sql
