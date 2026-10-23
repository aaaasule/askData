"""SSE chunk shapes shared with the LangChat analysis protocol."""

from __future__ import annotations

from app.services import sse_assembler as sse
from tests.sse_utils import events_named, parse_sse


def _event(frame: str) -> dict:
    parsed = parse_sse(frame)
    assert len(parsed) == 1
    chunk = parsed[0]
    assert chunk["object"] == "chat.completion.chunk"
    assert chunk["choices"][0]["index"] == 0
    return chunk["choices"][0]["delta"]


def test_message_delta_uses_content_and_event_name() -> None:
    delta = _event(sse.message_delta("hello"))
    assert delta["content"] == "hello"
    assert delta["event"]["name"] == "message.delta"


def test_tool_events_carry_tool_name() -> None:
    before = _event(sse.tool_before("query_data", {"sql": "SELECT 1"}))
    assert before["event"]["name"] == "tool.before"
    assert before["event"]["tool_name"] == "query_data"
    assert before["event"]["arguments"]["sql"] == "SELECT 1"

    executed = _event(
        sse.tool_executed("query_data", status="ok", result={"row_count": 1}, failed=False)
    )
    assert executed["event"]["name"] == "tool.executed"
    assert executed["event"]["failed"] is False
    assert executed["event"]["result"]["row_count"] == 1


def test_analysis_table_is_snake_case() -> None:
    delta = _event(
        sse.analysis_table(
            columns=["name", "cnt"],
            rows=[["alpha", 1]],
            row_count=1,
            sql="SELECT name, COUNT(*) AS cnt FROM orders",
            title="订单数",
        )
    )
    event = delta["event"]
    assert event["name"] == "analysis.table"
    assert event["columns"] == ["name", "cnt"]
    assert event["rows"] == [["alpha", 1]]
    assert event["row_count"] == 1
    assert event["sql"].startswith("SELECT")
    assert event["title"] == "订单数"
    assert "rowCount" not in event
    assert "chartType" not in event


def test_analysis_echart_requires_series_shape() -> None:
    option = {"series": [{"type": "bar", "data": [1]}]}
    event = _event(sse.analysis_echart(chart_type="bar", option=option, title="图"))["event"]
    assert event["name"] == "analysis.echart"
    assert event["chart_type"] == "bar"
    assert event["option"]["series"]
    assert event["title"] == "图"


def test_error_and_timeout_share_code_and_message() -> None:
    error = _event(sse.error_event("NO_TABLES", "没有授权表"))["event"]
    timeout = _event(sse.timeout_event("TIMEOUT", "query exceeded 30s"))["event"]
    assert error["name"] == "error"
    assert error["code"] == "NO_TABLES"
    assert timeout["name"] == "timeout"
    assert timeout["message"] == "query exceeded 30s"


def test_optional_lifecycle_events_and_done() -> None:
    start = _event(sse.message_start({"conversation_id": "c1"}))["event"]
    assert start["name"] == "message.start"
    assert start["conversation_id"] == "c1"
    log = _event(sse.log_delta("使用模型"))
    assert log["event"]["name"] == "log.delta"
    assert log["content"] == "使用模型"
    completed = _event(sse.message_completed("done"))
    assert completed["event"]["name"] == "message.completed"
    assert completed["content"] == "done"
    stop = parse_sse(sse.message_stop())[0]
    assert stop["choices"][0]["delta"]["event"]["name"] == "message.stop"
    assert stop["choices"][0]["finish_reason"] == "stop"
    assert sse.done() == "data: [DONE]\n\n"


def test_done_sentinel_is_last_token() -> None:
    frames = sse.message_delta("hi") + sse.done()
    parsed = parse_sse(frames)
    assert events_named(parsed, "message.delta")
    assert parsed[-1] == "[DONE]"
