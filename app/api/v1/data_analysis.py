"""智能问数: catalog + SSE chat/stream."""

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.deps import require_api_key
from app.schemas.analysis import AnalysisChatRequest
from app.schemas.common import success
from app.services.analysis_runtime import AnalysisRuntime
from app.services import sse_assembler as sse

router = APIRouter(dependencies=[Depends(require_api_key)])
_runtime = AnalysisRuntime()


@router.get("/catalog")
async def catalog(datasource_id: str = Query(..., alias="datasourceId")) -> dict[str, Any]:
    data = await _runtime.catalog(datasource_id)
    return success(data)


@router.post("/chat/stream")
async def chat_stream(body: AnalysisChatRequest) -> StreamingResponse:
    async def gen() -> AsyncIterator[bytes]:
        async for chunk in _runtime.chat_stream(
            datasource_id=body.datasource_id,
            question=body.question,
            table_names=body.table_names,
            model_id=body.model_id,
        ):
            yield chunk.encode("utf-8")
        # runtime already yields [DONE]; keep a safety net if a future impl forgets
        # (no-op if already sent — callers should not double-send in production)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/_sse-ping")
async def sse_ping() -> StreamingResponse:
    """Dev helper: emit one message.delta then [DONE] without LLM."""

    async def gen() -> AsyncIterator[bytes]:
        yield sse.message_delta("pong").encode("utf-8")
        yield sse.done().encode("utf-8")

    return StreamingResponse(gen(), media_type="text/event-stream")
