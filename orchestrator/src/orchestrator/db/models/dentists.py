"""Dentist model — supports both platform and OSM/community dentists."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.db.base import Base


class Dentist(Base):
    """Dentist record — platform-registered or external (OSM/curated)."""

    __tablename__ = "dentists"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="platform"
    )  # platform | osm | curated
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    clinic_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    specialties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    degree: Mapped[str | None] = mapped_column(String(100), nullable=True)
    degree_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    institution: Mapped[str | None] = mapped_column(String(200), nullable=True)
    specialized_training: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qualifications: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rating: Mapped[float | None] = mapped_column(nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_partner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    commission_rate: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_dentists_owner_user_id", "owner_user_id", unique=True),
        Index("ix_dentists_source_external", "source", "external_id"),
        Index("ix_dentists_city", "city"),
    )
