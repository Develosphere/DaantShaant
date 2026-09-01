"""Compose Teeth Analyzer → Diagnosis (MCP analyze_teeth_image flow)."""

import httpx
from pydantic import BaseModel
from uuid import UUID

from dantshaant_common.clients import DiagnosisClient, TeethAnalyzerClient
from dantshaant_common.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    DiagnoseRequest,
    DiagnoseResponse,
)
from orchestrator.config import settings


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
