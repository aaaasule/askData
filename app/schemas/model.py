"""Light model-management schemas (自建轻量模型表)."""

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, Field, model_validator


class ModelCreate(BaseModel):
    name: str
    provider: str = Field(default="openai-compatible")
    model: str | None = Field(default=None, description="Upstream model id, e.g. gpt-4o-mini")
    model_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("model_name", "modelName"),
    )
    type: str = "chat"
    base_url: str = ""
    endpoint: str = ""
    api_key: str = ""
    temperature: float | None = Field(default=0.2, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_token: int | None = Field(
        default=None,
        ge=1,
        le=1_000_000,
        validation_alias=AliasChoices("max_token", "max_tokens", "maxToken"),
    )
    config_json: dict[str, Any] | None = None
    enabled: bool = True
    extra: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _require_model_id(self) -> "ModelCreate":
        resolved = (self.model or self.model_name or "").strip()
        if not resolved:
            raise ValueError("model is required")
        self.model = resolved
        self.model_name = resolved
        return self


class ModelUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    model: str | None = None
    model_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("model_name", "modelName"),
    )
    type: str | None = None
    base_url: str | None = None
    endpoint: str | None = None
    api_key: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_token: int | None = Field(
        default=None,
        ge=1,
        le=1_000_000,
        validation_alias=AliasChoices("max_token", "max_tokens", "maxToken"),
    )
    config_json: dict[str, Any] | None = None
    enabled: bool | None = None
    extra: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _alias_model_id(self) -> "ModelUpdate":
        if self.model and not self.model_name:
            self.model_name = self.model.strip()
        elif self.model_name and not self.model:
            self.model = self.model_name.strip()
        elif self.model:
            self.model = self.model.strip()
            self.model_name = self.model
        return self


class ModelOut(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    model_name: str
    type: str = "chat"
    base_url: str = ""
    endpoint: str = ""
    api_key: str = ""
    temperature: float | None = None
    top_p: float | None = None
    max_token: int | None = None
    config_json: dict[str, Any] | None = None
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
