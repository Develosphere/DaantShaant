# Third-party dataset metadata is recorded for attribution/provenance.
# Dataset files remain outside Git and are not bundled with DaantShaant.

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class DatasetCase(BaseModel):
    """Single evaluation case in a dataset manifest."""

    id: str
    image_path: Optional[str] = None
    expected_relevance: Optional[str] = None  # "relevant" | "retake" | "unrelated"
    expected_findings: Optional[list[str]] = Field(default_factory=list)
    expected_urgency: Optional[str] = None  # "routine" | "soon" | "urgent" | "emergency"
    expected_specialist: Optional[str] = None
    source: Optional[str] = None  # e.g., "Roboflow Oral Disease", "Zenodo", "Synthetic"
    license: Optional[str] = None  # e.g., "CC-BY-4.0", "MIT", "Proprietary"
    attribution: Optional[str] = None
    notes: Optional[str] = None


class Manifest(BaseModel):
    """Collection of evaluation cases."""

    cases: list[DatasetCase] = Field(default_factory=list)
    description: Optional[str] = None
    version: str = "1.0"


class CaseResult(BaseModel):
    """Outcome of running evaluation on a single case."""

    case_id: str
    predicted_relevance: Optional[str] = None
    predicted_findings: list[str] = Field(default_factory=list)
    predicted_urgency: Optional[str] = None
    predicted_specialist: Optional[str] = None
    patient_facing_text: Optional[str] = None
    is_schema_valid: bool = True
    malformed_errors: list[str] = Field(default_factory=list)
    provider: Optional[str] = None
    model: Optional[str] = None
    fallback_used: bool = False
    relevance_ms: float = 0.0
    clinical_vision_ms: float = 0.0
    triage_ms: float = 0.0
    total_ms: float = 0.0


class LatencyStats(BaseModel):
    """Latency distribution summary."""

    count: int = 0
    mean_ms: float = 0.0
    median_ms: float = 0.0
    p95_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0


class RelevanceMetrics(BaseModel):
    """Evaluation metrics for semantic relevance."""

    total_cases: int = 0
    correct_count: int = 0
    accuracy: float = 0.0
    per_class_counts: dict[str, int] = Field(default_factory=dict)
    confusion_matrix: dict[str, dict[str, int]] = Field(default_factory=dict)


class FindingMetrics(BaseModel):
    """Multi-label evaluation metrics for clinical visual findings."""

    total_evaluated: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    exact_match_rate: float = 0.0


class TriageMetrics(BaseModel):
    """Evaluation metrics for deterministic clinical triage."""

    total_evaluated: int = 0
    urgency_correct: int = 0
    urgency_accuracy: float = 0.0
    specialist_evaluated: int = 0
    specialist_correct: int = 0
    specialist_accuracy: float = 0.0
    unsafe_wording_violations: int = 0
    unsafe_phrases_detected: list[str] = Field(default_factory=list)


class StructuredOutputMetrics(BaseModel):
    """Validation tracking for schema conformance."""

    total_cases: int = 0
    valid_schema_count: int = 0
    valid_schema_pct: float = 1.0
    malformed_response_count: int = 0
    missing_required_fields_count: int = 0


class RankingBenchmarkResult(BaseModel):
    """Benchmark outcome for dentist matching and ranking."""

    total_scenarios: int = 0
    passed_scenarios: int = 0
    accuracy: float = 0.0
    scenario_details: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    """Complete evaluation report summary."""

    mode: str = "mock"  # "mock" | "real"
    total_cases: int = 0
    relevance: RelevanceMetrics = Field(default_factory=RelevanceMetrics)
    findings: FindingMetrics = Field(default_factory=FindingMetrics)
    triage: TriageMetrics = Field(default_factory=TriageMetrics)
    structured: StructuredOutputMetrics = Field(default_factory=StructuredOutputMetrics)
    ranking: RankingBenchmarkResult = Field(default_factory=RankingBenchmarkResult)
    latency: LatencyStats = Field(default_factory=LatencyStats)
    fallback_count: int = 0
    fallback_rate: float = 0.0
    demo_summary: dict[str, Any] = Field(default_factory=dict)
