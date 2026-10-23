"""Analysis turns stored in the application database, keyed by conversation id."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import AigcConversation, AigcMessage

_MAX_ID_LEN = 128


class ConversationNotFoundError(LookupError):
    """No conversation row for the given id."""


def trim_history(
    messages: list[dict[str, str]],
    *,
    max_messages: int,
    max_chars: int,
) -> list[dict[str, str]]:
    """Keep the newest turns that fit the message count and character budget."""
    if max_messages < 1 or max_chars < 1:
        return []
    window = messages[-max_messages:]
    kept: list[dict[str, str]] = []
    used = 0
    for message in reversed(window):
        content = message.get("content") or ""
        if kept and used + len(content) > max_chars:
            break
        if not kept and len(content) > max_chars:
            content = content[-max_chars:]
        kept.append({"role": message["role"], "content": content})
        used += len(content)
    kept.reverse()
    return kept


class ConversationStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def open(
        self,
        conversation_id: str | None,
        datasource_id: str,
        model_id: str | None,
    ) -> tuple[str, list[dict[str, str]]]:
        """Return the id to echo and prior user/assistant turns for this scope.

        A missing id is created. An id that belongs to another datasource, or
        to a different model when both sides name one, is left untouched and
        replaced with a new id so histories stay isolated.
        """
        requested = _clean_id(conversation_id)
        row = await self.session.get(AigcConversation, requested) if requested else None
        if row is None or not _same_scope(row, datasource_id, model_id):
            created = AigcConversation(
                id=requested or str(uuid4()),
                datasource_id=datasource_id,
                model_id=model_id,
            )
            if row is not None:
                created.id = str(uuid4())
            self.session.add(created)
            await self.session.commit()
            await self.session.refresh(created)
            return created.id, []
        if model_id and not row.model_id:
            row.model_id = model_id
            row.updated_at = datetime.now(UTC)
            await self.session.commit()
        return row.id, await self._history(row.id)

    async def append_turn(self, conversation_id: str, user_text: str, assistant_text: str) -> None:
        row = await self.session.get(AigcConversation, conversation_id)
        if row is None or not (user_text or assistant_text):
            return
        result = await self.session.execute(
            select(func.max(AigcMessage.seq)).where(AigcMessage.conversation_id == conversation_id)
        )
        start = int(result.scalar_one() or 0)
        now = datetime.now(UTC)
        self.session.add(
            AigcMessage(
                conversation_id=conversation_id,
                seq=start + 1,
                role="user",
                content=user_text,
                created_at=now,
            )
        )
        self.session.add(
            AigcMessage(
                conversation_id=conversation_id,
                seq=start + 2,
                role="assistant",
                content=assistant_text,
                created_at=now,
            )
        )
        row.updated_at = now
        await self.session.commit()

    async def get(self, conversation_id: str) -> dict[str, Any] | None:
        row = await self.session.get(AigcConversation, conversation_id)
        if row is None:
            return None
        return _conversation_out(row)

    async def list_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        row = await self.session.get(AigcConversation, conversation_id)
        if row is None:
            raise ConversationNotFoundError(conversation_id)
        result = await self.session.execute(
            select(AigcMessage)
            .where(AigcMessage.conversation_id == conversation_id)
            .order_by(AigcMessage.seq.asc(), AigcMessage.created_at.asc())
        )
        return [_message_out(message) for message in result.scalars().all()]

    async def clear(self, conversation_id: str) -> None:
        row = await self.session.get(AigcConversation, conversation_id)
        if row is None:
            raise ConversationNotFoundError(conversation_id)
        result = await self.session.execute(
            select(AigcMessage).where(AigcMessage.conversation_id == conversation_id)
        )
        for message in result.scalars().all():
            await self.session.delete(message)
        await self.session.delete(row)
        await self.session.commit()

    async def _history(self, conversation_id: str) -> list[dict[str, str]]:
        result = await self.session.execute(
            select(AigcMessage)
            .where(AigcMessage.conversation_id == conversation_id)
            .order_by(AigcMessage.seq.asc(), AigcMessage.created_at.asc())
        )
        messages = [
            {"role": row.role, "content": row.content or ""}
            for row in result.scalars().all()
            if row.role in {"user", "assistant"}
        ]
        settings = get_settings()
        return trim_history(
            messages,
            max_messages=settings.conversation_max_messages,
            max_chars=settings.conversation_max_chars,
        )


def _same_scope(row: AigcConversation, datasource_id: str, model_id: str | None) -> bool:
    if row.datasource_id != datasource_id:
        return False
    return not model_id or not row.model_id or row.model_id == model_id


def _clean_id(conversation_id: str | None) -> str | None:
    text = (conversation_id or "").strip()
    if not text or len(text) > _MAX_ID_LEN:
        return None
    return text


def _conversation_out(row: AigcConversation) -> dict[str, Any]:
    return {
        "id": row.id,
        "datasource_id": row.datasource_id,
        "model_id": row.model_id,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _message_out(row: AigcMessage) -> dict[str, Any]:
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "role": row.role,
        "content": row.content,
        "created_at": _iso(row.created_at),
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
