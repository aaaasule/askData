"""Build a minimal ECharts option when a tool result looks aggregated."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

_MAX_ROWS = 24
_DATE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}")
_ID_NAMES = {"id", "pk", "uuid", "guid"}
_PIE_TOKENS = ("ratio", "percent", "pct", "share", "占比", "比例", "百分比")


def infer_chart(
    columns: list[str],
    rows: list[Any],
    title: str | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Return (chart_type, option) for a bar, line, or pie chart, or None.

    A result is chartable when it has one category column and at least one
    numeric measure that is not an identifier, and the row count is small.
    """
    matrix = _as_matrix(columns, rows)
    if len(columns) < 2 or not matrix or len(matrix) > _MAX_ROWS:
        return None
    numeric = [_is_numeric_column(matrix, index) for index in range(len(columns))]
    dims = [
        index
        for index, name in enumerate(columns)
        if not numeric[index] and not _is_identifier(name)
    ]
    measures = [
        index
        for index, name in enumerate(columns)
        if numeric[index] and not _is_identifier(name)
    ]
    if len(dims) != 1 or not measures:
        return None
    dim = dims[0]
    measure = measures[0]
    labels, values = _aggregate(matrix, dim, measure)
    if not labels or not values:
        return None
    value_name = columns[measure]
    if _temporal(labels):
        chart_type = "line"
    elif _prefer_pie(value_name, values):
        chart_type = "pie"
    else:
        chart_type = "bar"
    return chart_type, build_echart_option(chart_type, labels, values, value_name, title)


def build_echart_option(
    chart_type: str,
    labels: list[str],
    values: list[float],
    value_name: str = "",
    title: str | None = None,
) -> dict[str, Any]:
    """Minimal ECharts option. `series` is always a non-empty array."""
    heading = title or ""
    if chart_type == "pie":
        return {
            "title": {"text": heading},
            "tooltip": {"trigger": "item"},
            "series": [
                {
                    "type": "pie",
                    "name": value_name,
                    "radius": "60%",
                    "data": [
                        {"name": label, "value": value}
                        for label, value in zip(labels, values, strict=True)
                    ],
                }
            ],
        }
    kind = chart_type if chart_type in {"bar", "line"} else "bar"
    return {
        "title": {"text": heading},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": labels},
        "yAxis": {"type": "value"},
        "series": [{"type": kind, "name": value_name, "data": values}],
    }


def _as_matrix(columns: list[str], rows: list[Any]) -> list[list[Any]]:
    matrix: list[list[Any]] = []
    for row in rows:
        if isinstance(row, dict):
            matrix.append([row.get(column) for column in columns])
        else:
            matrix.append(list(row))
    return matrix


def _is_numeric_column(matrix: list[list[Any]], index: int) -> bool:
    seen = False
    for row in matrix:
        if index >= len(row) or row[index] is None:
            continue
        if _number(row[index]) is None:
            return False
        seen = True
    return seen


def _is_identifier(name: str) -> bool:
    normalized = name.lower().strip("`\"")
    return normalized in _ID_NAMES or normalized.endswith("_id")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float | Decimal):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _aggregate(
    matrix: list[list[Any]], dim: int, measure: int
) -> tuple[list[str], list[float]]:
    totals: dict[str, float] = {}
    order: list[str] = []
    for row in matrix:
        if dim >= len(row) or measure >= len(row):
            continue
        value = _number(row[measure])
        if value is None or row[dim] is None:
            continue
        label = str(row[dim])
        if label not in totals:
            order.append(label)
            totals[label] = 0.0
        totals[label] += value
    return order, [totals[label] for label in order]


def _temporal(labels: list[str]) -> bool:
    if not labels:
        return False
    hits = 0
    for label in labels:
        if _DATE.match(label) or ("T" in label and "-" in label and len(label) >= 8):
            hits += 1
    return hits / len(labels) >= 0.8


def _prefer_pie(value_name: str, values: list[float]) -> bool:
    if len(values) < 2 or len(values) > 8 or any(value < 0 for value in values):
        return False
    label = value_name.lower()
    if any(token in label for token in _PIE_TOKENS):
        return True
    return all(0 <= value <= 1 for value in values) and sum(values) <= 1.01 and any(
        value < 1 for value in values
    )
