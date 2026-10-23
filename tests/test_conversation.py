"""Server-side analysis history is scoped by conversation id."""

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
from app.services.conversation_store import trim_history
from tests.sse_utils import events_named, parse_sse
from tests.test_analysis_stream import ScriptedLLM, _datasource, _headers, _model, _seed


@pytest.fixture
def scripted_runtime():
    holder: dict[str, ScriptedLLM] = {}

    def install(llm: ScriptedLLM):
        holder["llm"] = llm

        def _override(session: Annotated[AsyncSession, Depends(get_db)]) -> AnalysisRuntime:
            return AnalysisRuntime(session, llm=holder["llm"])

        app.dependency_overrides[get_analysis_runtime] = _override
        return llm

    yield install
    app.dependency_overrides.pop(get_analysis_runtime, None)


def test_trim_history_keeps_the_newest_budget() -> None:
    messages = [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "1111"},
        {"role": "user", "content": "two"},
        {"role": "assistant", "content": "2222"},
    ]
    assert trim_history(messages, max_messages=2, max_chars=100) == messages[-2:]
    assert trim_history(messages, max_messages=4, max_chars=4) == [
        {"role": "assistant", "content": "2222"}
    ]
    assert trim_history(messages, max_messages=0, max_chars=100) == []


def _content_rounds(text: str) -> list[list[dict]]:
    return [
        [{"kind": "content", "text": text}],
        [{"kind": "content", "text": ""}],
    ]


def _calls_for(llm: ScriptedLLM, question: str) -> list[dict]:
    return [
        call
        for call in llm.seen
        if call["messages"][-1].get("content") == question
    ]


async def _ask(
    client: AsyncClient,
    llm: ScriptedLLM,
    scripted_runtime,
    *,
    datasource_id: str,
    model_id: str,
    question: str,
    conversation_id: str | None,
) -> str:
    scripted_runtime(llm)
    body: dict[str, object] = {
        "datasourceId": datasource_id,
        "question": question,
        "tableNames": ["orders"],
        "modelId": model_id,
    }
    if conversation_id is not None:
        body["conversationId"] = conversation_id
    response = await client.post(
        "/api/v1/core/data-analysis/chat/stream",
        headers=_headers(),
        json=body,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert not response.text.lstrip().startswith("{")
    parsed = parse_sse(response.text)
    assert parsed[-1] == "[DONE]"
    return events_named(parsed, "message.start")[0]["conversation_id"]


async def test_second_turn_sees_first_turn_and_new_id_is_isolated(
    client: AsyncClient, app_home: Path, scripted_runtime
) -> None:
    biz = app_home / "orders.db"
    _seed(biz)
    datasource_id = await _datasource(client, str(biz))
    model_id = await _model(client)
    llm = ScriptedLLM(
        [
            *_content_rounds("第一轮答案"),
            *_content_rounds("第二轮答案"),
            *_content_rounds("隔离答案"),
        ]
    )
    first = "每个名字有多少订单？"
    second = "沿用上一轮的结论"
    other = "这是另一段对话"
    conversation_id = await _ask(
        client,
        llm,
        scripted_runtime,
        datasource_id=datasource_id,
        model_id=model_id,
        question=first,
        conversation_id=None,
    )
    assert conversation_id
    again = await _ask(
        client,
        llm,
        scripted_runtime,
        datasource_id=datasource_id,
        model_id=model_id,
        question=second,
        conversation_id=conversation_id,
    )
    assert again == conversation_id
    follow = _calls_for(llm, second)
    assert follow
    roles = [(item["role"], item.get("content")) for item in follow[0]["messages"]]
    assert ("user", first) in roles
    assert any(role == "assistant" and "第一轮答案" in (content or "") for role, content in roles)
    assert roles[-1] == ("user", second)

    listed = await client.get(
        f"/api/v1/core/data-analysis/conversations/{conversation_id}/messages",
        headers=_headers(),
    )
    assert listed.status_code == 200
    assert listed.json()["code"] == "SUCCESS"
    contents = [item["content"] for item in listed.json()["data"]]
    assert first in contents
    assert any("第一轮答案" in content for content in contents)

    isolated = await _ask(
        client,
        llm,
        scripted_runtime,
        datasource_id=datasource_id,
        model_id=model_id,
        question=other,
        conversation_id="conv-other",
    )
    assert isolated == "conv-other"
    foreign = _calls_for(llm, other)
    assert foreign
    blob = json.dumps(foreign[0]["messages"], ensure_ascii=False)
    assert first not in blob
    assert "第一轮答案" not in blob

    missing = await client.get(
        "/api/v1/core/data-analysis/conversations/missing",
        headers=_headers(),
    )
    assert missing.status_code == 404
    cleared = await client.delete(
        f"/api/v1/core/data-analysis/conversations/{conversation_id}",
        headers=_headers(),
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"] is None
    gone = await client.get(
        f"/api/v1/core/data-analysis/conversations/{conversation_id}/messages",
        headers=_headers(),
    )
    assert gone.status_code == 404


async def test_history_cap_drops_older_turns(
    client: AsyncClient,
    app_home: Path,
    scripted_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    biz = app_home / "orders.db"
    _seed(biz)
    datasource_id = await _datasource(client, str(biz))
    model_id = await _model(client)
    llm = ScriptedLLM([*_content_rounds("只有这一句"), *_content_rounds("下一句")])
    conversation_id = await _ask(
        client,
        llm,
        scripted_runtime,
        datasource_id=datasource_id,
        model_id=model_id,
        question="第一问很独特",
        conversation_id="conv-cap",
    )
    monkeypatch.setenv("CONVERSATION_MAX_MESSAGES", "1")
    monkeypatch.setenv("CONVERSATION_MAX_CHARS", "12000")
    get_settings.cache_clear()
    await _ask(
        client,
        llm,
        scripted_runtime,
        datasource_id=datasource_id,
        model_id=model_id,
        question="第二问",
        conversation_id=conversation_id,
    )
    follow = _calls_for(llm, "第二问")
    assert follow
    contents = [item.get("content") for item in follow[0]["messages"]]
    assert "第一问很独特" not in contents
    assert any(content and "只有这一句" in content for content in contents)

    connection = sqlite3.connect(biz)
    try:
        count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    finally:
        connection.close()
    assert count == 2
