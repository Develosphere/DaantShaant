"""Unified PostgreSQL-backed access and refresh authentication."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.config import settings
from orchestrator.db.session import get_db_session
from orchestrator.dentist_portal.models import UserRole
from orchestrator.repositories import UserRepository

_password_hasher = PasswordHasher(type=Type.ID)
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return _password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _password_hasher.verify(hashed, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def create_access_token(user_id: UUID, email: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(
        payload, settings.require_jwt_secret(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(
        token,
        settings.require_jwt_secret(),
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    return payload


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = UUID(payload["sub"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    user = await UserRepository(session).get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Account not found")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account is disabled")
    return {
        "sub": str(user.id),
        "user_id": user.id,
        "email": user.email,
        "role": user.role,
    }


async def get_current_dentist(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != UserRole.DENTIST.value:
        raise HTTPException(status_code=403, detail="Dentist role required")
    return user


async def get_current_patient(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != UserRole.PATIENT.value:
        raise HTTPException(status_code=403, detail="Patient role required")
    return user


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
