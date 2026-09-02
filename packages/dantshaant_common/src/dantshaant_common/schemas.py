"""Pydantic models aligned with specs/*.openapi.yaml — single source for all services."""

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class VisualFinding(BaseModel):
    """One VISUAL SCREENING observation (never a confirmed diagnosis)."""

    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    region: str | None = None
    # Phase 3B-lite (additive/optional): how clearly the area was visible,
    # "clear" | "partial" | "limited". Used only to state screening limitations.
    visibility: str | None = None


# --- Teeth Analyzer (specs/teeth_analyzer.openapi.yaml) ---


class AnalyzeRequest(BaseModel):
    user_id: UUID
    image_base64: str
    image_mime_type: str = "image/jpeg"
    locale: str = "en"


class AnalyzeResponse(BaseModel):
    analysis_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    findings: list[VisualFinding]
    overall_quality_score: float = Field(ge=0.0, le=1.0, default=0.0)
    model_id: str = "stub-v0"
    inference_ms: int = 0
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- Diagnosis (specs/diagnosis.openapi.yaml) ---


class ConditionLabel(str, Enum):
    HEALTHY = "Healthy"
    PLAQUE_TARTAR = "Plaque / Tartar"
    EARLY_CAVITY = "Early Cavity"
    ADVANCED_CAVITY = "Advanced Cavity"
    GINGIVITIS = "Gingivitis"
    SEVERE_GUM_DISEASE = "Severe Gum Disease"
    DISCOLORATION = "Discoloration"
    # Phase 3B-lite (additive): a missing/broken tooth is structural damage and
    # must NOT be reported as an advanced cavity.
    MISSING_OR_DAMAGED_TOOTH = "Missing / Damaged Tooth"
    UNKNOWN = "Unknown"


class Severity(str, Enum):
    NONE = "None"
    MILD = "Mild"
    MODERATE = "Moderate"
    HIGH = "High"
    CRITICAL = "Critical"


class ActionTrigger(str, Enum):
    MAINTENANCE_REMINDER = "maintenance_reminder"
    PRODUCT_SUGGEST_BRUSHING = "product_suggest_brushing_alarm"
    PRODUCT_DENTIST_2_WEEKS = "product_dentist_2_weeks"
    DENTIST_URGENT_1_WEEK = "dentist_urgent_1_week"
    ANTIBACTERIAL_DENTIST = "antibacterial_product_dentist"
    IMMEDIATE_DENTIST = "immediate_dentist_referral"
    WHITENING_PRODUCT = "whitening_product"
    REQUEST_CLEARER_PHOTO = "request_clearer_photo"


class UrgencyLevel(str, Enum):
    """Screening urgency. Ordered routine < soon < urgent < emergency."""

    ROUTINE = "routine"
    SOON = "soon"
    URGENT = "urgent"
    EMERGENCY = "emergency"


SCREENING_DISCLAIMER = (
    "AI screening based only on what is visible in this image. "
    "It is not a diagnosis and should be confirmed by a licensed dentist."
)


class TriageResult(BaseModel):
    """Deterministic, rule-based AI screening triage (Phase 3B-lite).

    Produced WITHOUT any LLM/provider call from visual screening findings.
    Wording is deliberately non-definitive: possible concerns, screening
    observations, and licensed-dentist follow-up - never a confirmed disease,
    never treatment prescriptions, never guaranteed outcomes.
    """

    verdict: str
    condition_summary: str
    possible_concerns: list[str] = Field(default_factory=list)
    urgency_level: UrgencyLevel = UrgencyLevel.ROUTINE
    recommended_actions: list[str] = Field(default_factory=list)
    recommended_specialist: str | None = None
    visit_timeframe: str = ""
    limitations: list[str] = Field(default_factory=list)
    supporting_findings: list[str] = Field(default_factory=list)
    # Lightweight internal rule metadata only (no fabricated citations/sources).
    rule_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    disclaimer: str = SCREENING_DISCLAIMER


class DiagnoseRequest(BaseModel):
    user_id: UUID
    analysis_id: UUID
    findings: list[VisualFinding]
    overall_quality_score: float = Field(ge=0.0, le=1.0, default=0.0)
    patient_history_summary: str | None = None


class DiagnoseResponse(BaseModel):
    diagnosis_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    analysis_id: UUID
    condition_label: ConditionLabel
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    meets_threshold: bool
    action_trigger: ActionTrigger
    disclaimer: str = (
        "This is an awareness tool, not a medical diagnosis. "
        "Please consult a licensed dentist for confirmation."
    )
    diagnosed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Phase 3B-lite (additive/optional): safer screening triage detail. Existing
    # consumers that only read the legacy fields keep working unchanged.
    triage: TriageResult | None = None
