"""Datasource request/response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DatasourceCreate(BaseModel):
    name: str
    db_type: str = Field(description="mysql | postgres | ...")
    host: str = ""
    port: int | None = None
    database: str = ""
    username: str = ""
    password: str = ""
    jdbc_url: str | None = None
    extra: dict[str, Any] | None = None


class DatasourceUpdate(BaseModel):
    name: str | None = None
    db_type: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    jdbc_url: str | None = None
    extra: dict[str, Any] | None = None
    structure_json: dict[str, Any] | None = None


class DatasourceOut(BaseModel):
    id: str
    name: str
    db_type: str
    host: str = ""
    port: int | None = None
    database: str = ""
    username: str = ""
    # password omitted in responses by default
    jdbc_url: str | None = None
    structure_json: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DatasourceTestRequest(BaseModel):
    """Connection fields for POST /datasources/test (nothing is persisted)."""

    db_type: str
    host: str = ""
    port: int | None = None
    database: str = ""
    username: str = ""
    password: str = ""
    jdbc_url: str | None = None
    name: str = ""


class DatasourceTestResult(BaseModel):
    ok: bool
    message: str = ""
    latency_ms: int | None = None


class ReadOnlyQueryRequest(BaseModel):
    """Internal read-only query the analysis runtime will call later."""

    sql: str
    tables: list[str] | None = None
    max_rows: int | None = Field(default=None, ge=1)
    timeout_seconds: int | None = Field(default=None, ge=1)
