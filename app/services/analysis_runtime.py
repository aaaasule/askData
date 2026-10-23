"""NL → SQL tool loop + SSE streaming — stub."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.services import sse_assembler as sse


class AnalysisRuntime:
    """
    TODO:
      - load datasource structure / selected tables
      - resolve model from light model table (or default config)
      - tool loop: query_data / inspect_selected_tables / get_current_time
      - emit LangChat-aligned analysis SSE events via sse_assembler
    """

    async def chat_stream(
        self,
        *,
        datasource_id: str,
        question: str,
        table_names: list[str],
        model_id: str | None = None,
    ) -> AsyncIterator[str]:
        _ = datasource_id, question, table_names, model_id
        # Stub: acknowledge then finish — replace with real LLM+tool loop
        yield sse.message_delta("AskData analysis runtime is not implemented yet.\n")
        yield sse.done()

    async def catalog(self, datasource_id: str) -> dict[str, Any]:
        """Return imported==true and enabled!=false tables from structure_json."""
        _ = datasource_id
        return {"datasourceId": datasource_id, "tables": []}
