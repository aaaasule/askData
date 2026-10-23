"""Datasource CRUD + test / introspect / structure — stubs."""

from typing import Any

from fastapi import APIRouter, Depends

from app.deps import require_api_key
from app.schemas.common import success
from app.schemas.datasource import DatasourceCreate, DatasourceUpdate
from app.services.datasource_service import DatasourceService

router = APIRouter(dependencies=[Depends(require_api_key)])
_svc = DatasourceService()


@router.get("")
async def list_datasources() -> dict[str, Any]:
    items = await _svc.list_all()
    return success(items)


@router.post("")
async def create_datasource(body: DatasourceCreate) -> dict[str, Any]:
    # TODO: await _svc.create(body.model_dump())
    return success(None, message="NotImplemented: create datasource")


@router.get("/{datasource_id}")
async def get_datasource(datasource_id: str) -> dict[str, Any]:
    item = await _svc.get(datasource_id)
    return success(item)


@router.put("/{datasource_id}")
async def update_datasource(datasource_id: str, body: DatasourceUpdate) -> dict[str, Any]:
    _ = datasource_id, body
    return success(None, message="NotImplemented: update datasource")


@router.delete("/{datasource_id}")
async def delete_datasource(datasource_id: str) -> dict[str, Any]:
    _ = datasource_id
    return success(None, message="NotImplemented: delete datasource")


@router.post("/test")
async def test_datasource_body(body: dict[str, Any] | None = None) -> dict[str, Any]:
    result = await _svc.test_connection(None, body)
    return success(result)


@router.post("/{datasource_id}/test")
async def test_datasource(datasource_id: str) -> dict[str, Any]:
    result = await _svc.test_connection(datasource_id, None)
    return success(result)


@router.post("/{datasource_id}/introspect")
async def introspect(datasource_id: str) -> dict[str, Any]:
    _ = datasource_id
    return success(None, message="NotImplemented: introspect")


@router.get("/{datasource_id}/structure")
async def structure(datasource_id: str) -> dict[str, Any]:
    data = await _svc.get_structure(datasource_id)
    return success(data)
