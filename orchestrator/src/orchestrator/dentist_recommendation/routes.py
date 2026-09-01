"""Dentist recommendation and appointment routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import AppointmentRequest
from orchestrator.db.session import get_db_session
from orchestrator.dentist_portal.auth import get_current_patient, get_current_user
from orchestrator.dentist_portal.models import (
    BookConsultationRequest,
    BookConsultationResponse,
    DentistRecommendRequest,
    DentistRecommendResponse,
    DentistPin,
)
from orchestrator.dentist_recommendation.dentist_agent import run_dentist_recommendation
from orchestrator.dentist_recommendation.geocoding import geocode_address
from orchestrator.repositories import (
    AppointmentRepository,
    DentistRepository,
    ScanRepository,
    UserRepository,
)

router = APIRouter(prefix="/portal/recommend/dentists", tags=["dentist-recommendation"])


@router.post("/", response_model=DentistRecommendResponse)
async def recommend_dentists(
    req: DentistRecommendRequest,
    user: dict = Depends(get_current_patient),
    session: AsyncSession = Depends(get_db_session),
):
    lat, lng = req.lat, req.lng
    if lat is None or lng is None:
        profile = await UserRepository(session).get_patient_profile(user["user_id"])
        if profile and profile.location_text:
            coords = await geocode_address(profile.location_text)
            if coords:
                lat, lng = coords
    if lat is None or lng is None:
        raise HTTPException(
            status_code=400,
            detail="Location required - enable browser location or set profile location",
        )
    if req.scan_id:
        try:
            scan_id = UUID(req.scan_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid scan id") from exc
        if not await ScanRepository(session).get_owned(scan_id, user["user_id"]):
            raise HTTPException(status_code=404, detail="Scan not found")
    result = await run_dentist_recommendation(
        patient_id=str(user["user_id"]),
        issue=req.issue,
        lat=lat,
        lng=lng,
        severity=req.severity or "moderate",
        scan_id=req.scan_id,
        session_id=req.session_id,
        radius_km=req.radius_km or 25.0,
    )
    return DentistRecommendResponse(
        session_id=result["session_id"],
        issue=result["issue"],
        patient_lat=result["patient_lat"],
        patient_lng=result["patient_lng"],
        dentists=[DentistPin(**item) for item in result["dentists"]],
    )


@router.post("/appointments", response_model=BookConsultationResponse)
async def book_consultation(
    req: BookConsultationRequest,
    user: dict = Depends(get_current_patient),
    session: AsyncSession = Depends(get_db_session),
):
    try:
        dentist_id = UUID(req.dentist_id)
        scan_id = UUID(req.scan_id) if req.scan_id else None
        recommendation_session_id = UUID(req.session_id) if req.session_id else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid UUID") from exc
    if not await DentistRepository(session).get(dentist_id):
        raise HTTPException(status_code=404, detail="Dentist not found")
    if scan_id and not await ScanRepository(session).get_owned(scan_id, user["user_id"]):
        raise HTTPException(status_code=404, detail="Scan not found")
    appointment = await AppointmentRepository(session).add(
        AppointmentRequest(
            patient_user_id=user["user_id"],
            dentist_id=dentist_id,
            scan_id=scan_id,
            recommendation_session_id=recommendation_session_id,
            issue=req.issue,
            message=req.message,
            status="pending",
        )
    )
    return BookConsultationResponse(
        appointment_id=str(appointment.id),
        status=appointment.status,
        message="Consultation request sent. The dentist will contact you shortly.",
    )


@router.get("/appointments", response_model=list[dict])
async def list_appointments(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    appointments = await AppointmentRepository(session).list_for_principal(
        user_id=user["user_id"], role=user["role"]
    )
    return [
        {
            "appointment_id": str(item.id),
            "patient_user_id": str(item.patient_user_id),
            "dentist_id": str(item.dentist_id),
            "scan_id": str(item.scan_id) if item.scan_id else None,
            "issue": item.issue,
            "status": item.status,
            "created_at": item.created_at.isoformat(),
        }
        for item in appointments
    ]
