"""Dentist recommendation and appointment routes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import AppointmentRequest
from orchestrator.db.session import get_db_session
from orchestrator.dentist_portal.auth import get_current_dentist, get_current_patient, get_current_user
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

logger = logging.getLogger(__name__)

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
    resolved_scan_id: str | None = None
    if req.scan_id:
        try:
            parsed_scan_id = UUID(req.scan_id)
            owned_scan = await ScanRepository(session).get_owned(
                parsed_scan_id,
                user["user_id"],
            )
            if owned_scan:
                resolved_scan_id = req.scan_id
            else:
                logger.warning(
                    "[DENTIST_RECOMMEND] Scan ID '%s' not found or unowned for user %s. Continuing without scan context.",
                    req.scan_id,
                    user["user_id"],
                )
        except ValueError:
            logger.warning(
                "[DENTIST_RECOMMEND] Malformed scan ID '%s' provided by user %s. Continuing without scan context.",
                req.scan_id,
                user["user_id"],
            )
    result = await run_dentist_recommendation(
        patient_id=str(user["user_id"]),
        issue=req.issue,
        lat=lat,
        lng=lng,
        severity=req.severity or "moderate",
        scan_id=resolved_scan_id,
        session_id=req.session_id,
        radius_km=req.radius_km or 25.0,
    )
    return DentistRecommendResponse(
        session_id=result["session_id"],
        issue=result["issue"],
        patient_lat=result["patient_lat"],
        patient_lng=result["patient_lng"],
        dentists=[DentistPin(**item) for item in result["dentists"]],
        search_radius_km=result.get("search_radius_km"),
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
    user_repo = UserRepository(session)
    results = []
    for item in appointments:
        entry = {
            "appointment_id": str(item.id),
            "patient_user_id": str(item.patient_user_id),
            "dentist_id": str(item.dentist_id),
            "scan_id": str(item.scan_id) if item.scan_id else None,
            "issue": item.issue,
            "message": item.message,
            "preferred_time": item.preferred_time,
            "status": item.status,
            "created_at": item.created_at.isoformat(),
        }
        if user["role"] in {"dentist", "admin"}:
            patient_user = await user_repo.get(item.patient_user_id)
            if patient_user:
                full_name = f"{patient_user.first_name or ''} {patient_user.last_name or ''}".strip()
                entry["patient_name"] = full_name or "Patient"
                entry["patient_email"] = patient_user.email or ""
                entry["patient_phone"] = patient_user.phone or ""
        results.append(entry)
    return results


@router.post("/appointments/{appointment_id}/status", response_model=dict)
async def update_appointment_status(
    appointment_id: UUID,
    payload: dict,
    dentist: dict = Depends(get_current_dentist),
    session: AsyncSession = Depends(get_db_session),
):
    appointment = await AppointmentRepository(session).get_for_principal(
        appointment_id, user_id=dentist["user_id"], role="dentist"
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found or not yours")
    new_status = str(payload.get("status", "")).lower().strip()
    valid_statuses = {"pending", "confirmed", "accepted", "completed", "cancelled", "rejected"}
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=400, detail=f"Invalid status. Must be one of {valid_statuses}"
        )
    if new_status == "accepted":
        new_status = "confirmed"
    elif new_status == "rejected":
        new_status = "cancelled"
    appointment.status = new_status
    appointment.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return {"updated": True, "appointment_id": str(appointment.id), "status": new_status}

