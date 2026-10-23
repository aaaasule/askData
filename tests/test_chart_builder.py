"""Chart inference: bar, line, pie, and skip when the result is not aggregated."""

from __future__ import annotations

from app.services.chart_builder import infer_chart


def test_category_count_is_a_bar() -> None:
    chart = infer_chart(
        ["name", "cnt"],
        [{"name": "alpha", "cnt": 2}, {"name": "beta", "cnt": 1}],
        "订单数",
    )
    assert chart is not None
    chart_type, option = chart
    assert chart_type == "bar"
    assert option["series"][0]["type"] == "bar"
    assert option["series"][0]["data"] == [2.0, 1.0]
    assert option["xAxis"]["data"] == ["alpha", "beta"]
    assert option["title"]["text"] == "订单数"


def test_dates_become_a_line() -> None:
    chart = infer_chart(
        ["day", "amount"],
        [["2026-01-01", 10], ["2026-01-02", 4]],
    )
    assert chart is not None
    assert chart[0] == "line"
    assert chart[1]["series"][0]["data"] == [10.0, 4.0]


def test_ratio_column_becomes_a_pie() -> None:
    chart = infer_chart(
        ["status", "ratio"],
        [["open", 0.25], ["done", 0.75]],
    )
    assert chart is not None
    assert chart[0] == "pie"
    data = chart[1]["series"][0]["data"]
    assert data[0]["name"] == "open"
    assert data[1]["value"] == 0.75


def test_identifier_list_is_not_chartable() -> None:
    assert infer_chart(["id", "name"], [{"id": 1, "name": "alpha"}]) is None


def test_wide_or_empty_results_are_skipped() -> None:
    assert infer_chart(["name"], [["alpha"]]) is None
    rows = [[f"n{i}", i] for i in range(30)]
    assert infer_chart(["name", "cnt"], rows) is None
    assert infer_chart(["name", "note"], [["alpha", "text"]]) is None
