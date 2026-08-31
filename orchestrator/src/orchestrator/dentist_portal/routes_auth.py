"""Auth routes for Patient, Dentist, and Admin portals."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from orchestrator.dentist_portal.auth import create_token, get_current_user, hash_password, verify_password
from orchestrator.dentist_portal.db import get_portal_users_col
from orchestrator.dentist_portal.models import (
    AdminRegisterRequest,
    DentistRegisterRequest,
    LegacyRegisterRequest,
    LoginRequest,
    PatientRegisterRequest,
    TokenResponse,
    UserProfileResponse,
    UserRole,
)
from orchestrator.dentist_portal.user_service import (
    get_user_profile,
    login_user,
    register_admin,
    register_dentist,
    register_patient,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portal/auth", tags=["portal-auth"])


@router.post("/patient/register", response_model=TokenResponse)
async def register_patient_route(req: PatientRegisterRequest):
    return await register_patient(req)


@router.post("/patient/login", response_model=TokenResponse)
async def login_patient_route(req: LoginRequest):
    return await login_user(req, UserRole.PATIENT)


@router.post("/dentist/register", response_model=TokenResponse)
async def register_dentist_route(req: DentistRegisterRequest):
    return await register_dentist(req)


@router.post("/dentist/login", response_model=TokenResponse)
async def login_dentist_route(req: LoginRequest):
    return await login_user(req, UserRole.DENTIST)


@router.post("/admin/register", response_model=TokenResponse)
async def register_admin_route(req: AdminRegisterRequest):
    return await register_admin(req)


@router.post("/admin/login", response_model=TokenResponse)
async def login_admin_route(req: LoginRequest):
    return await login_user(req, UserRole.ADMIN)


@router.get("/me", response_model=UserProfileResponse)
async def get_me(user: dict = Depends(get_current_user)):
    return await get_user_profile(user["sub"])


# --- Legacy routes (existing /portal page) ---

@router.post("/register", response_model=TokenResponse)
async def register_legacy(req: LegacyRegisterRequest):
    users = get_portal_users_col()
    existing = await users.find_one({"email": req.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    parts = req.name.strip().split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""

    hashed = hash_password(req.password)
    doc = {
        "email": req.email.lower(),
        "hashed_password": hashed,
        "first_name": first_name,
        "last_name": last_name,
        "name": req.name.strip(),
        "role": req.role.value,
        "phone": "",
        "location": "",
        "profile_image": "/default-avatar.svg",
        "clinic_name": req.clinic_name,
        "license_number": req.license_number,
        "created_at": datetime.now(timezone.utc),
        "is_verified": False,
    }
    result = await users.insert_one(doc)
    user_id = str(result.inserted_id)
    token = create_token(user_id, req.email.lower(), req.role.value)

    logger.info("[PORTAL AUTH] Legacy register %s as %s", req.email, req.role)
    return TokenResponse(
        access_token=token,
        role=req.role,
        user_id=user_id,
        name=req.name.strip(),
        email=req.email.lower(),
        first_name=first_name,
        last_name=last_name,
        profile_image="/default-avatar.svg",
    )


@router.post("/login", response_model=TokenResponse)
async def login_legacy(req: LoginRequest):
    users = get_portal_users_col()
    user = await users.find_one({"email": req.email.lower()})
    if not user or not verify_password(req.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    profile = await get_user_profile(str(user["_id"]))
    token = create_token(profile.user_id, profile.email, profile.role.value)
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
