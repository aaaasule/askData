"""Light model CRUD — stubs."""

from typing import Any

from fastapi import APIRouter, Depends

from app.deps import require_api_key
from app.schemas.common import success
from app.schemas.model import ModelCreate, ModelUpdate

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("")
async def list_models() -> dict[str, Any]:
    return success([])


@router.post("")
async def create_model(body: ModelCreate) -> dict[str, Any]:
    _ = body
    return success(None, message="NotImplemented: create model")


@router.get("/{model_id}")
async def get_model(model_id: str) -> dict[str, Any]:
    _ = model_id
    return success(None)


@router.put("/{model_id}")
async def update_model(model_id: str, body: ModelUpdate) -> dict[str, Any]:
    _ = model_id, body
    return success(None, message="NotImplemented: update model")


@router.delete("/{model_id}")
async def delete_model(model_id: str) -> dict[str, Any]:
    _ = model_id
    return success(None, message="NotImplemented: delete model")
