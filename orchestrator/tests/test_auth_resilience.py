"""Unit tests for Auth and Session Resilience under transient database failures."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError, OperationalError

from orchestrator.config import settings
from orchestrator.db.models import AuthSession, User
from orchestrator.dentist_portal.auth import (
    create_access_token,
    get_current_user,
    hash_password,
)
from orchestrator.dentist_portal.models import LoginRequest, UserRole
from orchestrator.dentist_portal.user_service import (
    get_user_profile,
    login_user,
    rotate_refresh_token,
)


@pytest.fixture(autouse=True)
def configure_test_jwt(monkeypatch):
    monkeypatch.setattr(
        settings, "jwt_secret", "test-resilience-secret-with-sufficient-entropy-12345"
    )


# =========================================================================
# 1. TOKEN TTL VERIFICATION
# =========================================================================

def test_token_ttl_configuration():
    """Verify access and refresh token TTLs are standard and not accidentally ~5 seconds."""
    assert settings.access_token_expire_minutes >= 15, "Access token TTL must be at least 15m"
    assert settings.access_token_expire_minutes == 30, "Access token TTL should be 30m"
    assert settings.refresh_token_expire_days >= 1, "Refresh token TTL must be at least 1d"
    assert settings.refresh_token_expire_days == 7, "Refresh token TTL should be 7d"
    assert settings.auth_refresh_cookie_name == "daantshaant_refresh"
    assert settings.auth_cookie_path == "/"


# =========================================================================
# 2. LOGIN RESILIENCE & CLASSIFICATION
# =========================================================================

@pytest.mark.asyncio
async def test_login_correct_credentials_success():
    """Correct credentials return 200 with tokens and user details."""
    session = AsyncMock()
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "patient@example.com"
    user.password_hash = hash_password("ValidPassword123")
    user.role = UserRole.PATIENT.value
    user.status = "active"
    user.first_name = "Jane"
    user.last_name = "Doe"
    user.phone = "123456789"
    user.profile_image_url = "/default.png"
    user.created_at = datetime.now(timezone.utc)

    with patch("orchestrator.dentist_portal.user_service.UserRepository") as MockUserRepo, \
         patch("orchestrator.dentist_portal.user_service.AuthSessionRepository") as MockSessionRepo:
        user_repo = MockUserRepo.return_value
        user_repo.get_by_email = AsyncMock(return_value=user)
        user_repo.get_patient_profile = AsyncMock(return_value=None)
        session_repo = MockSessionRepo.return_value
        session_repo.add = AsyncMock()

        req = LoginRequest(email="patient@example.com", password="ValidPassword123")
        token_res, refresh = await login_user(req, UserRole.PATIENT, session)

        assert token_res.access_token
        assert token_res.role == "patient"
        assert token_res.email == "patient@example.com"
        assert refresh


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401():
    """Wrong password returns 401 Invalid email or password."""
    session = AsyncMock()
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "patient@example.com"
    user.password_hash = hash_password("ValidPassword123")
    user.role = UserRole.PATIENT.value
    user.status = "active"

    with patch("orchestrator.dentist_portal.user_service.UserRepository") as MockUserRepo:
        user_repo = MockUserRepo.return_value
        user_repo.get_by_email = AsyncMock(return_value=user)

        req = LoginRequest(email="patient@example.com", password="WrongPassword999")
        with pytest.raises(HTTPException) as exc_info:
            await login_user(req, UserRole.PATIENT, session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid email or password"


@pytest.mark.asyncio
async def test_login_db_timeout_returns_503_not_401(caplog):
    """Database timeout during user lookup retries once then raises controlled 503."""
    session = AsyncMock()

    with patch("orchestrator.dentist_portal.user_service.UserRepository") as MockUserRepo:
        user_repo = MockUserRepo.return_value
        # Simulate timeout on all attempts
        user_repo.get_by_email = AsyncMock(side_effect=TimeoutError("Connection handshake timeout"))

        req = LoginRequest(email="patient@example.com", password="Password123")
        with pytest.raises(HTTPException) as exc_info:
            await login_user(req, UserRole.PATIENT, session)

        assert exc_info.value.status_code == 503
        assert "temporarily unavailable" in exc_info.value.detail.lower()
        # Verify it did NOT return 401
        assert exc_info.value.status_code != 401
        assert "[AUTH] login_db_timeout" in caplog.text


@pytest.mark.asyncio
async def test_login_transient_db_error_succeeds_on_single_retry():
    """Transient connection error on attempt 1 succeeds if retry succeeds."""
    session = AsyncMock()
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "patient@example.com"
    user.password_hash = hash_password("ValidPassword123")
    user.role = UserRole.PATIENT.value
    user.status = "active"
    user.first_name = "Jane"
    user.last_name = "Doe"
    user.phone = "123456789"
    user.profile_image_url = "/default.png"
    user.created_at = datetime.now(timezone.utc)

    with patch("orchestrator.dentist_portal.user_service.UserRepository") as MockUserRepo, \
         patch("orchestrator.dentist_portal.user_service.AuthSessionRepository") as MockSessionRepo:
        user_repo = MockUserRepo.return_value
        # First call raises OperationalError, second returns user
        user_repo.get_by_email = AsyncMock(
            side_effect=[OperationalError("SSL EOF", {}, None), user]
        )
        user_repo.get_patient_profile = AsyncMock(return_value=None)
        session_repo = MockSessionRepo.return_value
        session_repo.add = AsyncMock()

        req = LoginRequest(email="patient@example.com", password="ValidPassword123")
        token_res, refresh = await login_user(req, UserRole.PATIENT, session)

        assert token_res.access_token
        assert token_res.email == "patient@example.com"
        assert user_repo.get_by_email.call_count == 2


# =========================================================================
# 3. REFRESH TOKEN RESILIENCE
# =========================================================================

@pytest.mark.asyncio
async def test_refresh_valid_token_success():
    """Valid refresh token rotates and returns new access and refresh token."""
    session = AsyncMock()
    user_id = uuid4()
    user = MagicMock(spec=User)
    user.id = user_id
    user.email = "patient@example.com"
    user.role = UserRole.PATIENT.value
    user.status = "active"
    user.first_name = "Jane"
    user.last_name = "Doe"
    user.phone = ""
    user.profile_image_url = "/default.png"
    user.created_at = datetime.now(timezone.utc)

    old_session = MagicMock(spec=AuthSession)
    old_session.user_id = user_id

    with patch("orchestrator.dentist_portal.user_service.AuthSessionRepository") as MockSessionRepo, \
         patch("orchestrator.dentist_portal.user_service.UserRepository") as MockUserRepo:
        session_repo = MockSessionRepo.return_value
        session_repo.get_active_by_hash = AsyncMock(return_value=old_session)
        session_repo.revoke = AsyncMock()
        session_repo.add = AsyncMock()

        user_repo = MockUserRepo.return_value
        user_repo.get = AsyncMock(return_value=user)
        user_repo.get_patient_profile = AsyncMock(return_value=None)

        token_res, rotated = await rotate_refresh_token("valid_token_123", session)
        assert token_res.access_token
        assert rotated
        assert session_repo.revoke.call_count >= 1


@pytest.mark.asyncio
async def test_refresh_invalid_token_returns_401():
    """Genuinely invalid or expired refresh token returns 401."""
    session = AsyncMock()

    with patch("orchestrator.dentist_portal.user_service.AuthSessionRepository") as MockSessionRepo:
        session_repo = MockSessionRepo.return_value
        session_repo.get_active_by_hash = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await rotate_refresh_token("nonexistent_token", session)

        assert exc_info.value.status_code == 401
        assert "Invalid refresh session" in exc_info.value.detail


@pytest.mark.asyncio
async def test_refresh_db_timeout_returns_503_does_not_revoke(caplog):
    """Database timeout during refresh returns 503 and does NOT revoke the session."""
    session = AsyncMock()

    with patch("orchestrator.dentist_portal.user_service.AuthSessionRepository") as MockSessionRepo:
        session_repo = MockSessionRepo.return_value
        session_repo.get_active_by_hash = AsyncMock(side_effect=TimeoutError("Pool timeout"))
        session_repo.revoke = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await rotate_refresh_token("valid_token_123", session)

        assert exc_info.value.status_code == 503
        assert session_repo.revoke.call_count == 0
        assert "[AUTH] refresh_db_unavailable" in caplog.text


# =========================================================================
# 4. /AUTH/ME RESILIENCE
# =========================================================================

@pytest.mark.asyncio
async def test_get_current_user_db_timeout_returns_503(caplog):
    """get_current_user returns 503 on database timeout, not 401."""
    session = AsyncMock()
    user_id = uuid4()
    token = create_access_token(user_id, "patient@example.com", "patient")
    creds = MagicMock()
    creds.credentials = token

    with patch("orchestrator.dentist_portal.auth.UserRepository") as MockUserRepo:
        user_repo = MockUserRepo.return_value
        user_repo.get = AsyncMock(side_effect=TimeoutError("DB connect timeout"))

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(creds, session)

        assert exc_info.value.status_code == 503
        assert "[AUTH] auth_me_db_unavailable" in caplog.text


@pytest.mark.asyncio
async def test_get_user_profile_db_timeout_returns_503(caplog):
    """get_user_profile returns 503 on database timeout."""
    session = AsyncMock()
    user_id = uuid4()

    with patch("orchestrator.dentist_portal.user_service.UserRepository") as MockUserRepo:
        user_repo = MockUserRepo.return_value
        user_repo.get = AsyncMock(side_effect=TimeoutError("DB lookup timeout"))

        with pytest.raises(HTTPException) as exc_info:
            await get_user_profile(user_id, session)

        assert exc_info.value.status_code == 503
        assert "[AUTH] auth_me_db_unavailable" in caplog.text
