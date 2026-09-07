"""Structured patient data retriever for DaantShaant Central Dentist.

Strictly tenant-scoped SQL queries. Every query filters by the authenticated
patient's UUID. Data for other patients can NEVER be accessed.
NO embeddings. Direct relational data retrieval via SQLAlchemy AsyncSession.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import (
    AppointmentRequest,
    ClinicalReport,
    Dentist,
    Scan,
    ScanFinding,
    User,
)

logger = logging.getLogger(__name__)


@dataclass
class FindingItem:
    finding_code: str
    region: Optional[str]
    observation: str
    confidence: float
    visibility: Optional[str] = None


@dataclass
class ScanSummary:
    scan_id: str
    created_at: datetime
    input_mode: str
    status: str
    quality_score: Optional[float] = None
    report_id: Optional[str] = None
    verdict: Optional[str] = None
    urgency_level: Optional[str] = None
    summary: Optional[str] = None
    confidence: Optional[float] = None
    recommended_specialist: Optional[str] = None
    findings: list[FindingItem] = field(default_factory=list)


@dataclass
class AppointmentSummary:
    appointment_id: str
    dentist_id: str
    dentist_name: str
    clinic_name: Optional[str]
    clinic_address: Optional[str]
    clinic_phone: Optional[str]
    status: str
    preferred_time: Optional[str]
    issue: Optional[str]
    created_at: datetime


@dataclass
class PatientContextData:
    patient_user_id: str
    patient_name: Optional[str] = None
    total_scans: int = 0
    latest_scan: Optional[ScanSummary] = None
    previous_scans: list[ScanSummary] = field(default_factory=list)
    appointments: list[AppointmentSummary] = field(default_factory=list)
    active_dentist: Optional[dict[str, Any]] = None


async def _fetch_scan_findings(session: AsyncSession, scan_id: UUID) -> list[FindingItem]:
    """Retrieve findings for a specific scan."""
    result = await session.execute(
        select(ScanFinding).where(ScanFinding.scan_id == scan_id)
    )
    items: list[FindingItem] = []
    for f in result.scalars():
        items.append(
            FindingItem(
                finding_code=f.finding_code,
                region=f.region,
                observation=f.observation or f.finding_code.replace("_", " "),
                confidence=float(f.confidence or 0.0),
                visibility=f.raw_ai_metadata.get("visibility") if isinstance(f.raw_ai_metadata, dict) else None,
            )
        )
    return items


async def retrieve_latest_screening(
    session: AsyncSession,
    patient_user_id: UUID,
) -> Optional[ScanSummary]:
    """Fetch only the latest screening scan, report, and findings for the patient."""
    query = (
        select(Scan, ClinicalReport)
        .outerjoin(ClinicalReport, ClinicalReport.scan_id == Scan.id)
        .where(Scan.patient_user_id == patient_user_id)
        .order_by(desc(Scan.created_at))
        .limit(1)
    )
    result = await session.execute(query)
    row = result.first()
    if not row:
        return None

    scan, report = row[0], row[1]
    findings = await _fetch_scan_findings(session, scan.id)

    confidence = None
    if report and isinstance(report.agent_trace_summary, dict):
        confidence = report.agent_trace_summary.get("confidence")
    elif findings:
        confidence = max((f.confidence for f in findings), default=None)

    return ScanSummary(
        scan_id=str(scan.id),
        created_at=scan.created_at,
        input_mode=scan.input_mode or "upload",
        status=scan.status or "completed",
        quality_score=scan.mechanical_quality_score,
        report_id=str(report.id) if report else None,
        verdict=report.verdict if report else None,
        urgency_level=report.urgency_level if report else None,
        summary=report.summary if report else None,
        confidence=confidence,
        recommended_specialist=report.recommended_specialist if report else None,
        findings=findings,
    )


async def retrieve_scan_comparison(
    session: AsyncSession,
    patient_user_id: UUID,
) -> tuple[Optional[ScanSummary], Optional[ScanSummary]]:
    """Fetch the latest two completed scans for side-by-side comparison."""
    query = (
        select(Scan, ClinicalReport)
        .outerjoin(ClinicalReport, ClinicalReport.scan_id == Scan.id)
        .where(Scan.patient_user_id == patient_user_id)
        .order_by(desc(Scan.created_at))
        .limit(2)
    )
    result = await session.execute(query)
    rows = result.all()
    if not rows:
        return None, None

    summaries: list[ScanSummary] = []
    for scan, report in rows:
        findings = await _fetch_scan_findings(session, scan.id)
        confidence = None
        if report and isinstance(report.agent_trace_summary, dict):
            confidence = report.agent_trace_summary.get("confidence")
        elif findings:
            confidence = max((f.confidence for f in findings), default=None)

        summaries.append(
            ScanSummary(
                scan_id=str(scan.id),
                created_at=scan.created_at,
                input_mode=scan.input_mode or "upload",
                status=scan.status or "completed",
                quality_score=scan.mechanical_quality_score,
                report_id=str(report.id) if report else None,
                verdict=report.verdict if report else None,
                urgency_level=report.urgency_level if report else None,
                summary=report.summary if report else None,
                confidence=confidence,
                recommended_specialist=report.recommended_specialist if report else None,
                findings=findings,
            )
        )

    latest = summaries[0] if len(summaries) >= 1 else None
    previous = summaries[1] if len(summaries) >= 2 else None
    return latest, previous


async def retrieve_scan_history(
    session: AsyncSession,
    patient_user_id: UUID,
    limit: int = 5,
) -> list[ScanSummary]:
    """Fetch historical screening scans and reports for the patient."""
    query = (
        select(Scan, ClinicalReport)
        .outerjoin(ClinicalReport, ClinicalReport.scan_id == Scan.id)
        .where(Scan.patient_user_id == patient_user_id)
        .order_by(desc(Scan.created_at))
        .limit(limit)
    )
    result = await session.execute(query)
    rows = result.all()

    summaries: list[ScanSummary] = []
    for scan, report in rows:
        findings = await _fetch_scan_findings(session, scan.id)
        confidence = None
        if report and isinstance(report.agent_trace_summary, dict):
            confidence = report.agent_trace_summary.get("confidence")
        elif findings:
            confidence = max((f.confidence for f in findings), default=None)

        summaries.append(
            ScanSummary(
                scan_id=str(scan.id),
                created_at=scan.created_at,
                input_mode=scan.input_mode or "upload",
                status=scan.status or "completed",
                quality_score=scan.mechanical_quality_score,
                report_id=str(report.id) if report else None,
                verdict=report.verdict if report else None,
                urgency_level=report.urgency_level if report else None,
                summary=report.summary if report else None,
                confidence=confidence,
                recommended_specialist=report.recommended_specialist if report else None,
                findings=findings,
            )
        )
    return summaries


async def retrieve_patient_appointments(
    session: AsyncSession,
    patient_user_id: UUID,
    limit: int = 5,
) -> list[AppointmentSummary]:
    """Fetch appointments belonging strictly to the authenticated patient."""
    query = (
        select(AppointmentRequest, Dentist)
        .outerjoin(Dentist, Dentist.id == AppointmentRequest.dentist_id)
        .where(AppointmentRequest.patient_user_id == patient_user_id)
        .order_by(desc(AppointmentRequest.created_at))
        .limit(limit)
    )
    result = await session.execute(query)
    rows = result.all()

    appointments: list[AppointmentSummary] = []
    for appt, dentist in rows:
        appointments.append(
            AppointmentSummary(
                appointment_id=str(appt.id),
                dentist_id=str(appt.dentist_id),
                dentist_name=dentist.name if dentist else "Assigned Dentist",
                clinic_name=dentist.clinic_name if dentist else None,
                clinic_address=dentist.address if dentist else None,
                clinic_phone=dentist.phone if dentist else None,
                status=appt.status,
                preferred_time=appt.preferred_time,
                issue=appt.issue,
                created_at=appt.created_at,
            )
        )
    return appointments


async def retrieve_patient_dentist_info(
    session: AsyncSession,
    patient_user_id: UUID,
) -> Optional[dict[str, Any]]:
    """Retrieve dentist information associated with the patient's recent appointments."""
    query = (
        select(Dentist)
        .join(AppointmentRequest, AppointmentRequest.dentist_id == Dentist.id)
        .where(AppointmentRequest.patient_user_id == patient_user_id)
        .order_by(desc(AppointmentRequest.created_at))
        .limit(1)
    )
    result = await session.execute(query)
    dentist = result.scalar_one_or_none()
    if not dentist:
        return None

    return {
        "dentist_id": str(dentist.id),
        "name": dentist.name,
        "clinic_name": dentist.clinic_name,
        "address": dentist.address,
        "phone": dentist.phone,
        "city": dentist.city,
        "rating": dentist.rating,
        "is_verified": dentist.is_verified,
    }
