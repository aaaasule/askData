"""NL → SQL tool loop. Emits LangChat-aligned analysis SSE and stops with [DONE]."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import AigcDatasource, AigcModel
from app.security.secrets import SecretError, open_secret, seal_secret
from app.services import sse_assembler as sse
from app.services.catalog import build_catalog, select_requested_tables
from app.services.chart_builder import infer_chart
from app.services.conversation_store import ConversationStore
from app.services.datasource_service import DatasourceService
from app.services.llm_client import (
    LLMError,
    LLMTimeoutError,
    OpenAICompatibleClient,
    normalize_base_url,
)
from app.services.sql_guard import SqlGuardError
from app.services.target_db import (
    DatasourceDriverError,
    QueryExecutionError,
    QueryTimeoutError,
    dialect_name,
)

logger = logging.getLogger(__name__)

_MAX_ROUNDS = 4
_PREVIEW_ROWS = 20
_CHAT_TYPES = {"chat", "llm", "openai", "openai-compatible"}

_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": sse.TOOL_QUERY_DATA,
            "description": (
                "Execute one read-only SELECT or WITH query on the authorized tables "
                "and return columns and rows."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "A single SELECT or WITH query."},
                    "title": {"type": "string", "description": "Short title for the table and chart."},
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": sse.TOOL_INSPECT_TABLES,
            "description": "List columns of the tables authorized for this question.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": sse.TOOL_GET_CURRENT_TIME,
            "description": "Return the current UTC time. Use it for relative dates such as today.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


class _TurnError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class _ResolvedModel:
    id: str | None
    name: str
    model: str
    type: str
    base_url: str
    endpoint: str
    api_key: str
    temperature: float | None
    top_p: float | None
    max_token: int | None


class _ModelTurn:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.tool_calls: list[dict[str, Any]] = []
        self.terminal: str | None = None


@dataclass
class _ToolOutcome:
    events: list[str]
    result: dict[str, Any]
    failed: bool
    has_table: bool = False
    stop: str | None = None


class AnalysisRuntime:
    """One analysis turn: prior conversation context, model tools, read-only SQL."""

    def __init__(self, session: AsyncSession, llm: Any | None = None) -> None:
        self.session = session
        self.llm = llm or OpenAICompatibleClient()
        self.settings = get_settings()

    async def catalog(
        self, datasource_id: str, structure: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return build_catalog(datasource_id, structure)

    async def chat_stream(
        self,
        *,
        datasource_id: str,
        question: str,
        table_names: list[str],
        model_id: str | None = None,
        conversation_id: str | None = None,
    ) -> AsyncIterator[str]:
        completed = False
        try:
            async with asyncio.timeout(self.settings.analysis_timeout_seconds):
                async for chunk in self._events(
                    datasource_id=datasource_id,
                    question=question,
                    table_names=table_names,
                    model_id=model_id,
                    conversation_id=conversation_id,
                ):
                    yield chunk
            completed = True
        except TimeoutError:
            yield sse.timeout_event("TIMEOUT", "analysis timed out")
        except Exception as exc:  # noqa: BLE001 - the SSE client must see an error frame
            yield sse.error_event("INTERNAL", _safe(exc))
        if not completed:
            yield sse.message_stop()
        yield sse.done()

    async def _events(
        self,
        *,
        datasource_id: str,
        question: str,
        table_names: list[str],
        model_id: str | None,
        conversation_id: str | None,
    ) -> AsyncIterator[str]:
        try:
            resolved, base_url, datasource, tables = await self._prepare(
                datasource_id, question, table_names, model_id
            )
        except _TurnError as exc:
            yield sse.message_start({"conversation_id": conversation_id or str(uuid4())})
            yield sse.error_event(exc.code, exc.message)
            yield sse.message_stop()
            return

        store = ConversationStore(self.session)
        conversation, prior = await store.open(conversation_id, datasource_id, resolved.id)
        yield sse.message_start({"conversation_id": conversation})
        yield sse.log_delta(f"使用模型 {resolved.name}（{resolved.model}）")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _system_prompt(dialect_name(datasource.db_type), tables)},
            *prior,
            {"role": "user", "content": question.strip()},
        ]
        allowed = {_table_label(table) for table in tables}
        answer: list[str] = []
        produced_table = False
        nudged = False
        try:
            async for chunk in self._run_rounds(
                resolved,
                base_url,
                messages,
                answer,
                datasource_id,
                allowed,
                tables,
                question,
                produced_table,
                nudged,
            ):
                yield chunk
        finally:
            await _remember(store, conversation, question.strip(), "".join(answer))

    async def _prepare(
        self,
        datasource_id: str,
        question: str,
        table_names: list[str],
        model_id: str | None,
    ) -> tuple[_ResolvedModel, str, AigcDatasource, list[dict[str, Any]]]:
        if not question or not question.strip():
            raise _TurnError("BAD_REQUEST", "question is required")
        resolved = await self._resolve_model(model_id)
        if (resolved.type or "chat").lower() not in _CHAT_TYPES:
            raise _TurnError("MODEL_TYPE", f"model type {resolved.type} cannot answer questions")
        if not resolved.api_key:
            raise _TurnError("MODEL_CONFIG", "model api_key is empty")
        try:
            base_url = normalize_base_url(resolved.base_url, resolved.endpoint)
        except LLMError as exc:
            raise _TurnError(exc.code, str(exc)) from exc
        datasource = await self.session.get(AigcDatasource, datasource_id)
        if datasource is None:
            raise _TurnError("DATASOURCE_NOT_FOUND", "datasource not found")
        tables = select_requested_tables(datasource.structure_json, table_names)
        if not tables:
            raise _TurnError(
                "NO_TABLES",
                "没有已导入且启用的表，请先在 structureJson 中授权",
            )
        return resolved, base_url, datasource, tables

    async def _resolve_model(self, model_id: str | None) -> _ResolvedModel:
        if model_id:
            row = await self.session.get(AigcModel, model_id)
            if row is None:
                raise _TurnError("MODEL_NOT_FOUND", "model not found")
            if not row.enabled:
                raise _TurnError("MODEL_DISABLED", "model is disabled")
            return await self._materialize(row)
        result = await self.session.execute(
            select(AigcModel)
            .where(AigcModel.enabled.is_(True))
            .order_by(AigcModel.updated_at.desc(), AigcModel.created_at.desc())
        )
        row = result.scalars().first()
        if row is not None:
            return await self._materialize(row)
        settings = self.settings
        if settings.default_model_base_url and settings.default_model_name:
            return _ResolvedModel(
                id=None,
                name=settings.default_model_name,
                model=settings.default_model_name,
                type="chat",
                base_url=settings.default_model_base_url,
                endpoint="",
                api_key=settings.default_model_api_key,
                temperature=0.2,
                top_p=None,
                max_token=None,
            )
        raise _TurnError("MODEL_CONFIG", "no enabled model and no default model configured")

    async def _materialize(self, row: AigcModel) -> _ResolvedModel:
        resolved, migrated = _from_row(row)
        if migrated:
            await self.session.commit()
        return resolved

    async def _run_rounds(
        self,
        resolved: _ResolvedModel,
        base_url: str,
        messages: list[dict[str, Any]],
        answer: list[str],
        datasource_id: str,
        allowed: set[str],
        tables: list[dict[str, Any]],
        question: str,
        produced_table: bool,
        nudged: bool,
    ) -> AsyncIterator[str]:
        for _round in range(_MAX_ROUNDS):
            turn = _ModelTurn()
            async for chunk in self._stream_model(resolved, base_url, messages, turn):
                if chunk:
                    answer.append(chunk)
                    yield sse.message_delta(chunk)
            if turn.terminal is not None:
                yield turn.terminal
                yield sse.message_stop()
                return
            content = "".join(turn.parts)
            tool_calls = turn.tool_calls
            if not tool_calls:
                if not produced_table and not nudged:
                    nudged = True
                    messages.append({"role": "assistant", "content": content or ""})
                    messages.append(
                        {
                            "role": "user",
                            "content": "请调用 query_data 执行一条只读 SQL，用查询结果回答，不要编造数字。",
                        }
                    )
                    yield sse.log_delta("模型未查询数据，要求调用 query_data")
                    continue
                break
            messages.append(_assistant_tool_message(content, tool_calls))
            for call in tool_calls:
                args = _parse_args(call.get("arguments"))
                name = str(call.get("name") or "")
                yield sse.tool_before(name, args)
                if name == sse.TOOL_QUERY_DATA:
                    yield sse.log_delta(f"query_data: {str(args.get('sql') or '')[:400]}")
                outcome = await self._execute_tool(
                    name, args, datasource_id, allowed, tables, question
                )
                for event in outcome.events:
                    yield event
                produced_table = produced_table or outcome.has_table
                if outcome.stop == "timeout":
                    status = "timeout"
                elif outcome.failed:
                    status = "error"
                else:
                    status = "ok"
                yield sse.tool_executed(
                    name,
                    status=status,
                    result=outcome.result,
                    failed=outcome.failed,
                    arguments=args,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id") or f"call_{uuid4().hex[:8]}",
                        "content": json.dumps(outcome.result, ensure_ascii=False),
                    }
                )
                if outcome.stop == "timeout":
                    message = str(outcome.result.get("message") or "query timed out")
                    yield sse.timeout_event("TIMEOUT", message)
                    yield sse.message_stop()
                    return
        yield sse.message_completed(content="".join(answer) or None)
        yield sse.message_stop()

    async def _stream_model(
        self,
        resolved: _ResolvedModel,
        base_url: str,
        messages: list[dict[str, Any]],
        turn: _ModelTurn,
    ) -> AsyncIterator[str]:
        try:
            async for event in self.llm.stream(
                base_url=base_url,
                api_key=resolved.api_key,
                model=resolved.model,
                messages=messages,
                tools=_TOOLS,
                temperature=0.2 if resolved.temperature is None else resolved.temperature,
                top_p=resolved.top_p,
                max_tokens=resolved.max_token,
            ):
                if event.get("kind") == "content" and event.get("text"):
                    text = str(event["text"])
                    turn.parts.append(text)
                    yield text
                elif event.get("kind") == "tool_calls":
                    turn.tool_calls = list(event.get("calls") or [])
        except LLMTimeoutError:
            turn.terminal = sse.timeout_event("TIMEOUT", "model request timed out")
        except LLMError as exc:
            turn.terminal = sse.error_event(exc.code, str(exc))

    async def _execute_tool(
        self,
        name: str,
        args: dict[str, Any],
        datasource_id: str,
        allowed: set[str],
        tables: list[dict[str, Any]],
        question: str,
    ) -> _ToolOutcome:
        if name == sse.TOOL_GET_CURRENT_TIME:
            now = datetime.now(UTC)
            return _ToolOutcome([], {"utc": now.isoformat(), "date": now.date().isoformat()}, False)
        if name == sse.TOOL_INSPECT_TABLES:
            return _ToolOutcome([], {"tables": [_public_table(table) for table in tables]}, False)
        if name != sse.TOOL_QUERY_DATA:
            return _ToolOutcome([], {"message": f"unknown tool {name}"}, True)
        sql = str(args.get("sql") or args.get("query") or "").strip()
        if not sql:
            return _ToolOutcome([], {"message": "sql is required"}, True)
        title = str(args.get("title") or "").strip() or _short(question)
        service = DatasourceService(self.session)
        try:
            payload = await service.execute_read_only_query(
                datasource_id,
                sql,
                allowed,
                max_rows=self.settings.sql_max_rows,
                timeout_seconds=self.settings.sql_timeout_seconds,
            )
        except QueryTimeoutError as exc:
            return _ToolOutcome([], {"message": str(exc)}, True, stop="timeout")
        except (SqlGuardError, QueryExecutionError, DatasourceDriverError, SecretError) as exc:
            return _ToolOutcome([], {"message": str(exc)}, True)
        columns = [str(column) for column in payload.get("columns") or []]
        raw_rows = payload.get("rows") or []
        listed = _rows_to_lists(columns, raw_rows)
        executed_sql = str(payload.get("sql") or sql)
        row_count = int(payload.get("row_count") if payload.get("row_count") is not None else len(listed))
        events = [
            sse.analysis_table(
                columns=columns,
                rows=listed,
                row_count=row_count,
                sql=executed_sql,
                title=title,
            )
        ]
        chart = infer_chart(columns, raw_rows, title)
        if chart is not None:
            chart_type, option = chart
            events.append(
                sse.analysis_echart(chart_type=chart_type, option=option, title=title)
            )
        preview = {
            "columns": columns,
            "rows": listed[:_PREVIEW_ROWS],
            "row_count": row_count,
            "sql": executed_sql,
            "title": title,
            "truncated": row_count > _PREVIEW_ROWS,
        }
        return _ToolOutcome(events, preview, False, has_table=True)


def _from_row(row: AigcModel) -> tuple[_ResolvedModel, bool]:
    try:
        plain, legacy = open_secret(row.api_key or "")
    except SecretError as exc:
        raise _TurnError("MODEL_CONFIG", str(exc)) from exc
    migrated = False
    if legacy and row.api_key:
        row.api_key = seal_secret(plain)
        migrated = True
    resolved = _ResolvedModel(
        id=row.id,
        name=row.name,
        model=row.model_name,
        type=row.type or "chat",
        base_url=row.base_url or "",
        endpoint=row.endpoint or "",
        api_key=plain,
        temperature=row.temperature,
        top_p=row.top_p,
        max_token=row.max_token,
    )
    return resolved, migrated


async def _remember(
    store: ConversationStore,
    conversation_id: str,
    user_text: str,
    assistant_text: str,
) -> None:
    try:
        await store.append_turn(conversation_id, user_text, assistant_text)
    except Exception:
        logger.warning("failed to persist analysis turn", exc_info=True)


def _system_prompt(dialect: str, tables: list[dict[str, Any]]) -> str:
    lines = [
        "你是智能问数助手。只能通过工具查询数据库，禁止编造数字。",
        f"SQL 方言：{dialect}。每次只执行一条 SELECT 或 WITH。",
        "只能使用下面已授权的表，不要访问其他表，不要写库。",
        "需要数据时调用 query_data；不确定字段时调用 inspect_selected_tables；相对时间先调用 get_current_time。",
        "聚合问题优先 GROUP BY，并为结果提供简短 title。回答使用用户的语言。",
        "授权表：",
    ]
    for table in tables:
        columns = []
        for column in table.get("columns") or []:
            if not isinstance(column, dict):
                continue
            piece = f"{column.get('name')} {column.get('type') or ''}".strip()
            if column.get("comment"):
                piece += f"（{column.get('comment')}）"
            columns.append(piece)
        comment = f"（{table.get('comment')}）" if table.get("comment") else ""
        lines.append(f"- {_table_label(table)}{comment}: {', '.join(columns)}")
    return "\n".join(lines)


def _assistant_tool_message(content: str, tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": content or None,
        "tool_calls": [
            {
                "id": call.get("id") or f"call_{uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": call.get("name") or "",
                    "arguments": _arguments_text(call.get("arguments")),
                },
            }
            for call in tool_calls
        ],
    }


def _public_table(table: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": _table_label(table),
        "comment": table.get("comment"),
        "columns": table.get("columns") or [],
    }


def _table_label(table: dict[str, Any]) -> str:
    return str(table.get("name") or table.get("tableName") or "").strip()


def _arguments_text(raw: Any) -> str:
    if raw is None or raw == "":
        return "{}"
    if isinstance(raw, str):
        return raw
    return json.dumps(raw, ensure_ascii=False)


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _rows_to_lists(columns: list[str], rows: list[Any]) -> list[list[Any]]:
    listed: list[list[Any]] = []
    for row in rows:
        if isinstance(row, dict):
            listed.append([row.get(column) for column in columns])
        else:
            listed.append(list(row))
    return listed


def _short(question: str) -> str:
    text = " ".join(question.split())
    return text[:40]


def _safe(exc: Exception) -> str:
    return (str(exc) or exc.__class__.__name__)[:500]

