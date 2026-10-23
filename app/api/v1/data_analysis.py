"""智能问数: catalog + SSE chat/stream."""

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.deps import get_analysis_runtime, get_datasource_service, require_api_key
from app.schemas.analysis import AnalysisChatRequest
from app.schemas.common import success
from app.services import sse_assembler as sse
from app.services.analysis_runtime import AnalysisRuntime
from app.services.catalog import build_catalog
from app.services.datasource_service import DatasourceNotFoundError, DatasourceService

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/catalog")
async def catalog(
    svc: Annotated[DatasourceService, Depends(get_datasource_service)],
    datasource_id: str = Query(..., alias="datasourceId"),
) -> dict[str, Any]:
    try:
        structure = await svc.get_structure(datasource_id)
    except DatasourceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="datasource not found"
        ) from None
    return success(build_catalog(datasource_id, structure))


@router.post("/chat/stream")
async def chat_stream(
    body: AnalysisChatRequest,
    runtime: Annotated[AnalysisRuntime, Depends(get_analysis_runtime)],
) -> StreamingResponse:
    async def gen() -> AsyncIterator[bytes]:
        async for chunk in runtime.chat_stream(
            datasource_id=body.datasource_id,
            question=body.question,
            table_names=body.table_names,
            model_id=body.model_id,
            conversation_id=body.conversation_id,
        ):
            yield chunk.encode("utf-8")

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
    """Dev helper: emit one message.delta then [DONE] without an LLM."""

    async def gen() -> AsyncIterator[bytes]:
        yield sse.message_delta("pong").encode("utf-8")
        yield sse.done().encode("utf-8")

    return StreamingResponse(gen(), media_type="text/event-stream")
