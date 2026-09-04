"""Focused unit tests for Phase 10.5: Portal Security, Session, Orders, and Appointments."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from orchestrator.config import settings
from orchestrator.db.models import AppointmentRequest, Dentist, Order, Product, User
from orchestrator.dentist_portal.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
)
from orchestrator.dentist_portal.models import LoginRequest, UserRole
from orchestrator.dentist_portal.user_service import login_user
from orchestrator.dentist_portal.routes_products import (
    list_dentist_orders,
    list_patient_orders,
)
from orchestrator.dentist_recommendation.routes import (
    list_appointments,
    update_appointment_status,
)


@pytest.fixture(autouse=True)
def ensure_jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-with-sufficient-entropy-for-hashing-12345")


# =========================================================================
# 1. AUTH SECURITY & ROLE DISCLOSURE
# =========================================================================

@pytest.mark.asyncio
async def test_login_unknown_email_generic_401():
    session = AsyncMock()
    with patch("orchestrator.dentist_portal.user_service.UserRepository") as MockUserRepo:
        repo = MockUserRepo.return_value
        repo.get_by_email = AsyncMock(return_value=None)

        req = LoginRequest(email="nonexistent@example.com", password="Password123")
        with pytest.raises(HTTPException) as exc_info:
            await login_user(req, UserRole.PATIENT, session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid email or password"
        assert "patient" not in exc_info.value.detail.lower()
        assert "dentist" not in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_login_wrong_password_generic_401():
    session = AsyncMock()
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "patient@example.com"
    user.password_hash = hash_password("CorrectPass123")
    user.role = "patient"
    user.status = "active"

    with patch("orchestrator.dentist_portal.user_service.UserRepository") as MockUserRepo:
        repo = MockUserRepo.return_value
        repo.get_by_email = AsyncMock(return_value=user)

        req = LoginRequest(email="patient@example.com", password="WrongPassword")
        with pytest.raises(HTTPException) as exc_info:
            await login_user(req, UserRole.PATIENT, session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid email or password"


@pytest.mark.asyncio
async def test_login_dentist_email_on_patient_login_generic_401():
    """Security requirement: Dentist trying patient portal must get same generic 401."""
    session = AsyncMock()
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "dentist@example.com"
    user.password_hash = hash_password("DentistPass123")
    user.role = "dentist"
    user.status = "active"

    with patch("orchestrator.dentist_portal.user_service.UserRepository") as MockUserRepo:
        repo = MockUserRepo.return_value
        repo.get_by_email = AsyncMock(return_value=user)

        req = LoginRequest(email="dentist@example.com", password="DentistPass123")
        with pytest.raises(HTTPException) as exc_info:
            await login_user(req, UserRole.PATIENT, session)

        # Must NOT be 403 and must NOT say "registered as a dentist"
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid email or password"
        assert "dentist" not in exc_info.value.detail.lower()
        assert "patient" not in exc_info.value.detail.lower()
        assert "registered" not in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_login_patient_email_on_dentist_login_generic_401():
    """Security requirement: Patient trying dentist portal must get same generic 401."""
    session = AsyncMock()
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "patient@example.com"
    user.password_hash = hash_password("PatientPass123")
    user.role = "patient"
    user.status = "active"

    with patch("orchestrator.dentist_portal.user_service.UserRepository") as MockUserRepo:
        repo = MockUserRepo.return_value
        repo.get_by_email = AsyncMock(return_value=user)

        req = LoginRequest(email="patient@example.com", password="PatientPass123")
        with pytest.raises(HTTPException) as exc_info:
            await login_user(req, UserRole.DENTIST, session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid email or password"
        assert "dentist" not in exc_info.value.detail.lower()
        assert "patient" not in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_login_inactive_user_generic_401():
    session = AsyncMock()
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "disabled@example.com"
    user.password_hash = hash_password("Pass12345")
    user.role = "patient"
    user.status = "disabled"

    with patch("orchestrator.dentist_portal.user_service.UserRepository") as MockUserRepo:
        repo = MockUserRepo.return_value
        repo.get_by_email = AsyncMock(return_value=user)

        req = LoginRequest(email="disabled@example.com", password="Pass12345")
        with pytest.raises(HTTPException) as exc_info:
            await login_user(req, UserRole.PATIENT, session)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid email or password"


@pytest.mark.asyncio
async def test_login_correct_credentials_success():
    session = AsyncMock()
    user_id = uuid4()
    user = MagicMock(spec=User)
    user.id = user_id
    user.email = "valid.patient@example.com"
    user.password_hash = hash_password("ValidPass123")
    user.role = "patient"
    user.status = "active"
    user.first_name = "Jane"
    user.last_name = "Doe"
    user.phone = "+923001234567"
    user.profile_image_url = ""
    user.created_at = datetime.now(timezone.utc)

    with patch("orchestrator.dentist_portal.user_service.UserRepository") as MockUserRepo, \
         patch("orchestrator.dentist_portal.user_service.AuthSessionRepository") as MockAuthRepo:
        MockUserRepo.return_value.get_by_email = AsyncMock(return_value=user)
        MockUserRepo.return_value.get_patient_profile = AsyncMock(return_value=None)
        MockAuthRepo.return_value.add = AsyncMock()

        req = LoginRequest(email="valid.patient@example.com", password="ValidPass123")
        token_resp, raw_refresh = await login_user(req, UserRole.PATIENT, session)

        assert token_resp.user_id == str(user_id)
        assert token_resp.role == "patient"
        assert len(raw_refresh) >= 64


# =========================================================================
# 2. SESSION CONFIGURATION
# =========================================================================

def test_session_expiry_configuration():
    # Access token ~30 minutes
    assert settings.access_token_expire_minutes == 30
    # Refresh session ~7 days
    assert settings.refresh_token_expire_days == 7


def test_access_token_creation_and_payload():
    user_id = uuid4()
    token = create_access_token(user_id, "user@example.com", "dentist")
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "dentist"
    assert payload["type"] == "access"
    assert "exp" in payload


# =========================================================================
# 3. DENTIST ORDERS SELLER ISOLATION
# =========================================================================

@pytest.mark.asyncio
async def test_dentist_orders_returns_seller_orders_only():
    dentist_user_id = uuid4()
    dentist_id = uuid4()
    order_id = uuid4()
    order = MagicMock(spec=Order)
    order.id = order_id
    order.dentist_id = dentist_id
    order.items = {
        "product_id": str(uuid4()),
        "product_name": "Ultra Sonic Brush",
        "quantity": 2,
        "patient_name": "John Doe",
        "patient_email": "john@example.com",
    }
    order.total = 89.99
    order.status = "pending"
    order.created_at = datetime.now(timezone.utc)

    session = AsyncMock()
    with patch("orchestrator.dentist_portal.routes_products.OrderRepository") as MockOrderRepo:
        MockOrderRepo.return_value.list_for_dentist = AsyncMock(return_value=[order])

        result = await list_dentist_orders(
            dentist={"user_id": dentist_user_id, "role": "dentist"},
            session=session,
        )

        MockOrderRepo.return_value.list_for_dentist.assert_called_once_with(dentist_user_id)
        assert len(result) == 1
        assert result[0]["order_id"] == str(order_id)
        assert result[0]["product_name"] == "Ultra Sonic Brush"
        assert result[0]["quantity"] == 2
        assert result[0]["price"] == 89.99
        assert result[0]["patient_name"] == "John Doe"
        assert result[0]["patient_email"] == "john@example.com"


@pytest.mark.asyncio
async def test_dentist_orders_empty_returns_safe_list():
    dentist_user_id = uuid4()
    session = AsyncMock()
    with patch("orchestrator.dentist_portal.routes_products.OrderRepository") as MockOrderRepo:
        MockOrderRepo.return_value.list_for_dentist = AsyncMock(return_value=[])

        result = await list_dentist_orders(
            dentist={"user_id": dentist_user_id, "role": "dentist"},
            session=session,
        )
        assert result == []


# =========================================================================
# 4. APPOINTMENTS OWNERSHIP & STATUS MUTATION
# =========================================================================

@pytest.mark.asyncio
async def test_dentist_appointments_list_scoped_with_patient_info():
    dentist_user_id = uuid4()
    patient_user_id = uuid4()
    appointment_id = uuid4()

    app_mock = MagicMock(spec=AppointmentRequest)
    app_mock.id = appointment_id
    app_mock.patient_user_id = patient_user_id
    app_mock.dentist_id = uuid4()
    app_mock.scan_id = None
    app_mock.issue = "Tooth pain"
    app_mock.message = "Severe pain in lower molar"
    app_mock.preferred_time = "Morning"
    app_mock.status = "pending"
    app_mock.created_at = datetime.now(timezone.utc)

    patient_mock = MagicMock(spec=User)
    patient_mock.first_name = "Alice"
    patient_mock.last_name = "Smith"
    patient_mock.email = "alice@example.com"
    patient_mock.phone = "+923001234567"

    session = AsyncMock()
    with patch("orchestrator.dentist_recommendation.routes.AppointmentRepository") as MockAppRepo, \
         patch("orchestrator.dentist_recommendation.routes.UserRepository") as MockUserRepo:
        MockAppRepo.return_value.list_for_principal = AsyncMock(return_value=[app_mock])
        MockUserRepo.return_value.get = AsyncMock(return_value=patient_mock)

        result = await list_appointments(
            user={"user_id": dentist_user_id, "role": "dentist"},
            session=session,
        )

        MockAppRepo.return_value.list_for_principal.assert_called_once_with(
            user_id=dentist_user_id, role="dentist"
        )
        assert len(result) == 1
        assert result[0]["appointment_id"] == str(appointment_id)
        assert result[0]["patient_name"] == "Alice Smith"
        assert result[0]["patient_email"] == "alice@example.com"
        assert result[0]["patient_phone"] == "+923001234567"
        assert result[0]["issue"] == "Tooth pain"


@pytest.mark.asyncio
async def test_update_appointment_status_success_and_cross_dentist_denial():
    dentist_user_id = uuid4()
    appointment_id = uuid4()

    app_mock = MagicMock(spec=AppointmentRequest)
    app_mock.id = appointment_id
    app_mock.status = "pending"
    app_mock.updated_at = None

    session = AsyncMock()
    with patch("orchestrator.dentist_recommendation.routes.AppointmentRepository") as MockAppRepo:
        # Owning dentist succeeds
        MockAppRepo.return_value.get_for_principal = AsyncMock(return_value=app_mock)

        res = await update_appointment_status(
            appointment_id=appointment_id,
            payload={"status": "confirmed"},
            dentist={"user_id": dentist_user_id, "role": "dentist"},
            session=session,
        )
        assert res["updated"] is True
        assert res["status"] == "confirmed"
        assert app_mock.status == "confirmed"

        # Cross-dentist denial: Dentist B querying Dentist A's appointment returns None -> 404
        MockAppRepo.return_value.get_for_principal = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc_info:
            await update_appointment_status(
                appointment_id=appointment_id,
                payload={"status": "confirmed"},
                dentist={"user_id": uuid4(), "role": "dentist"},
                session=session,
            )
        assert exc_info.value.status_code == 404
        assert "not yours" in exc_info.value.detail.lower()


# =========================================================================
# 5. PATIENT ORDERS ISOLATION & SIMPLE STATUS
# =========================================================================

@pytest.mark.asyncio
async def test_patient_orders_returns_patient_purchases_only():
    patient_user_id = uuid4()
    order_id = uuid4()
    dentist_id = uuid4()

    order = MagicMock(spec=Order)
    order.id = order_id
    order.dentist_id = dentist_id
    order.patient_user_id = patient_user_id
    order.items = {
        "product_id": str(uuid4()),
        "product_name": "Fluoride Toothpaste Pro",
        "dentist_name": "Al-Shifa Dental Clinic",
        "quantity": 2,
    }
    order.total = 24.50
    order.status = "placed"
    order.created_at = datetime.now(timezone.utc)

    dentist = MagicMock(spec=Dentist)
    dentist.clinic_name = "Al-Shifa Dental Clinic"
    dentist.doctor_name = "Dr. Tariq"

    session = AsyncMock()
    with patch("orchestrator.dentist_portal.routes_products.OrderRepository") as MockOrderRepo:
        MockOrderRepo.return_value.list_for_patient = AsyncMock(return_value=[(order, dentist)])

        result = await list_patient_orders(
            patient={"user_id": patient_user_id, "role": "patient"},
            session=session,
        )

        MockOrderRepo.return_value.list_for_patient.assert_called_once_with(patient_user_id)
        assert len(result) == 1
        assert result[0]["order_id"] == str(order_id)
        assert result[0]["product_name"] == "Fluoride Toothpaste Pro"
        assert result[0]["seller_name"] == "Al-Shifa Dental Clinic"
        assert result[0]["quantity"] == 2
        assert result[0]["price"] == 24.50
        assert result[0]["status"] == "placed"


@pytest.mark.asyncio
async def test_patient_orders_empty_returns_safe_list():
    patient_user_id = uuid4()
    session = AsyncMock()
    with patch("orchestrator.dentist_portal.routes_products.OrderRepository") as MockOrderRepo:
        MockOrderRepo.return_value.list_for_patient = AsyncMock(return_value=[])

        result = await list_patient_orders(
            patient={"user_id": patient_user_id, "role": "patient"},
            session=session,
        )

        MockOrderRepo.return_value.list_for_patient.assert_called_once_with(patient_user_id)
        assert result == []

