"""Light model CRUD. Responses mask api_key; auth stays on the API key dependency."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import require_api_key
from app.schemas.common import success
from app.schemas.model import ModelCreate, ModelUpdate
from app.services.model_service import ModelNotFoundError, ModelService

router = APIRouter(dependencies=[Depends(require_api_key)])
Svc = Annotated[AsyncSession, Depends(get_db)]


def _service(session: AsyncSession) -> ModelService:
    return ModelService(session)


@router.get("")
async def list_models(session: Svc) -> dict[str, Any]:
    return success(await _service(session).list_all())


@router.post("")
async def create_model(body: ModelCreate, session: Svc) -> dict[str, Any]:
    created = await _service(session).create(body.model_dump())
    return success(created)


@router.get("/{model_id}")
async def get_model(model_id: str, session: Svc) -> dict[str, Any]:
    item = await _service(session).get(model_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model not found")
    return success(item)


@router.put("/{model_id}")
async def update_model(model_id: str, body: ModelUpdate, session: Svc) -> dict[str, Any]:
    try:
        updated = await _service(session).update(model_id, body.model_dump(exclude_unset=True))
    except ModelNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model not found") from None
    return success(updated)


@router.delete("/{model_id}")
async def delete_model(model_id: str, session: Svc) -> dict[str, Any]:
    try:
        await _service(session).delete(model_id)
    except ModelNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model not found") from None
    return success(None)
