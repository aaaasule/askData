"""Catalog rules for imported and enabled tables inside structure_json.

A table is authorized when `imported` is not false and `enabled` is not false.
Missing flags count as true, matching introspect output and the read-only
allowlist. `name` and LangChat-style `tableName` are both accepted.
"""

from __future__ import annotations

from typing import Any


def authorized_tables(structure: dict[str, Any] | None) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for table in (structure or {}).get("tables") or []:
        if not isinstance(table, dict):
            continue
        name = _table_name(table)
        if not name:
            continue
        if _is_false(table.get("imported", True)):
            continue
        if _is_false(table.get("enabled", True)):
            continue
        tables.append(table)
    return tables


def build_catalog(datasource_id: str, structure: dict[str, Any] | None) -> dict[str, Any]:
    """Return the analysis catalog: authorized tables only."""
    listed: list[dict[str, Any]] = []
    for table in authorized_tables(structure):
        listed.append(
            {
                "name": _table_name(table),
                "comment": table.get("comment"),
                "imported": True,
                "enabled": True,
                "columns": table.get("columns") or [],
            }
        )
    return {"datasourceId": datasource_id, "tables": listed}


def select_requested_tables(
    structure: dict[str, Any] | None,
    requested: list[str] | None,
) -> list[dict[str, Any]]:
    """Intersect an optional request whitelist with authorized tables.

    An empty request means every authorized table.
    """
    authorized = authorized_tables(structure)
    if not requested:
        return authorized
    wanted = {normalize_table_name(name) for name in requested if str(name).strip()}
    selected: list[dict[str, Any]] = []
    for table in authorized:
        if normalize_table_name(_table_name(table)) in wanted:
            selected.append(table)
    return selected


def normalize_table_name(name: str | None) -> str:
    text = (name or "").strip().strip('"').strip("`").strip("[]")
    if "." in text:
        text = text.split(".")[-1]
    return text.lower()


def _table_name(table: dict[str, Any]) -> str:
    raw = table.get("name") or table.get("tableName") or ""
    return str(raw).strip()


def _is_false(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"0", "false", "no", "off"}
    return value is False or value == 0
