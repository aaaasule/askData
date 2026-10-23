"""SQLAlchemy models: datasources + light model registry."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def _uuid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class AigcDatasource(Base):
    """Mirrors LangChat aigc_datasource fields needed for 问数 (no Agent/RAG)."""

    __tablename__ = "aigc_datasource"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    db_type: Mapped[str] = mapped_column(String(32), nullable=False, default="mysql")
    host: Mapped[str] = mapped_column(String(255), default="")
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    database: Mapped[str] = mapped_column(String(128), default="")
    username: Mapped[str] = mapped_column(String(128), default="")
    # Fernet ciphertext (enc:v1:...). Legacy plaintext is rewritten on read.
    password: Mapped[str] = mapped_column(Text, default="")
    jdbc_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    structure_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AigcModel(Base):
    """Light model management table (自建轻量模型管理)."""

    __tablename__ = "aigc_model"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), default="openai-compatible")
    # Upstream model id. API field name is `model` (alias `model_name`).
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), default="chat", server_default="chat")
    base_url: Mapped[str] = mapped_column(String(512), default="")
    endpoint: Mapped[str] = mapped_column(String(512), default="")
    # Fernet ciphertext (enc:v1:...). API responses only ever return a mask.
    api_key: Mapped[str] = mapped_column(Text, default="")
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_token: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AigcConversation(Base):
    """One analysis thread for a datasource, optionally pinned to a model."""

    __tablename__ = "aigc_conversation"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    datasource_id: Mapped[str] = mapped_column(String(36), index=True)
    model_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AigcMessage(Base):
    """A single user or assistant turn inside a conversation."""

    __tablename__ = "aigc_message"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(String(128), index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
