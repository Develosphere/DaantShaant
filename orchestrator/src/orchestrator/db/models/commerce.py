"""Commerce and recommendation models: Product, ProductRecommendation, Order,
DentistRecommendation, AppointmentRequest, CommissionRecord."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.db.base import Base


class Product(Base):
    """Dentist-listed product for commerce."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dentist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dentists.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    raw_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    problems_solved: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    images: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recommendation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_products_dentist_id", "dentist_id"),
    )


class ProductRecommendation(Base):
    """AI-generated product recommendation for a patient."""

    __tablename__ = "product_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    scan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="SET NULL"), nullable=True
    )
    issue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    recommendations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Order(Base):
    """Patient order for products from a dentist."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dentist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dentists.id", ondelete="SET NULL"), nullable=False
    )
    patient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    items: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DentistRecommendation(Base):
    """AI-generated dentist recommendation for a patient."""

    __tablename__ = "dentist_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="SET NULL"), nullable=True
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinical_reports.id", ondelete="SET NULL"), nullable=True
    )
    specialist: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    patient_lat: Mapped[float | None] = mapped_column(nullable=True)
    patient_lng: Mapped[float | None] = mapped_column(nullable=True)
    results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_dentist_recommendations_patient_user_id", "patient_user_id"),
    )


class AppointmentRequest(Base):
    """Patient request for an appointment with a dentist."""

    __tablename__ = "appointment_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    dentist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dentists.id", ondelete="SET NULL"), nullable=False
    )
    scan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="SET NULL"), nullable=True
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinical_reports.id", ondelete="SET NULL"), nullable=True
    )
    recommendation_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    issue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_appointment_requests_patient_user_id", "patient_user_id"),
        Index("ix_appointment_requests_dentist_id", "dentist_id"),
    )


class CommissionRecord(Base):
    """Commission tracking for completed appointments."""

    __tablename__ = "commission_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_requests.id", ondelete="SET NULL"), nullable=False
    )
    dentist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dentists.id", ondelete="SET NULL"), nullable=False
    )
    commission_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    commission_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
