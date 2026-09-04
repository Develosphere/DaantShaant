"""Authenticated aggregate dashboard endpoints for patients and dentists."""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.session import get_db_session
from orchestrator.dentist_portal.auth import get_current_dentist, get_current_patient
from orchestrator.repositories import (
    AppointmentRepository,
    DentistRepository,
    OrderRepository,
    ProductRepository,
    RecommendationRepository,
    ScanRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["portal-dashboards"])


def _normalize_urgency(urgency_val: str | None) -> str:
    if not urgency_val:
        return "routine"
    u = urgency_val.lower().strip()
    if any(term in u for term in ("emergency", "critical")):
        return "emergency"
    if any(term in u for term in ("urgent", "high")):
        return "urgent"
    if any(term in u for term in ("soon", "moderate")):
        return "soon"
    return "routine"


@router.get("/patient/dashboard", response_model=dict)
async def get_patient_dashboard(
    patient_user: dict = Depends(get_current_patient),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Return real aggregate dashboard data scoped strictly to the authenticated patient."""
    user_id: UUID = patient_user["user_id"]

    scan_repo = ScanRepository(session)
    order_repo = OrderRepository(session)
    product_repo = ProductRepository(session)
    appt_repo = AppointmentRepository(session)
    recom_repo = RecommendationRepository(session)
    dentist_repo = DentistRepository(session)

    # 1. Counts
    scan_count = await scan_repo.count_scans(user_id)
    order_count = await order_repo.count_for_patient(user_id)

    # 2. Latest screening
    latest = await scan_repo.get_latest_screening(user_id)
    latest_screening: dict[str, Any] | None = None
    oral_status: str | None = None

    if latest is not None:
        scan, report = latest
        canonical_urgency = _normalize_urgency(report.urgency_level if report else None)
        oral_status = canonical_urgency

        major_concerns = []
        if report and report.possible_concerns and isinstance(report.possible_concerns, dict):
            findings_data = report.possible_concerns.get("findings")
            if isinstance(findings_data, list):
                for f in findings_data[:3]:
                    if isinstance(f, dict):
                        obs = f.get("observation") or f.get("label") or f.get("finding_code")
                        if obs:
                            major_concerns.append(str(obs).replace("_", " ").title())
        if not major_concerns and report and report.verdict:
            major_concerns.append(report.verdict)

        confidence = 0.85
        if report and report.agent_trace_summary and isinstance(report.agent_trace_summary, dict):
            confidence = float(report.agent_trace_summary.get("confidence") or 0.85)
        elif scan.mechanical_quality_score is not None:
            confidence = float(scan.mechanical_quality_score)

        latest_screening = {
            "scan_id": str(scan.id),
            "created_at": report.created_at.isoformat() if report else scan.created_at.isoformat(),
            "verdict": report.verdict if report else "Completed Screening",
            "summary": report.summary if report else "Oral health screening recorded.",
            "urgency": canonical_urgency,
            "confidence": confidence,
            "recommended_specialist": (report.recommended_specialist if report and report.recommended_specialist else "General Dentist"),
            "major_concerns": major_concerns,
        }

    # 3. Clinically relevant recommended products
    recommended_products: list[dict[str, Any]] = []
    if latest_screening:
        # Check if saved ProductRecommendation exists for this patient
        persisted_recoms = await recom_repo.list_product_for_patient(user_id, limit=1)
        if persisted_recoms:
            rec_row = persisted_recoms[0]
            rec_items = (rec_row.recommendations or {}).get("products", [])
            for item in rec_items[:3]:
                pid_str = item.get("product_id") if isinstance(item, dict) else str(item)
                try:
                    p = await product_repo.get(UUID(pid_str))
                    if p and p.status == "active":
                        dentist = await dentist_repo.get(p.dentist_id)
                        seller_name = dentist.clinic_name or dentist.doctor_name if dentist else "Partner Dental Clinic"
                        recommended_products.append({
                            "product_id": str(p.id),
                            "name": p.name,
                            "category": p.category or "other",
                            "price": float(p.price or 0),
                            "dentist_name": seller_name,
                        })
                except (ValueError, TypeError):
                    continue

        # If no recommendation record exists, deterministically match active products
        if not recommended_products:
            verdict_text = (latest_screening.get("verdict") or "").lower()
            concerns_text = " ".join(latest_screening.get("major_concerns") or []).lower()
            combined_text = f"{verdict_text} {concerns_text}"

            category = None
            search_keyword = None
            if any(term in combined_text for term in ("healthy", "clean", "normal")):
                category = "toothbrush"
            elif any(term in combined_text for term in ("cavity", "decay", "caries")):
                search_keyword = "cavity"
            elif any(term in combined_text for term in ("gum", "gingivitis", "periodontal")):
                search_keyword = "gum"
            elif any(term in combined_text for term in ("plaque", "tartar", "calculus")):
                search_keyword = "plaque"
            elif any(term in combined_text for term in ("discolor", "stain", "whitening")):
                search_keyword = "whitening"
            else:
                category = "toothbrush"

            active_products = await product_repo.list_active(category=category, search=search_keyword, limit=3)
            if not active_products and category:
                active_products = await product_repo.list_active(limit=3)

            for p in active_products[:3]:
                dentist = await dentist_repo.get(p.dentist_id)
                seller_name = dentist.clinic_name or dentist.doctor_name if dentist else "Partner Dental Clinic"
                recommended_products.append({
                    "product_id": str(p.id),
                    "name": p.name,
                    "category": p.category or "other",
                    "price": float(p.price or 0),
                    "dentist_name": seller_name,
                })

    # 4. Recent orders (limit 4)
    patient_order_rows = await order_repo.list_for_patient(user_id, limit=4)
    recent_orders: list[dict[str, Any]] = []
    for ord_obj, d_obj in patient_order_rows:
        items = ord_obj.items or {}
        seller_name = (
            items.get("dentist_name")
            or items.get("seller_name")
            or (d_obj.clinic_name if d_obj else None)
            or (d_obj.doctor_name if d_obj else None)
            or "Partner Dental Clinic"
        )
        recent_orders.append({
            "order_id": str(ord_obj.id),
            "product_id": str(items.get("product_id", "")),
            "product_name": items.get("product_name", "Oral Care Product"),
            "dentist_name": seller_name,
            "seller_name": seller_name,
            "quantity": int(items.get("quantity", 1)),
            "price": float(ord_obj.total),
            "status": ord_obj.status,
            "created_at": ord_obj.created_at.isoformat() if ord_obj.created_at else "",
        })

    # 5. Recent Activity (derived from real scans, orders, and appointments)
    activity_events = []
    recent_scans = await scan_repo.list_owned(user_id, limit=3)
    for s in recent_scans:
        activity_events.append({
            "id": f"scan-{s.id}",
            "type": "scan",
            "title": "Oral Health Screening",
            "description": f"Status: {s.status}",
            "created_at": s.created_at.isoformat() if s.created_at else "",
            "_raw_time": s.created_at,
        })

    for ord_obj, _ in patient_order_rows[:3]:
        p_name = (ord_obj.items or {}).get("product_name", "Product")
        activity_events.append({
            "id": f"order-{ord_obj.id}",
            "type": "order",
            "title": f"Order: {p_name}",
            "description": f"Status: {ord_obj.status} • ${float(ord_obj.total):.2f}",
            "created_at": ord_obj.created_at.isoformat() if ord_obj.created_at else "",
            "_raw_time": ord_obj.created_at,
        })

    recent_appts = await appt_repo.list_for_principal(user_id=user_id, role="patient", limit=3)
    for a in recent_appts:
        activity_events.append({
            "id": f"appt-{a.id}",
            "type": "appointment",
            "title": f"Consultation: {a.issue or 'Dental Checkup'}",
            "description": f"Status: {a.status}",
            "created_at": a.created_at.isoformat() if a.created_at else "",
            "_raw_time": a.created_at,
        })

    # Sort real activity by timestamp descending
    activity_events.sort(key=lambda x: x["_raw_time"] if x["_raw_time"] else "", reverse=True)
    recent_activity = [
        {
            "id": e["id"],
            "type": e["type"],
            "title": e["title"],
            "description": e["description"],
            "created_at": e["created_at"],
        }
        for e in activity_events[:5]
    ]

    return {
        "stats": {
            "scan_count": scan_count,
            "order_count": order_count,
            "oral_status": oral_status,
        },
        "latest_screening": latest_screening,
        "recommended_products": recommended_products,
        "recent_orders": recent_orders,
        "recent_activity": recent_activity,
    }


@router.get("/dentist/dashboard", response_model=dict)
async def get_dentist_dashboard(
    dentist_user: dict = Depends(get_current_dentist),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Return real aggregate dashboard data scoped strictly to the authenticated dentist."""
    user_id: UUID = dentist_user["user_id"]

    dentist_repo = DentistRepository(session)
    product_repo = ProductRepository(session)
    order_repo = OrderRepository(session)
    appt_repo = AppointmentRepository(session)
    user_repo = UserRepository(session)

    dentist = await dentist_repo.get_by_owner(user_id)
    if not dentist:
        raise HTTPException(status_code=404, detail="Dentist profile not found")

    # 1. Counts (strictly scoped to this dentist)
    product_count = await product_repo.count_owned(user_id)
    order_count = await order_repo.count_for_dentist(user_id)
    pending_order_count = await order_repo.count_for_dentist(user_id, status=["pending", "placed"])
    completed_order_count = await order_repo.count_for_dentist(
        user_id, status=["completed", "shipped", "confirmed"]
    )
    appointment_count = await appt_repo.count_for_principal(user_id=user_id, role="dentist")
    pending_appointment_count = await appt_repo.count_for_principal(
        user_id=user_id, role="dentist", status="pending"
    )

    # 2. Recent orders (latest 4 for this dentist)
    orders = await order_repo.list_for_dentist(user_id, limit=4)
    recent_orders = [
        {
            "order_id": str(row.id),
            "product_id": str((row.items or {}).get("product_id", "")),
            "product_name": (row.items or {}).get("product_name", "Product"),
            "quantity": int((row.items or {}).get("quantity", 1)),
            "price": float(row.total),
            "patient_name": (row.items or {}).get("patient_name", "Patient"),
            "patient_email": (row.items or {}).get("patient_email", ""),
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
        for row in orders
    ]

    # 3. Recent appointments (latest 4 booked with this dentist)
    appts = await appt_repo.list_for_principal(user_id=user_id, role="dentist", limit=4)
    recent_appointments = []
    for item in appts:
        entry = {
            "appointment_id": str(item.id),
            "issue": item.issue or "General Dental Consultation",
            "status": item.status,
            "preferred_time": item.preferred_time,
            "created_at": item.created_at.isoformat() if item.created_at else "",
            "patient_name": "Patient",
        }
        patient = await user_repo.get(item.patient_user_id)
        if patient:
            full_name = f"{patient.first_name or ''} {patient.last_name or ''}".strip()
            entry["patient_name"] = full_name or "Patient"
            entry["patient_email"] = patient.email or ""
        recent_appointments.append(entry)

    return {
        "stats": {
            "product_count": product_count,
            "order_count": order_count,
            "pending_order_count": pending_order_count,
            "completed_order_count": completed_order_count,
            "appointment_count": appointment_count,
            "pending_appointment_count": pending_appointment_count,
        },
        "recent_orders": recent_orders,
        "recent_appointments": recent_appointments,
    }
