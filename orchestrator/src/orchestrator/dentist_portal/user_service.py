"""Portal user registration, login, and profile helpers."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from orchestrator.dentist_portal.auth import create_token, hash_password, verify_password
from orchestrator.dentist_portal.constants import DEFAULT_PROFILE_IMAGE
from orchestrator.dentist_portal.db import get_portal_users_col
from orchestrator.dentist_portal.models import (
    AdminRegisterRequest,
    DentistRegisterRequest,
    LoginRequest,
    PatientRegisterRequest,
    TokenResponse,
    UserProfileResponse,
    UserRole,
)

logger = logging.getLogger(__name__)

_MAX_IMAGE_CHARS = 500_000


def _full_name(first: str, last: str) -> str:
    return f"{first.strip()} {last.strip()}".strip()


def _resolve_profile_image(profile_image: Optional[str]) -> str:
    if not profile_image or not profile_image.strip():
        return DEFAULT_PROFILE_IMAGE
    value = profile_image.strip()
    if len(value) > _MAX_IMAGE_CHARS:
        raise HTTPException(status_code=400, detail="Profile image is too large")
    if value.startswith("/"):
        return value
    if value.startswith("data:image/"):
        return value
    raise HTTPException(status_code=400, detail="Profile image must be a data URL or default path")


def _user_to_profile(user: dict[str, Any]) -> UserProfileResponse:
    first = user.get("first_name") or ""
    last = user.get("last_name") or ""
    name = user.get("name") or _full_name(first, last)
    if not first and name:
        parts = name.split(" ", 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ""

    return UserProfileResponse(
        user_id=str(user["_id"]),
        email=user["email"],
        role=user["role"],
        first_name=first,
        last_name=last,
        name=name,
        phone=user.get("phone", ""),
        location=user.get("location", ""),
        profile_image=user.get("profile_image", DEFAULT_PROFILE_IMAGE),
        degree=user.get("degree"),
        degree_year=user.get("degree_year"),
        institution=user.get("institution"),
        specialized_training=user.get("specialized_training"),
        is_verified=user.get("is_verified", False),
        created_at=user.get("created_at"),
    )


def _to_token_response(user: dict[str, Any]) -> TokenResponse:
    profile = _user_to_profile(user)
    token = create_token(profile.user_id, profile.email, profile.role)
    return TokenResponse(
        access_token=token,
        role=profile.role,
        user_id=profile.user_id,
        name=profile.name,
        email=profile.email,
        first_name=profile.first_name,
        last_name=profile.last_name,
        profile_image=profile.profile_image,
    )


async def register_patient(req: PatientRegisterRequest) -> TokenResponse:
    return await _register_user(req, UserRole.PATIENT)


async def register_dentist(req: DentistRegisterRequest) -> TokenResponse:
    extra: dict[str, Any] = {
        "degree": req.degree.strip(),
        "degree_year": req.degree_year,
        "institution": req.institution.strip(),
        "specialized_training": req.specialized_training.strip() if req.specialized_training else None,
        "clinic_name": req.institution.strip(),
        "is_partner": True,
    }
    from orchestrator.dentist_recommendation.geocoding import geocode_address

    coords = await geocode_address(req.location.strip())
    if coords:
        lat, lng = coords
        extra["lat"] = lat
        extra["lng"] = lng
        extra["coordinates"] = {"type": "Point", "coordinates": [lng, lat]}

    return await _register_user(req, UserRole.DENTIST, extra=extra)


async def register_admin(req: AdminRegisterRequest) -> TokenResponse:
    return await _register_user(req, UserRole.ADMIN)


async def _register_user(
    req: PatientRegisterRequest,
    role: UserRole,
    extra: Optional[dict[str, Any]] = None,
) -> TokenResponse:
    users = get_portal_users_col()
    existing = await users.find_one({"email": req.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    doc: dict[str, Any] = {
        "email": req.email.lower(),
        "hashed_password": hash_password(req.password),
        "role": role.value,
        "first_name": req.first_name.strip(),
        "last_name": req.last_name.strip(),
        "name": _full_name(req.first_name, req.last_name),
        "phone": req.phone.strip(),
        "location": req.location.strip(),
        "profile_image": _resolve_profile_image(req.profile_image),
        "created_at": datetime.now(timezone.utc),
        "is_verified": False,
    }
    if extra:
        doc.update(extra)

    result = await users.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info("[PORTAL AUTH] Registered %s as %s", doc["email"], role.value)
    return _to_token_response(doc)


async def login_user(req: LoginRequest, expected_role: UserRole) -> TokenResponse:
    users = get_portal_users_col()
    user = await users.find_one({"email": req.email.lower()})
    if not user or not verify_password(req.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.get("role") != expected_role.value:
        raise HTTPException(
            status_code=403,
            detail=f"This account is not registered as a {expected_role.value}",
        )

    logger.info("[PORTAL AUTH] Login: %s (%s)", req.email, expected_role.value)
    return _to_token_response(user)


async def get_user_profile(user_id: str) -> UserProfileResponse:
    from bson import ObjectId
    from bson.errors import InvalidId

    users = get_portal_users_col()
    try:
        oid = ObjectId(user_id)
    except InvalidId as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc

    user = await users.find_one({"_id": oid})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_profile(user)
