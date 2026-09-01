"""Unified user and refresh-session persistence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import AuthSession, PatientProfile, User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email.strip().lower())
        )
        return result.scalar_one_or_none()

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def add_patient_profile(self, profile: PatientProfile) -> PatientProfile:
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def get_patient_profile(self, user_id: UUID) -> PatientProfile | None:
        return await self.session.get(PatientProfile, user_id)


class AuthSessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, auth_session: AuthSession) -> AuthSession:
        self.session.add(auth_session)
        await self.session.flush()
        return auth_session

    async def get_active_by_hash(
        self, token_hash: str, now: datetime, *, lock: bool = False
    ) -> AuthSession | None:
        query = select(AuthSession).where(
            AuthSession.refresh_token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
        if lock:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def revoke(self, auth_session: AuthSession, now: datetime) -> None:
        auth_session.revoked_at = now
        auth_session.last_used_at = now
        await self.session.flush()
