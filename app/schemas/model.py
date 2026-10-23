"""Light model-management schemas (自建轻量模型表)."""

from datetime import datetime

from pydantic import BaseModel, Field


class ModelCreate(BaseModel):
    name: str
    provider: str = Field(default="openai-compatible", description="openai-compatible | ...")
    base_url: str = ""
    api_key: str = ""
    model_name: str = Field(description="Upstream model id, e.g. gpt-4o-mini")
    enabled: bool = True
    extra: dict | None = None


class ModelUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    enabled: bool | None = None
    extra: dict | None = None


class ModelOut(BaseModel):
    id: str
    name: str
    provider: str
    base_url: str = ""
    # api_key omitted or masked in responses
    model_name: str
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
