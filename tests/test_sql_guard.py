"""Read-only SQL guard: SELECT/WITH only, table allowlist, max rows."""

from __future__ import annotations

import pytest

from app.services.sql_guard import (
    SqlGuardError,
    apply_max_rows,
    assert_read_only,
    enforce_table_allowlist,
    prepare_read_only_sql,
)


def test_select_and_with_are_allowed() -> None:
    assert assert_read_only("SELECT 1").lower().startswith("select")
    assert assert_read_only("  WITH t AS (SELECT 1) SELECT * FROM t").lower().startswith("with")
    assert assert_read_only("select id from orders;")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO orders (id) VALUES (1)",
        "UPDATE orders SET name = 'x'",
        "DELETE FROM orders",
        "DROP TABLE orders",
        "ALTER TABLE orders ADD COLUMN x INT",
        "CREATE TABLE t (id INT)",
        "TRUNCATE TABLE orders",
        "REPLACE INTO orders (id) VALUES (1)",
        "PRAGMA writable_schema = ON",
        "ATTACH DATABASE 'other.db' AS other",
    ],
)
def test_rejects_writes_and_ddl(sql: str) -> None:
    with pytest.raises(SqlGuardError):
        assert_read_only(sql)


def test_rejects_multiple_statements() -> None:
    with pytest.raises(SqlGuardError):
        assert_read_only("SELECT 1; DELETE FROM orders")


def test_rejects_empty_sql() -> None:
    with pytest.raises(SqlGuardError):
        assert_read_only("   ")


def test_rejects_select_into_and_dangerous_functions() -> None:
    with pytest.raises(SqlGuardError):
        assert_read_only("SELECT * INTO OUTFILE '/tmp/x' FROM orders")
    with pytest.raises(SqlGuardError):
        prepare_read_only_sql("SELECT readfile('/etc/passwd')", set(), max_rows=10)
    with pytest.raises(SqlGuardError):
        prepare_read_only_sql("SELECT pg_read_file('/etc/passwd')", set(), max_rows=10)
    with pytest.raises(SqlGuardError):
        prepare_read_only_sql("SELECT sleep(10)", set(), max_rows=10)


def test_allowlist_blocks_unknown_tables_and_allows_cte_names() -> None:
    sql = "WITH recent AS (SELECT id FROM orders) SELECT id FROM recent"
    enforce_table_allowlist(sql, {"orders"})

    with pytest.raises(SqlGuardError):
        enforce_table_allowlist(
            "SELECT * FROM orders o JOIN secrets s ON o.id = s.id",
            {"orders"},
        )

    with pytest.raises(SqlGuardError):
        enforce_table_allowlist("SELECT * FROM (SELECT * FROM hidden) h", {"orders"})


def test_table_less_select_does_not_need_allowlist_entries() -> None:
    enforce_table_allowlist("SELECT 1", set())


def test_allowlist_is_case_insensitive() -> None:
    enforce_table_allowlist('SELECT * FROM "Orders"', {"orders"})


def test_apply_max_rows_caps_limit() -> None:
    capped = apply_max_rows("SELECT * FROM orders", max_rows=200)
    assert "200" in capped

    kept = apply_max_rows("SELECT * FROM orders LIMIT 10", max_rows=200)
    assert "10" in kept
    assert "200" not in kept.split("LIMIT")[-1]

    reduced = apply_max_rows("SELECT * FROM orders LIMIT 9999", max_rows=200)
    assert "9999" not in reduced


def test_prepare_composes_checks() -> None:
    sql = prepare_read_only_sql("SELECT id FROM orders", {"orders"}, max_rows=50)
    assert "50" in sql
    with pytest.raises(SqlGuardError):
        prepare_read_only_sql("DELETE FROM orders", {"orders"}, max_rows=50)
    with pytest.raises(SqlGuardError):
        prepare_read_only_sql("SELECT * FROM secrets", {"orders"}, max_rows=50)
