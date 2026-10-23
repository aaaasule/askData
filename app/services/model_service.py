"""CRUD for the light aigc_model registry. API responses mask api_key."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AigcModel
from app.schemas.model import ModelOut
from app.security.api_key import mask_api_key

_UPDATABLE = {
    "name",
    "provider",
    "model",
    "type",
    "base_url",
    "endpoint",
    "api_key",
    "temperature",
    "top_p",
    "max_token",
    "config_json",
    "enabled",
    "extra",
}


class ModelNotFoundError(LookupError):
    """No model row for the given id."""


class ModelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(AigcModel).order_by(AigcModel.created_at.desc(), AigcModel.id)
        )
        return [_to_out(row) for row in result.scalars().all()]

    async def get(self, model_id: str) -> dict[str, Any] | None:
        row = await self.session.get(AigcModel, model_id)
        if row is None:
            return None
        return _to_out(row)

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = AigcModel(
            name=payload["name"],
            provider=payload.get("provider") or "openai-compatible",
            model_name=_model_id(payload),
            type=payload.get("type") or "chat",
            base_url=payload.get("base_url") or "",
            endpoint=payload.get("endpoint") or "",
            api_key=payload.get("api_key") or "",
            temperature=payload.get("temperature", 0.2),
            top_p=payload.get("top_p"),
            max_token=payload.get("max_token"),
            config_json=payload.get("config_json"),
            enabled=True if payload.get("enabled") is None else bool(payload.get("enabled")),
            extra=payload.get("extra"),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return _to_out(row)

    async def update(self, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = await self._require(model_id)
        data = dict(payload)
        if "model" in data or "model_name" in data:
            renamed = _model_id(data)
            if renamed:
                data["model"] = renamed
        if "api_key" in data and _is_masked_echo(data.get("api_key"), row.api_key):
            data.pop("api_key")
        for key, value in data.items():
            if key not in _UPDATABLE:
                continue
            if key == "model":
                if value:
                    row.model_name = str(value)
                continue
            setattr(row, key, value)
        row.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(row)
        return _to_out(row)

    async def delete(self, model_id: str) -> None:
        row = await self._require(model_id)
        await self.session.delete(row)
        await self.session.commit()

    async def _require(self, model_id: str) -> AigcModel:
        row = await self.session.get(AigcModel, model_id)
        if row is None:
            raise ModelNotFoundError(model_id)
        return row


def _model_id(payload: dict[str, Any]) -> str:
    return str(payload.get("model") or payload.get("model_name") or "").strip()


def _is_masked_echo(submitted: Any, stored: str) -> bool:
    """Ignore list/get echoes and blank updates so a key is not wiped or rewritten."""
    if submitted is None:
        return True
    text = str(submitted).strip()
    if not text:
        return True
    return text == mask_api_key(stored)


def _to_out(row: AigcModel) -> dict[str, Any]:
    payload = ModelOut(
        id=row.id,
        name=row.name,
        provider=row.provider,
        model=row.model_name,
        model_name=row.model_name,
        type=row.type or "chat",
        base_url=row.base_url or "",
        endpoint=row.endpoint or "",
        api_key=mask_api_key(row.api_key),
        temperature=row.temperature,
        top_p=row.top_p,
        max_token=row.max_token,
        config_json=row.config_json,
        enabled=bool(row.enabled),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return payload.model_dump(mode="json")
