"""Compose Teeth Analyzer → Diagnosis (MCP analyze_teeth_image flow).

Phase 4-lite: ``run_scan_with_relevance`` now delegates to the unified clinical
LangGraph (``clinical.graph.run_clinical_graph``) while preserving the exact
same ``ScanOutcome`` response shape. The graph orchestrates the existing
pipeline — relevance → clinical vision → triage → report → persist — inside
a deterministic StateGraph.

``run_teeth_analysis_pipeline`` remains the low-level boundary that the graph
calls for the Teeth Analyzer + Diagnosis HTTP calls.
"""

import logging
import time
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from uuid import UUID

from dantshaant_common.clients import DiagnosisClient, TeethAnalyzerClient
from dantshaant_common.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    DiagnoseRequest,
    DiagnoseResponse,
)
from orchestrator.ai.gateway import AIGateway
from orchestrator.clinical.relevance import (
    DentalRelevanceResult,
    evaluate_dental_relevance,
)
from orchestrator.config import settings

logger = logging.getLogger(__name__)


class TeethAnalyzePipelineRequest(BaseModel):
    user_id: UUID
    image_base64: str
    image_mime_type: str = "image/jpeg"
    locale: str = "en"


class AuthenticatedTeethAnalyzeRequest(BaseModel):
    """External scan payload; patient identity comes from the access token."""

    image_base64: str
    image_mime_type: str = "image/jpeg"
    locale: str = "en"


class TeethAnalyzePipelineResponse(BaseModel):
    analysis: AnalyzeResponse
    diagnosis: DiagnoseResponse


class RelevanceInfo(BaseModel):
    """Minimal, provider-neutral view of a relevance verdict.

    Deliberately omits ``is_dental_relevant`` so downstream consumers route on
    ``classification`` / ``recommended_action`` (``retake`` is not the same as
    ``unrelated``) and never on a single boolean.
    """

    classification: Literal["relevant", "retake", "unrelated"]
    recommended_action: Literal["continue", "retake", "reject"]
    reason: str = ""
    retake_reason: str | None = None
    confidence: float = 0.0
    relevance_score: float = 0.0
    visible_regions: list[str] = Field(default_factory=list)


class ScanOutcome(BaseModel):
    """Outcome of a relevance-gated scan for any mode (snapshot/upload/live).

    ``status`` is ``analyzed`` only when clinical vision ran and both
    ``analysis``/``diagnosis`` are populated; ``retake``/``rejected`` short-
    circuit before clinical vision and carry just the relevance verdict.
    """

    status: Literal["analyzed", "retake", "rejected"]
    relevance: RelevanceInfo
    analysis: AnalyzeResponse | None = None
    diagnosis: DiagnoseResponse | None = None


def _relevance_info(relevance: DentalRelevanceResult) -> RelevanceInfo:
    return RelevanceInfo(
        classification=relevance.classification,
        recommended_action=relevance.recommended_action,
        reason=relevance.reason,
        retake_reason=relevance.retake_reason,
        confidence=relevance.confidence,
        relevance_score=relevance.relevance_score,
        visible_regions=list(relevance.visible_regions),
    )


async def run_scan_with_relevance(
    request: TeethAnalyzePipelineRequest,
    gateway: AIGateway | None = None,
    *,
    db_session: object | None = None,
    input_mode: str = "snapshot",
) -> ScanOutcome:
    """Relevance-gate a single image, then run clinical analysis if allowed.

    Phase 4-lite: this function now delegates to the unified clinical
    LangGraph (``clinical.graph.run_clinical_graph``) which orchestrates
    the same pipeline — relevance → clinical vision → triage → report →
    persist — inside a deterministic StateGraph.

    This is the ONE shared integration point for snapshot, upload and live.
    Provider failures from relevance propagate unchanged - a technical outage
    is never reported as an ``unrelated`` rejection.
    """
    from orchestrator.clinical.graph import run_clinical_graph

    return await run_clinical_graph(
        request,
        gateway=gateway,
        db_session=db_session,
        input_mode=input_mode,
    )


async def run_teeth_analysis_pipeline(
    request: TeethAnalyzePipelineRequest,
) -> TeethAnalyzePipelineResponse:
    analyzer = TeethAnalyzerClient(
        settings.teeth_analyzer_url,
        timeout=settings.request_timeout_seconds,
    )
    diagnosis_client = DiagnosisClient(
        settings.diagnosis_url,
        timeout=settings.request_timeout_seconds,
    )

    analyze_req = AnalyzeRequest(
        user_id=request.user_id,
        image_base64=request.image_base64,
        image_mime_type=request.image_mime_type,
        locale=request.locale,
    )
    analysis = await analyzer.analyze(analyze_req)

    diagnose_req = DiagnoseRequest(
        user_id=request.user_id,
        analysis_id=analysis.analysis_id,
        findings=analysis.findings,
        overall_quality_score=analysis.overall_quality_score,
    )
    diagnosis = await diagnosis_client.diagnose(diagnose_req)

    return TeethAnalyzePipelineResponse(analysis=analysis, diagnosis=diagnosis)


async def check_dependencies() -> dict[str, str]:
    deps: dict[str, str] = {}
    analyzer = TeethAnalyzerClient(
        settings.teeth_analyzer_url,
        timeout=5.0,
    )
    diagnosis_client = DiagnosisClient(
        settings.diagnosis_url,
        timeout=5.0,
    )
    for name, check in [
        ("teeth_analyzer", analyzer.health),
        ("diagnosis", diagnosis_client.health),
    ]:
        try:
            await check()
            deps[name] = "ok"
        except (httpx.HTTPError, httpx.TimeoutException):
            deps[name] = "unreachable"
    return deps
