"""Shared JSON envelope: {code, message, data} with SUCCESS."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: str = Field(default="SUCCESS", description="SUCCESS or error code")
    message: str = Field(default="ok")
    data: T | None = None


def success(data: Any = None, message: str = "ok") -> dict[str, Any]:
    """Build a SUCCESS envelope dict (JSON routes only; not for SSE)."""
    return {"code": "SUCCESS", "message": message, "data": data}
