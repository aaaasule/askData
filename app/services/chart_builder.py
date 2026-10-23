"""Build ECharts option payloads for analysis.echart events."""

from __future__ import annotations

from typing import Any


def build_echart_option(
    chart_type: str,
    columns: list[str],
    rows: list[list[Any]],
    title: str | None = None,
) -> dict[str, Any]:
    """
    TODO: infer category/value columns; produce a minimal ECharts option
    with non-empty series[] so LangChat Vue parser accepts it.
    """
    _ = columns, rows
    return {
        "title": {"text": title or ""},
        "tooltip": {},
        "xAxis": {"type": "category", "data": []},
        "yAxis": {"type": "value"},
        "series": [{"type": chart_type or "bar", "data": []}],
    }
