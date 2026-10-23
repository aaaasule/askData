"""Base URL normalization for OpenAI-compatible endpoints. No network."""

from __future__ import annotations

import pytest

from app.services.llm_client import LLMError, normalize_base_url


def test_normalize_base_url_strips_completions_suffix() -> None:
    assert normalize_base_url("https://llm.example/v1/", "") == "https://llm.example/v1"
    assert normalize_base_url("", "https://llm.example/v1/chat/completions") == (
        "https://llm.example/v1"
    )
    assert normalize_base_url("https://llm.example/v1", "https://ignored.example") == (
        "https://llm.example/v1"
    )


def test_normalize_base_url_requires_a_value() -> None:
    with pytest.raises(LLMError):
        normalize_base_url("  ", "")
