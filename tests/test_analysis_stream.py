"""Stream path with a scripted model. SQL still goes through the read-only guard."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.deps import get_analysis_runtime
from app.main import app
from app.services.analysis_runtime import AnalysisRuntime
from app.services.llm_client import LLMTimeoutError
from tests.sse_utils import deltas_named, events_named, parse_sse


class ScriptedLLM:
    def __init__(self, rounds: list[list[dict]]) -> None:
        self.rounds = list(rounds)
        self.seen: list[dict] = []

    async def stream(self, **kwargs: object):
        self.seen.append(kwargs)
        events = self.rounds.pop(0) if self.rounds else [{"kind": "content", "text": "完成"}]
        for event in events:
            yield event


class TimeoutLLM:
    async def stream(self, **kwargs: object):
        raise LLMTimeoutError("slow")
        yield {}


def _headers() -> dict[str, str]:
    return {"X-API-Key": "test-key"}


def _seed(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, name TEXT, amount REAL)")
    conn.execute("INSERT INTO orders (id, name, amount) VALUES (1, 'alpha', 10)")
    conn.execute("INSERT INTO orders (id, name, amount) VALUES (2, 'beta', 4)")
    conn.commit()
    conn.close()


async def _datasource(client: AsyncClient, database: str) -> str:
    created = await client.post(
        "/api/v1/datasources",
        headers=_headers(),
        json={"name": "biz", "db_type": "sqlite", "database": database},
    )
    assert created.status_code == 200
    datasource_id = created.json()["data"]["id"]
    structure = {
        "tables": [
            {
                "name": "orders",
                "imported": True,
                "enabled": True,
                "columns": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "name", "type": "TEXT"},
                    {"name": "amount", "type": "REAL"},
                ],
            },
            {"name": "secrets", "imported": True, "enabled": False, "columns": []},
        ]
    }
    saved = await client.put(
        f"/api/v1/datasources/{datasource_id}",
        headers=_headers(),
        json={"structure_json": structure},
    )
    assert saved.status_code == 200
    return datasource_id


async def _model(client: AsyncClient, **extra: object) -> str:
    payload = {
        "name": "测试模型",
        "model": "gpt-test",
        "type": "chat",
        "base_url": "",
        "endpoint": "https://llm.example/v1/chat/completions",
        "api_key": "sk-live-secret-1234",
        "temperature": 0.1,
        "enabled": True,
    }
    payload.update(extra)
    created = await client.post("/api/v1/aigc/models", headers=_headers(), json=payload)
    assert created.status_code == 200
    assert "sk-live-secret-1234" not in created.text
    return created.json()["data"]["id"]


@pytest.fixture
def scripted_runtime():
    holder: dict[str, ScriptedLLM | TimeoutLLM] = {}

    def install(llm: ScriptedLLM | TimeoutLLM):
        holder["llm"] = llm

        def _override(session: Annotated[AsyncSession, Depends(get_db)]) -> AnalysisRuntime:
            return AnalysisRuntime(session, llm=holder["llm"])

        app.dependency_overrides[get_analysis_runtime] = _override
        return llm

    yield install
    app.dependency_overrides.pop(get_analysis_runtime, None)


async def test_stream_emits_table_from_mocked_tool_call(
    client: AsyncClient, app_home: Path, scripted_runtime
) -> None:
    biz = app_home / "orders.db"
    _seed(biz)
    datasource_id = await _datasource(client, str(biz))
    model_id = await _model(client)
    sql = "SELECT name, COUNT(*) AS cnt FROM orders GROUP BY name ORDER BY name"
    llm = scripted_runtime(
        ScriptedLLM(
            [
                [
                    {
                        "kind": "tool_calls",
                        "calls": [
                            {
                                "id": "call_1",
                                "name": "query_data",
                                "arguments": json.dumps({"sql": sql, "title": "订单数"}),
                            }
                        ],
                    }
                ],
                [{"kind": "content", "text": "alpha 与 beta 各有 1 条。"}],
            ]
        )
    )

    response = await client.post(
        "/api/v1/core/data-analysis/chat/stream",
        headers=_headers(),
        json={
            "datasourceId": datasource_id,
            "question": "每个名字有多少订单？",
            "tableNames": ["orders", "secrets"],
            "modelId": model_id,
            "conversationId": "conv-1",
        },
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "sk-live-secret-1234" not in response.text
    parsed = parse_sse(response.text)
    assert parsed[-1] == "[DONE]"
    assert events_named(parsed, "message.start")[0]["conversation_id"] == "conv-1"
    assert deltas_named(parsed, "message.delta")[0]["content"] == "alpha 与 beta 各有 1 条。"
    assert events_named(parsed, "tool.before")[0]["tool_name"] == "query_data"
    executed = events_named(parsed, "tool.executed")[0]
    assert executed["failed"] is False
    table = events_named(parsed, "analysis.table")[0]
    assert table["columns"] == ["name", "cnt"]
    assert table["row_count"] == 2
    assert table["rows"][0] == ["alpha", 1]
    assert "orders" in table["sql"].lower()
    assert table["title"] == "订单数"
    assert "rowCount" not in table
    chart = events_named(parsed, "analysis.echart")[0]
    assert chart["chart_type"] == "bar"
    assert chart["option"]["series"]
    assert events_named(parsed, "message.completed")
    assert events_named(parsed, "message.stop")
    assert events_named(parsed, "log.delta")
    assert llm.seen[0]["model"] == "gpt-test"
    assert llm.seen[0]["base_url"] == "https://llm.example/v1"
    assert llm.seen[0]["api_key"] == "sk-live-secret-1234"
    assert llm.seen[0]["temperature"] == 0.1


async def test_stream_rejects_writes_without_a_table_event(
    client: AsyncClient, app_home: Path, scripted_runtime
) -> None:
    biz = app_home / "orders.db"
    _seed(biz)
    datasource_id = await _datasource(client, str(biz))
    model_id = await _model(client)
    scripted_runtime(
        ScriptedLLM(
            [
                [
                    {
                        "kind": "tool_calls",
                        "calls": [
                            {
                                "id": "call_del",
                                "name": "query_data",
                                "arguments": json.dumps({"sql": "DELETE FROM orders"}),
                            }
                        ],
                    }
                ],
                [{"kind": "content", "text": "语句被拒绝。"}],
            ]
        )
    )
    response = await client.post(
        "/api/v1/core/data-analysis/chat/stream",
        headers=_headers(),
        json={
            "datasourceId": datasource_id,
            "question": "删掉订单",
            "tableNames": ["orders"],
            "modelId": model_id,
        },
    )
    parsed = parse_sse(response.text)
    assert parsed[-1] == "[DONE]"
    assert events_named(parsed, "analysis.table") == []
    assert events_named(parsed, "tool.executed")[0]["failed"] is True
    conn = sqlite3.connect(biz)
    try:
        remaining = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    finally:
        conn.close()
    assert remaining == 2


async def test_stream_timeout_and_missing_model(
    client: AsyncClient, app_home: Path, scripted_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    biz = app_home / "orders.db"
    _seed(biz)
    datasource_id = await _datasource(client, str(biz))
    model_id = await _model(client)
    scripted_runtime(TimeoutLLM())
    timed = await client.post(
        "/api/v1/core/data-analysis/chat/stream",
        headers=_headers(),
        json={
            "datasourceId": datasource_id,
            "question": "有多少订单？",
            "tableNames": ["orders"],
            "modelId": model_id,
        },
    )
    parsed = parse_sse(timed.text)
    assert events_named(parsed, "timeout")
    assert parsed[-1] == "[DONE]"
    assert events_named(parsed, "analysis.table") == []

    await client.delete(f"/api/v1/aigc/models/{model_id}", headers=_headers())
    app.dependency_overrides.pop(get_analysis_runtime, None)
    monkeypatch.setenv("DEFAULT_MODEL_BASE_URL", "")
    monkeypatch.setenv("DEFAULT_MODEL_API_KEY", "")
    monkeypatch.setenv("DEFAULT_MODEL_NAME", "")
    get_settings.cache_clear()
    missing = await client.post(
        "/api/v1/core/data-analysis/chat/stream",
        headers=_headers(),
        json={"datasourceId": datasource_id, "question": "有多少订单？", "tableNames": ["orders"]},
    )
    missing_events = parse_sse(missing.text)
    assert events_named(missing_events, "error")[0]["code"] == "MODEL_CONFIG"
    assert missing_events[-1] == "[DONE]"


async def test_demo_page_is_served(client: AsyncClient) -> None:
    page = await client.get("/demo/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "问数" in page.text
