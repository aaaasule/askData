"""OpenAI-compatible chat completions streaming client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI


class LLMError(RuntimeError):
    def __init__(self, message: str, *, code: str = "LLM_ERROR") -> None:
        super().__init__(message)
        self.code = code


class LLMTimeoutError(LLMError):
    def __init__(self, message: str = "model request timed out") -> None:
        super().__init__(message, code="TIMEOUT")


def normalize_base_url(base_url: str, endpoint: str = "") -> str:
    """Return an OpenAI SDK base_url (no trailing /chat/completions)."""
    raw = (base_url or endpoint or "").strip()
    if not raw:
        raise LLMError("model base_url is empty", code="MODEL_CONFIG")
    raw = raw.rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)].rstrip("/")
            break
    if not raw:
        raise LLMError("model base_url is empty", code="MODEL_CONFIG")
    return raw


class OpenAICompatibleClient:
    """Stream chat completions from any OpenAI-compatible endpoint."""

    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout

    async def stream(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield content deltas, then one tool_calls event when tools were requested."""
        client = AsyncOpenAI(
            api_key=api_key or "missing",
            base_url=base_url,
            timeout=self.timeout,
        )
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature
        if top_p is not None:
            kwargs["top_p"] = top_p
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        pending: dict[int, dict[str, str]] = {}
        try:
            stream = await client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta is None:
                    continue
                if delta.content:
                    yield {"kind": "content", "text": delta.content}
                for tool_call in delta.tool_calls or []:
                    slot = pending.setdefault(
                        tool_call.index or 0,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    if tool_call.id:
                        slot["id"] = tool_call.id
                    function = tool_call.function
                    if function is None:
                        continue
                    if function.name:
                        slot["name"] += function.name
                    if function.arguments:
                        slot["arguments"] += function.arguments
        except APITimeoutError as exc:
            raise LLMTimeoutError(_public_message(exc, api_key)) from exc
        except (APIError, APIConnectionError) as exc:
            raise LLMError(_public_message(exc, api_key)) from exc
        finally:
            await client.close()
        if not pending:
            return
        calls = [pending[index] for index in sorted(pending)]
        for call in calls:
            if not call["id"]:
                call["id"] = f"call_{uuid4().hex[:12]}"
        yield {"kind": "tool_calls", "calls": calls}


def _public_message(exc: Exception, secret: str) -> str:
    text = str(exc) or exc.__class__.__name__
    if secret:
        text = text.replace(secret, "***")
    return text[:500]
