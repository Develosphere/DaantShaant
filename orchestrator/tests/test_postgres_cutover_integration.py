"""Safe transactional integration coverage for auth, CRUD, and ownership."""

import asyncio
import os
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.config import settings
from orchestrator.db.models import AppointmentRequest, Dentist, Product, Scan, User
from orchestrator.db.session import engine
from orchestrator.dentist_portal.auth import hash_password
from orchestrator.dentist_portal.models import (
    DentistRegisterRequest,
    LoginRequest,
    PatientRegisterRequest,
    UserRole,
)
from orchestrator.dentist_portal.user_service import (
    login_user,
    register_dentist,
    register_patient,
    revoke_refresh_token,
    rotate_refresh_token,
)
from orchestrator.repositories import (
    AppointmentRepository,
    ConversationRepository,
    DentistRepository,
    ProductRepository,
    ScanRepository,
    UserRepository,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Set RUN_POSTGRES_INTEGRATION=1 for the configured development database",
)


def test_auth_crud_and_ownership_cutover():
    asyncio.run(_exercise_cutover())


async def _exercise_cutover() -> None:
    previous_secret = settings.jwt_secret
    settings.jwt_secret = previous_secret or "integration-test-secret-with-sufficient-entropy"
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    suffix = uuid4().hex
    try:
        patient_response, patient_refresh = await register_patient(
            PatientRegisterRequest(
                first_name="Patient",
                last_name="One",
                email=f"patient-{suffix}@example.com",
                password="Patient123",
                phone="+92 300 1234567",
                location="Karachi, Pakistan",
            ),
            session,
        )
        other_response, _ = await register_patient(
            PatientRegisterRequest(
                first_name="Patient",
                last_name="Two",
                email=f"other-{suffix}@example.com",
                password="Patient123",
                phone="+92 300 7654321",
                location="Lahore, Pakistan",
            ),
            session,
        )
        dentist_response, _ = await register_dentist(
            DentistRegisterRequest(
                first_name="Dentist",
                last_name="One",
                email=f"dentist-{suffix}@example.com",
                password="Dentist123",
                phone="+92 300 2222222",
                location="Karachi, Pakistan",
                degree="BDS",
                degree_year=2020,
                institution="Dental University",
            ),
            session,
        )
        patient_id = patient_response.user_id
        other_id = other_response.user_id
        dentist_user_id = dentist_response.user_id

        login, _ = await login_user(
            LoginRequest(email=f"patient-{suffix}@example.com", password="Patient123"),
            UserRole.PATIENT,
            session,
        )
        assert login.user_id == patient_id
        with pytest.raises(HTTPException):
            await login_user(
                LoginRequest(email=f"patient-{suffix}@example.com", password="wrong"),
                UserRole.PATIENT,
                session,
            )

        rotated_response, rotated_refresh = await rotate_refresh_token(
            patient_refresh, session
        )
        assert rotated_response.user_id == patient_id
        with pytest.raises(HTTPException):
            await rotate_refresh_token(patient_refresh, session)
        await revoke_refresh_token(rotated_refresh, session)
        with pytest.raises(HTTPException):
            await rotate_refresh_token(rotated_refresh, session)

        patient_uuid = __import__("uuid").UUID(patient_id)
        other_uuid = __import__("uuid").UUID(other_id)
        dentist_user_uuid = __import__("uuid").UUID(dentist_user_id)
        conversation = await ConversationRepository(session).create(patient_uuid, "Owned")
        assert await ConversationRepository(session).get_owned(conversation.id, patient_uuid)
        assert not await ConversationRepository(session).get_owned(conversation.id, other_uuid)

        scan = Scan(patient_user_id=patient_uuid, input_mode="upload", status="clinical_complete")
        session.add(scan)
        await session.flush()
        assert await ScanRepository(session).get_owned(scan.id, patient_uuid)
        assert not await ScanRepository(session).get_owned(scan.id, other_uuid)

        dentist = await DentistRepository(session).get_by_owner(dentist_user_uuid)
        product = await ProductRepository(session).add(
            Product(
                dentist_id=dentist.id,
                name="Test Product",
                price=Decimal("10.00"),
                status="active",
            )
        )
        assert await ProductRepository(session).get_owned(product.id, dentist_user_uuid)
        assert not await ProductRepository(session).get_owned(product.id, patient_uuid)

        appointment = await AppointmentRepository(session).add(
            AppointmentRequest(
                patient_user_id=patient_uuid,
                dentist_id=dentist.id,
                scan_id=scan.id,
                issue="sensitivity",
            )
        )
        assert await AppointmentRepository(session).get_for_principal(
            appointment.id, user_id=patient_uuid, role="patient"
        )
        assert not await AppointmentRepository(session).get_for_principal(
            appointment.id, user_id=other_uuid, role="patient"
        )
        assert await AppointmentRepository(session).get_for_principal(
            appointment.id, user_id=dentist_user_uuid, role="dentist"
        )

        patient = await UserRepository(session).get(patient_uuid)
        patient.status = "disabled"
        await session.flush()
        with pytest.raises(HTTPException):
            await login_user(
                LoginRequest(email=patient.email, password="Patient123"),
                UserRole.PATIENT,
                session,
            )
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        settings.jwt_secret = previous_secret
        await engine.dispose()
