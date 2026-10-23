"""
SSE assembler aligned with LangChat analysis protocol.

Wire format (no `event:` lines):
  data: <OpenAI-style chat chunk JSON>\\n\\n
  data: [DONE]\\n\\n

Chunk shape (essentials):
  {
    "id": "...",
    "object": "chat.completion.chunk",
    "choices": [{
      "index": 0,
      "delta": {
        "content": "...",          # for message.delta
        "event": {
          "name": "<event name>",
          ...event-specific fields (snake_case for table/chart)
        }
      },
      "finish_reason": null
    }]
  }

Required event names (must implement for migrated Vue pages):
  - message.delta      — text delta via delta.content
  - tool.before        — tool about to run
  - tool.executed      — tool finished (status, result, failed)
  - analysis.table     — columns, rows, row_count, sql, title (snake_case)
  - analysis.echart    — chart_type, option (series non-empty), title
  - error              — code, message
  - timeout            — code, message

Also useful (Vue may ignore on 问数 page):
  message.start, log.delta, message.completed, message.stop

Tool names in tool_name field:
  query_data, inspect_selected_tables, get_current_time
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

# --- event name constants -------------------------------------------------

EVENT_MESSAGE_DELTA = "message.delta"
EVENT_TOOL_BEFORE = "tool.before"
EVENT_TOOL_EXECUTED = "tool.executed"
EVENT_ANALYSIS_TABLE = "analysis.table"
EVENT_ANALYSIS_ECHART = "analysis.echart"
EVENT_ERROR = "error"
EVENT_TIMEOUT = "timeout"

EVENT_MESSAGE_START = "message.start"
EVENT_LOG_DELTA = "log.delta"
EVENT_MESSAGE_COMPLETED = "message.completed"
EVENT_MESSAGE_STOP = "message.stop"

DONE_SENTINEL = "[DONE]"

TOOL_QUERY_DATA = "query_data"
TOOL_INSPECT_TABLES = "inspect_selected_tables"
TOOL_GET_CURRENT_TIME = "get_current_time"


def _chunk_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def build_chunk(
    event_name: str | None = None,
    *,
    content: str | None = None,
    event_fields: dict[str, Any] | None = None,
    chunk_id: str | None = None,
    finish_reason: str | None = None,
) -> dict[str, Any]:
    """Build one OpenAI-style chat.completion.chunk with optional delta.event."""
    delta: dict[str, Any] = {}
    if content is not None:
        delta["content"] = content
    if event_name is not None:
        event: dict[str, Any] = {"name": event_name}
        if event_fields:
            event.update(event_fields)
        delta["event"] = event
    return {
        "id": chunk_id or _chunk_id(),
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }


def format_sse_data(payload: dict[str, Any] | str) -> str:
    """Serialize one SSE data line (JSON or literal [DONE])."""
    if isinstance(payload, str):
        body = payload
    else:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"data: {body}\n\n"


def message_delta(text: str, *, chunk_id: str | None = None) -> str:
    return format_sse_data(
        build_chunk(EVENT_MESSAGE_DELTA, content=text, chunk_id=chunk_id)
    )


def tool_before(
    tool_name: str,
    arguments: dict[str, Any] | str | None = None,
    *,
    chunk_id: str | None = None,
) -> str:
    return format_sse_data(
        build_chunk(
            EVENT_TOOL_BEFORE,
            event_fields={"tool_name": tool_name, "arguments": arguments or {}},
            chunk_id=chunk_id,
        )
    )


def tool_executed(
    tool_name: str,
    *,
    status: str = "ok",
    result: Any = None,
    failed: bool = False,
    arguments: dict[str, Any] | str | None = None,
    chunk_id: str | None = None,
) -> str:
    return format_sse_data(
        build_chunk(
            EVENT_TOOL_EXECUTED,
            event_fields={
                "tool_name": tool_name,
                "status": status,
                "result": result,
                "failed": failed,
                "arguments": arguments or {},
            },
            chunk_id=chunk_id,
        )
    )


def analysis_table(
    *,
    columns: list[str],
    rows: list[list[Any]],
    row_count: int | None = None,
    sql: str | None = None,
    title: str | None = None,
    chunk_id: str | None = None,
) -> str:
    """Snake_case fields as expected by analysis-event-parser.ts."""
    return format_sse_data(
        build_chunk(
            EVENT_ANALYSIS_TABLE,
            event_fields={
                "columns": columns,
                "rows": rows,
                "row_count": row_count if row_count is not None else len(rows),
                "sql": sql,
                "title": title,
            },
            chunk_id=chunk_id,
        )
    )


def analysis_echart(
    *,
    chart_type: str,
    option: dict[str, Any],
    title: str | None = None,
    chunk_id: str | None = None,
) -> str:
    """option.series must be a non-empty array for Vue acceptance."""
    return format_sse_data(
        build_chunk(
            EVENT_ANALYSIS_ECHART,
            event_fields={
                "chart_type": chart_type,
                "option": option,
                "title": title,
            },
            chunk_id=chunk_id,
        )
    )


def error_event(code: str, message: str, *, chunk_id: str | None = None) -> str:
    return format_sse_data(
        build_chunk(
            EVENT_ERROR,
            event_fields={"code": code, "message": message},
            chunk_id=chunk_id,
        )
    )


def timeout_event(code: str = "TIMEOUT", message: str = "timeout", *, chunk_id: str | None = None) -> str:
    return format_sse_data(
        build_chunk(
            EVENT_TIMEOUT,
            event_fields={"code": code, "message": message},
            chunk_id=chunk_id,
        )
    )


def message_start(fields: dict[str, Any] | None = None, *, chunk_id: str | None = None) -> str:
    return format_sse_data(
        build_chunk(EVENT_MESSAGE_START, event_fields=fields or None, chunk_id=chunk_id)
    )


def log_delta(text: str, *, chunk_id: str | None = None) -> str:
    return format_sse_data(build_chunk(EVENT_LOG_DELTA, content=text, chunk_id=chunk_id))


def message_completed(content: str | None = None, *, chunk_id: str | None = None) -> str:
    return format_sse_data(
        build_chunk(EVENT_MESSAGE_COMPLETED, content=content, chunk_id=chunk_id)
    )


def message_stop(*, chunk_id: str | None = None) -> str:
    return format_sse_data(
        build_chunk(EVENT_MESSAGE_STOP, finish_reason="stop", chunk_id=chunk_id)
    )


def done() -> str:
    return format_sse_data(DONE_SENTINEL)
