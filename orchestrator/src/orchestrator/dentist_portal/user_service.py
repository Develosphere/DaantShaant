"""Unified user registration, login, profile, and refresh-session services."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.config import settings
from orchestrator.db.models import AuthSession, Dentist, PatientProfile, User
from orchestrator.dentist_portal.auth import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from orchestrator.dentist_portal.auth_utils import execute_with_single_retry
from orchestrator.dentist_portal.constants import DEFAULT_PROFILE_IMAGE
from orchestrator.dentist_portal.models import (
    DentistRegisterRequest,
    LoginRequest,
    PatientRegisterRequest,
    TokenResponse,
    UserProfileResponse,
    UserRole,
)
from orchestrator.repositories import AuthSessionRepository, DentistRepository, UserRepository

_MAX_IMAGE_CHARS = 500_000


def _full_name(first: str, last: str) -> str:
    return f"{first.strip()} {last.strip()}".strip()


def _resolve_profile_image(profile_image: Optional[str]) -> str:
    if not profile_image or not profile_image.strip():
        return DEFAULT_PROFILE_IMAGE
    value = profile_image.strip()
    if len(value) > _MAX_IMAGE_CHARS:
        raise HTTPException(status_code=400, detail="Profile image is too large")
    if value.startswith("/") or value.startswith("data:image/"):
        return value
    raise HTTPException(
        status_code=400, detail="Profile image must be a data URL or default path"
    )


async def _profile(session: AsyncSession, user: User) -> UserProfileResponse:
    location = ""
    degree = degree_year = institution = specialized_training = None
    is_verified = False
    if user.role == UserRole.PATIENT.value:
        patient = await UserRepository(session).get_patient_profile(user.id)
        location = patient.location_text if patient and patient.location_text else ""
    elif user.role == UserRole.DENTIST.value:
        dentist = await DentistRepository(session).get_by_owner(user.id)
        if dentist:
            location = dentist.address or ""
            degree = dentist.degree
            degree_year = dentist.degree_year
            institution = dentist.institution
            specialized_training = dentist.specialized_training
            is_verified = dentist.is_verified
    return UserProfileResponse(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        name=_full_name(user.first_name or "", user.last_name or ""),
        phone=user.phone or "",
        location=location,
        profile_image=user.profile_image_url or DEFAULT_PROFILE_IMAGE,
        degree=degree,
        degree_year=degree_year,
        institution=institution,
        specialized_training=specialized_training,
        is_verified=is_verified,
        created_at=user.created_at,
    )


async def _issue_tokens(
    session: AsyncSession,
    user: User,
    *,
    user_agent: str | None = None,
) -> tuple[TokenResponse, str]:
    refresh_token = generate_refresh_token()
    auth_repo = AuthSessionRepository(session)
    await execute_with_single_retry(
        lambda: auth_repo.add(
            AuthSession(
                user_id=user.id,
                refresh_token_hash=hash_refresh_token(refresh_token),
                expires_at=datetime.now(timezone.utc)
                + timedelta(days=settings.refresh_token_expire_days),
                user_agent=user_agent,
            )
        ),
        op_name="issue_tokens_add_session",
    )
    profile = await execute_with_single_retry(
        lambda: _profile(session, user),
        op_name="issue_tokens_profile",
    )
    response = TokenResponse(
        access_token=create_access_token(user.id, user.email, user.role),
        role=profile.role,
        user_id=profile.user_id,
        name=profile.name,
        email=profile.email,
        first_name=profile.first_name,
        last_name=profile.last_name,
        profile_image=profile.profile_image,
    )
    return response, refresh_token


async def register_patient(
    req: PatientRegisterRequest,
    session: AsyncSession,
    *,
    user_agent: str | None = None,
) -> tuple[TokenResponse, str]:
    user_repo = UserRepository(session)
    if await user_repo.get_by_email(req.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    user = await user_repo.add(
        User(
            email=req.email.lower(),
            password_hash=hash_password(req.password),
            role=UserRole.PATIENT.value,
            first_name=req.first_name.strip(),
            last_name=req.last_name.strip(),
            phone=req.phone.strip(),
            profile_image_url=_resolve_profile_image(req.profile_image),
        )
    )
    await user_repo.add_patient_profile(
        PatientProfile(user_id=user.id, location_text=req.location.strip())
    )
    return await _issue_tokens(session, user, user_agent=user_agent)


async def register_dentist(
    req: DentistRegisterRequest,
    session: AsyncSession,
    *,
    user_agent: str | None = None,
) -> tuple[TokenResponse, str]:
    user_repo = UserRepository(session)
    if await user_repo.get_by_email(req.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    user = await user_repo.add(
        User(
            email=req.email.lower(),
            password_hash=hash_password(req.password),
            role=UserRole.DENTIST.value,
            first_name=req.first_name.strip(),
            last_name=req.last_name.strip(),
            phone=req.phone.strip(),
            profile_image_url=_resolve_profile_image(req.profile_image),
        )
    )
    dentist = Dentist(
        owner_user_id=user.id,
        source="platform",
        name=_full_name(req.first_name, req.last_name),
        clinic_name=req.institution.strip(),
        email=user.email,
        phone=user.phone,
        address=req.location.strip(),
        degree=req.degree.strip(),
        degree_year=req.degree_year,
        institution=req.institution.strip(),
        specialized_training=(
            req.specialized_training.strip() if req.specialized_training else None
        ),
        is_verified=False,
        is_partner=False,
    )
    await DentistRepository(session).add(dentist)
    return await _issue_tokens(session, user, user_agent=user_agent)


async def login_user(
    req: LoginRequest,
    expected_role: UserRole,
    session: AsyncSession,
    *,
    user_agent: str | None = None,
) -> tuple[TokenResponse, str]:
    domain = req.email.split("@")[-1] if "@" in req.email else "unknown"
    logger.info("[AUTH] login_attempt domain=%s role=%s", domain, expected_role.value)

    user_repo = UserRepository(session)
    try:
        user = await execute_with_single_retry(
            lambda: user_repo.get_by_email(req.email),
            op_name="login_user_lookup",
        )
    except HTTPException as exc:
        if exc.status_code == 503:
            logger.error("[AUTH] login_db_timeout")
        raise

    if not user or not verify_password(req.password, user.password_hash):
        logger.warning("[AUTH] login_invalid_credentials")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.role != expected_role.value:
        logger.warning(
            "[AUTH] login_invalid_credentials role mismatch for user %s (expected %s, got %s)",
            user.id,
            expected_role.value,
            user.role,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.status != "active":
        logger.warning("[AUTH] login_invalid_credentials inactive/disabled user %s", user.id)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    try:
        token_response, refresh = await _issue_tokens(session, user, user_agent=user_agent)
    except HTTPException as exc:
        if exc.status_code == 503:
            logger.error("[AUTH] login_db_timeout")
        raise

    logger.info("[AUTH] login_success user_id=%s role=%s", user.id, user.role)
    return token_response, refresh


async def rotate_refresh_token(
    raw_token: str,
    session: AsyncSession,
    *,
    user_agent: str | None = None,
) -> tuple[TokenResponse, str]:
    now = datetime.now(timezone.utc)
    auth_repo = AuthSessionRepository(session)
    user_repo = UserRepository(session)

    try:
        old = await execute_with_single_retry(
            lambda: auth_repo.get_active_by_hash(
                hash_refresh_token(raw_token), now, lock=True
            ),
            op_name="rotate_refresh_lookup",
        )
    except HTTPException as exc:
        if exc.status_code == 503:
            logger.error("[AUTH] refresh_db_unavailable")
        raise

    if not old:
        logger.warning("[AUTH] refresh_invalid")
        raise HTTPException(status_code=401, detail="Invalid refresh session")

    try:
        user = await execute_with_single_retry(
            lambda: user_repo.get(old.user_id),
            op_name="rotate_refresh_user_lookup",
        )
    except HTTPException as exc:
        if exc.status_code == 503:
            logger.error("[AUTH] refresh_db_unavailable")
        raise

    if not user or user.status != "active":
        try:
            await execute_with_single_retry(
                lambda: auth_repo.revoke(old, now),
                op_name="rotate_refresh_revoke_disabled",
            )
        except Exception:
            pass
        logger.warning("[AUTH] refresh_invalid disabled_account user_id=%s", old.user_id)
        raise HTTPException(status_code=403, detail="Account is disabled")

    try:
        await execute_with_single_retry(
            lambda: auth_repo.revoke(old, now),
            op_name="rotate_refresh_revoke_old",
        )
        token_response, rotated = await _issue_tokens(
            session, user, user_agent=user_agent
        )
    except HTTPException as exc:
        if exc.status_code == 503:
            logger.error("[AUTH] refresh_db_unavailable")
        raise

    logger.info("[AUTH] refresh_success user_id=%s", user.id)
    return token_response, rotated


async def revoke_refresh_token(raw_token: str, session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    auth_repo = AuthSessionRepository(session)
    try:
        auth_session = await execute_with_single_retry(
            lambda: auth_repo.get_active_by_hash(
                hash_refresh_token(raw_token), now, lock=True
            ),
            op_name="revoke_refresh_lookup",
        )
        if auth_session:
            await execute_with_single_retry(
                lambda: auth_repo.revoke(auth_session, now),
                op_name="revoke_refresh_revoke",
            )
    except Exception as exc:
        logger.warning("[AUTH] revoke_token_failed_during_logout: %s", exc)


async def get_user_profile(user_id: UUID, session: AsyncSession) -> UserProfileResponse:
    try:
        user = await execute_with_single_retry(
            lambda: UserRepository(session).get(user_id),
            op_name="get_user_profile_user",
        )
    except HTTPException as exc:
        if exc.status_code == 503:
            logger.error("[AUTH] auth_me_db_unavailable")
        raise

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        return await execute_with_single_retry(
            lambda: _profile(session, user),
            op_name="get_user_profile_details",
        )
    except HTTPException as exc:
        if exc.status_code == 503:
            logger.error("[AUTH] auth_me_db_unavailable")
        raise
