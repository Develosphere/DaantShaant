"""Dentist recommendation + appointment routes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException

from orchestrator.dentist_portal.auth import get_current_patient
from orchestrator.dentist_portal.db import get_portal_appointments_col, get_portal_users_col
from orchestrator.dentist_portal.models import (
    BookConsultationRequest,
    BookConsultationResponse,
    DentistRecommendRequest,
    DentistRecommendResponse,
    DentistPin,
)
from orchestrator.dentist_recommendation.dentist_agent import run_dentist_recommendation
from orchestrator.dentist_recommendation.geocoding import geocode_address

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal/recommend/dentists", tags=["dentist-recommendation"])


@router.post("/", response_model=DentistRecommendResponse)
async def recommend_dentists(
    req: DentistRecommendRequest,
    user: dict = Depends(get_current_patient),
):
    lat, lng = req.lat, req.lng

    if lat is None or lng is None:
        users = get_portal_users_col()
        try:
            patient = await users.find_one({"_id": ObjectId(user["sub"])})
        except InvalidId:
            patient = None
        if patient and patient.get("location"):
            coords = await geocode_address(patient["location"])
            if coords:
                lat, lng = coords

    if lat is None or lng is None:
        raise HTTPException(
            status_code=400,
            detail="Location required — enable browser location or set location on your profile",
        )

    patient_id = user["sub"]
    logger.info(
        "[DENTIST-REC] issue=%s patient=%s lat=%s lng=%s",
        req.issue, patient_id, lat, lng,
    )

    result = await run_dentist_recommendation(
        patient_id=patient_id,
        issue=req.issue,
        lat=lat,
        lng=lng,
        severity=req.severity or "moderate",
        scan_id=req.scan_id,
        session_id=req.session_id,
        radius_km=req.radius_km or 25.0,
    )

    dentists = [DentistPin(**d) for d in result["dentists"]]
    return DentistRecommendResponse(
        session_id=result["session_id"],
        issue=result["issue"],
        patient_lat=result["patient_lat"],
        patient_lng=result["patient_lng"],
        dentists=dentists,
    )


@router.post("/appointments", response_model=BookConsultationResponse)
async def book_consultation(
    req: BookConsultationRequest,
    user: dict = Depends(get_current_patient),
):
    """Request a consultation with a platform dentist (MVP — stores request)."""
    users = get_portal_users_col()
    try:
        dentist_oid = ObjectId(req.dentist_id)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail="Invalid dentist id") from exc

    dentist = await users.find_one({"_id": dentist_oid, "role": "dentist"})
    if not dentist:
        raise HTTPException(status_code=404, detail="Dentist not found")

    appt_id = str(uuid4())
    col = get_portal_appointments_col()
    await col.insert_one({
        "appointment_id": appt_id,
        "patient_id": user["sub"],
        "dentist_id": req.dentist_id,
        "issue": req.issue,
        "scan_id": req.scan_id,
        "session_id": req.session_id,
        "message": req.message,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    })

    logger.info("[APPOINTMENT] patient=%s dentist=%s appt=%s", user["sub"], req.dentist_id, appt_id)
    return BookConsultationResponse(
        appointment_id=appt_id,
        status="pending",
        message="Consultation request sent. The dentist will contact you shortly.",
    )
