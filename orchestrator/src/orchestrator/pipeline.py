"""Compose Teeth Analyzer → Diagnosis (MCP analyze_teeth_image flow).

Phase 2B.2: production scan flow gates the expensive clinical vision/analysis
behind semantic dental relevance.  ``run_scan_with_relevance`` is the single
reusable entry point shared by the snapshot/upload HTTP route and the live
WebSocket frame handler, so relevance routing lives in exactly one place.
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
) -> ScanOutcome:
    """Relevance-gate a single image, then run clinical analysis if allowed.

    This is the ONE shared integration point for snapshot, upload and live.
    Semantic relevance is evaluated before the Teeth Analyzer request so that
    expensive clinical vision never runs for ``retake``/``unrelated`` images.
    Provider failures from relevance propagate unchanged - a technical outage
    is never reported as an ``unrelated`` rejection.
    """
    started = time.perf_counter()
    relevance = await evaluate_dental_relevance(
        request.image_base64,
        request.image_mime_type,
        gateway=gateway,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    # Safe-by-construction: never log image bytes, prompts, keys, or payload.
    logger.info(
        "[RELEVANCE] classification=%s action=%s confidence=%.2f scan_mode=scan duration_ms=%d",
        relevance.classification,
        relevance.recommended_action,
        relevance.confidence,
        elapsed_ms,
    )

    info = _relevance_info(relevance)

    if relevance.recommended_action == "continue":
        result = await run_teeth_analysis_pipeline(request)
        return ScanOutcome(
            status="analyzed",
            relevance=info,
            analysis=result.analysis,
            diagnosis=result.diagnosis,
        )
    if relevance.classification == "retake":
        return ScanOutcome(status="retake", relevance=info)
    return ScanOutcome(status="rejected", relevance=info)


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
