"""JWT auth for Dentist Portal."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from orchestrator.dentist_portal.db import get_portal_users_col
from orchestrator.dentist_portal.models import UserRole

import os

logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv("PORTAL_JWT_SECRET", "dantshaant-portal-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_dentist(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != UserRole.DENTIST:
        raise HTTPException(status_code=403, detail="Dentist role required")
    return user


async def get_current_patient(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Patient role required")
    return user


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
