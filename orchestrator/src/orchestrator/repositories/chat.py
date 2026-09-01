"""Conversation and message persistence with patient ownership."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import Conversation, Message


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, patient_user_id: UUID, title: str) -> Conversation:
        conversation = Conversation(patient_user_id=patient_user_id, title=title)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get_owned(
        self, conversation_id: UUID, patient_user_id: UUID
    ) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.patient_user_id == patient_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_owned(
        self, patient_user_id: UUID, limit: int = 50
    ) -> list[tuple[Conversation, int, str | None]]:
        conversations = list(
            (
                await self.session.execute(
                    select(Conversation)
                    .where(Conversation.patient_user_id == patient_user_id)
                    .order_by(Conversation.updated_at.desc())
                    .limit(limit)
                )
            ).scalars()
        )
        rows: list[tuple[Conversation, int, str | None]] = []
        for conversation in conversations:
            count = (
                await self.session.execute(
                    select(func.count(Message.id)).where(
                        Message.conversation_id == conversation.id
                    )
                )
            ).scalar_one()
            last = (
                await self.session.execute(
                    select(Message.content)
                    .where(Message.conversation_id == conversation.id)
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            rows.append((conversation, count, last))
        return rows

    async def list_messages(
        self, conversation_id: UUID, *, newest_first: bool = False, limit: int | None = None
    ) -> list[Message]:
        order = Message.created_at.desc() if newest_first else Message.created_at.asc()
        query = select(Message).where(Message.conversation_id == conversation_id).order_by(order)
        if limit:
            query = query.limit(limit)
        return list((await self.session.execute(query)).scalars())

    async def add_message(
        self,
        *,
        conversation_id: UUID,
        user_id: UUID | None,
        role: str,
        content: str,
        evidence_refs: dict | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=content,
            evidence_refs=evidence_refs,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def touch(self, conversation: Conversation) -> None:
        conversation.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
