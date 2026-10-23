"""Parse the analysis SSE wire format in tests."""

from __future__ import annotations

import json
from typing import Any


def parse_sse(body: str) -> list[Any]:
    events: list[Any] = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if not data:
                continue
            events.append("[DONE]" if data == "[DONE]" else json.loads(data))
    return events


def deltas_named(events: list[Any], name: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        delta = event["choices"][0]["delta"]
        if (delta.get("event") or {}).get("name") == name:
            found.append(delta)
    return found


def events_named(events: list[Any], name: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        payload = event["choices"][0]["delta"].get("event") or {}
        if payload.get("name") == name:
            found.append(payload)
    return found
