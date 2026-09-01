"""Unified patient, dentist, and admin authentication routes."""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.config import settings
from orchestrator.db.session import get_db_session
from orchestrator.dentist_portal.auth import get_current_user
from orchestrator.dentist_portal.models import (
    DentistRegisterRequest,
    LoginRequest,
    PatientRegisterRequest,
    TokenResponse,
    UserProfileResponse,
    UserRole,
)
from orchestrator.dentist_portal.user_service import (
    get_user_profile,
    login_user,
    register_dentist,
    register_patient,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/portal/auth", tags=["portal-auth"])


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path=settings.auth_cookie_path,
        domain=settings.auth_cookie_domain or None,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_refresh_cookie_name,
        path=settings.auth_cookie_path,
        domain=settings.auth_cookie_domain or None,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )


@router.post("/patient/register", response_model=TokenResponse)
async def register_patient_route(
    req: PatientRegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
):
    token_response, refresh = await register_patient(
        req, session, user_agent=request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, refresh)
    return token_response


@router.post("/patient/login", response_model=TokenResponse)
async def login_patient_route(
    req: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
):
    token_response, refresh = await login_user(
        req, UserRole.PATIENT, session, user_agent=request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, refresh)
    return token_response


@router.post("/dentist/register", response_model=TokenResponse)
async def register_dentist_route(
    req: DentistRegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
):
    token_response, refresh = await register_dentist(
        req, session, user_agent=request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, refresh)
    return token_response


@router.post("/dentist/login", response_model=TokenResponse)
async def login_dentist_route(
    req: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
):
    token_response, refresh = await login_user(
        req, UserRole.DENTIST, session, user_agent=request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, refresh)
    return token_response


@router.post("/admin/login", response_model=TokenResponse)
async def login_admin_route(
    req: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
):
    token_response, refresh = await login_user(
        req, UserRole.ADMIN, session, user_agent=request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, refresh)
    return token_response


@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(
        default=None, alias=settings.auth_refresh_cookie_name
    ),
    session: AsyncSession = Depends(get_db_session),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh cookie is missing")
    token_response, rotated = await rotate_refresh_token(
        refresh_token, session, user_agent=request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, rotated)
    return token_response


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(
        default=None, alias=settings.auth_refresh_cookie_name
    ),
    session: AsyncSession = Depends(get_db_session),
):
    if refresh_token:
        await revoke_refresh_token(refresh_token, session)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await get_user_profile(user["user_id"], session)
