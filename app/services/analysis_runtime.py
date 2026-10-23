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

    async def execute_read_only_query(
        self, service: Any, *args: Any, **kwargs: Any
    ) -> dict[str, Any]:
        """Delegate to DatasourceService.execute_read_only_query for the future tool loop."""
        return await service.execute_read_only_query(*args, **kwargs)

    async def catalog(self, datasource_id: str, structure: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return imported==true and enabled!=false tables from structure_json."""
        tables: list[dict[str, Any]] = []
        for table in (structure or {}).get("tables") or []:
            if table.get("imported", True) and table.get("enabled", True) is not False:
                tables.append(
                    {
                        "name": table.get("name"),
                        "comment": table.get("comment"),
                        "imported": True,
                        "enabled": True,
                        "columns": table.get("columns"),
                    }
                )
        return {"datasourceId": datasource_id, "tables": tables}
