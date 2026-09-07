"""Dental models: Scan, ScanFinding, ClinicalReport."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.db.base import Base


class Scan(Base):
    """A teeth scan session (snapshot, upload, or live)."""

    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    input_mode: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # snapshot | upload | live
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    media_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mechanical_quality_score: Mapped[float | None] = mapped_column(nullable=True)
    mechanical_quality_issues: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(nullable=True)
    relevance_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ai_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_scans_patient_user_id", "patient_user_id"),
        Index("ix_scans_created_at", "created_at"),
    )


class ScanFinding(Base):
    """Individual finding from a scan. A finding is NOT automatically a confirmed disease."""

    __tablename__ = "scan_findings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    finding_code: Mapped[str] = mapped_column(String(50), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tooth_reference: Mapped[str | None] = mapped_column(String(20), nullable=True)
    observation: Mapped[str] = mapped_column(String(500), nullable=False)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    visibility: Mapped[float | None] = mapped_column(nullable=True)
    raw_ai_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_scan_findings_scan_id", "scan_id"),
    )


class ClinicalReport(Base):
    """Clinical report generated from scan findings."""

    __tablename__ = "clinical_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="SET NULL"), nullable=False
    )
    patient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    verdict: Mapped[str] = mapped_column(String(50), nullable=False)
    urgency_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    possible_concerns: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    recommended_actions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    recommended_specialist: Mapped[str | None] = mapped_column(String(100), nullable=True)
    limitations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    evidence_refs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    agent_trace_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_clinical_reports_scan_id", "scan_id"),
        Index("ix_clinical_reports_patient_user_id", "patient_user_id"),
    )
