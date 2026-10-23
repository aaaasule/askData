"""Datasource CRUD, connection test, introspect, and read-only query."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import get_settings
from app.deps import get_datasource_service, require_api_key
from app.schemas.common import success
from app.schemas.datasource import (
    DatasourceCreate,
    DatasourceTestRequest,
    DatasourceUpdate,
    ReadOnlyQueryRequest,
    SaveStructureRequest,
)
from app.security.secrets import SecretError
from app.services.datasource_service import (
    DatasourceNotFoundError,
    DatasourceService,
    QueryExecutionError,
    QueryTimeoutError,
    enabled_table_names,
)
from app.services.sql_guard import SqlGuardError
from app.services.target_db import DatasourceDriverError

router = APIRouter(dependencies=[Depends(require_api_key)])
Svc = Annotated[DatasourceService, Depends(get_datasource_service)]


@router.get("")
async def list_datasources(svc: Svc) -> dict[str, Any]:
    return success(await svc.list_all())


@router.post("")
async def create_datasource(body: DatasourceCreate, svc: Svc) -> dict[str, Any]:
    created = await svc.create(body.model_dump())
    return success(created)


@router.post("/test")
async def test_datasource_body(body: DatasourceTestRequest, svc: Svc) -> dict[str, Any]:
    result = await svc.test_connection(None, body.model_dump())
    return success(result)


@router.get("/{datasource_id}")
async def get_datasource(datasource_id: str, svc: Svc) -> dict[str, Any]:
    item = await svc.get(datasource_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="datasource not found")
    return success(item)


@router.put("/{datasource_id}")
async def update_datasource(datasource_id: str, body: DatasourceUpdate, svc: Svc) -> dict[str, Any]:
    try:
        updated = await svc.update(datasource_id, body.model_dump(exclude_unset=True))
    except DatasourceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="datasource not found") from None
    return success(updated)


@router.delete("/{datasource_id}")
async def delete_datasource(datasource_id: str, svc: Svc) -> dict[str, Any]:
    try:
        await svc.delete(datasource_id)
    except DatasourceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="datasource not found") from None
    return success(None)


@router.post("/{datasource_id}/test")
async def test_datasource(datasource_id: str, svc: Svc) -> dict[str, Any]:
    try:
        result = await svc.test_connection(datasource_id, None)
    except DatasourceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="datasource not found") from None
    return success(result)


@router.post("/{datasource_id}/introspect")
async def introspect(datasource_id: str, svc: Svc) -> dict[str, Any]:
    try:
        structure = await svc.introspect(datasource_id)
    except DatasourceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="datasource not found") from None
    except (DatasourceDriverError, QueryExecutionError, SecretError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return success(structure)


@router.get("/{datasource_id}/structure")
async def structure(datasource_id: str, svc: Svc) -> dict[str, Any]:
    try:
        data = await svc.get_structure(datasource_id)
    except DatasourceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="datasource not found") from None
    return success(data)


@router.put("/{datasource_id}/structure")
async def save_structure(
    datasource_id: str,
    body: SaveStructureRequest,
    svc: Svc,
) -> dict[str, Any]:
    """Persist imported/enabled table authorization without a full datasource update."""
    parsed = _parse_structure(body.structure_json)
    try:
        saved = await svc.save_structure(datasource_id, parsed)
    except DatasourceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="datasource not found") from None
    return success(saved)


@router.post("/{datasource_id}/query")
async def query_readonly(datasource_id: str, body: ReadOnlyQueryRequest, svc: Svc) -> dict[str, Any]:
    """Thin internal read-only entry. AnalysisRuntime calls the service method later."""
    settings = get_settings()
    try:
        if body.tables is None:
            stored = await svc.get_structure(datasource_id)
            allowed = enabled_table_names(stored)
        else:
            allowed = set(body.tables)
        result = await svc.execute_read_only_query(
            datasource_id,
            body.sql,
            allowed,
            max_rows=body.max_rows if body.max_rows is not None else settings.sql_max_rows,
            timeout_seconds=(
                body.timeout_seconds
                if body.timeout_seconds is not None
                else settings.sql_timeout_seconds
            ),
        )
    except DatasourceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="datasource not found") from None
    except SqlGuardError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except QueryTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT, detail=str(exc)) from None
    except (DatasourceDriverError, QueryExecutionError, SecretError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return success(result)


def _parse_structure(value: dict[str, Any] | str) -> dict[str, Any]:
    """Accept LangChat's JSON string or an object. Reject anything that is not an object."""
    if isinstance(value, str):
        try:
            parsed: Any = json.loads(value)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="structureJson is not valid JSON",
            ) from exc
    else:
        parsed = value
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="structure must be a JSON object",
        )
    tables = parsed.get("tables")
    if tables is not None and not isinstance(tables, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tables must be a list",
        )
    return parsed
