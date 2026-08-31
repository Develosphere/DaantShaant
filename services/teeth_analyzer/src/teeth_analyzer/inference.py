"""
Vision inference: OpenCV preprocess → Gemini/OpenRouter (or stub) → VisualFinding[].
"""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from dantshaant_common.schemas import AnalyzeRequest, AnalyzeResponse

from teeth_analyzer.backends.gemini import analyze_with_gemini
from teeth_analyzer.backends.openrouter import analyze_with_openrouter
from teeth_analyzer.backends.stub import analyze_with_stub
from teeth_analyzer.config import settings
from teeth_analyzer.preprocess import preprocess_frame

logger = logging.getLogger(__name__)


class ImageQualityError(ValueError):
    def __init__(self, hint: str, quality_score: float) -> None:
        super().__init__(hint)
        self.hint = hint
        self.quality_score = quality_score


class VisionBackendError(RuntimeError):
    pass


def _run_vision(jpeg_bytes: bytes, locale: str) -> tuple[list, str]:
    backend = settings.backend.lower()
    
    if backend == "gemini":
        try:
            findings = analyze_with_gemini(jpeg_bytes, locale)
            return findings, settings.gemini_model
        except Exception as exc:
            logger.exception("Gemini vision failed: %s", exc)
            if settings.fallback_to_stub:
                logger.warning("Falling back to stub (disable TEETH_ANALYZER_FALLBACK_TO_STUB)")
                return analyze_with_stub(jpeg_bytes, locale), "stub-fallback"
            raise VisionBackendError(
                f"Gemini vision failed: {exc}. "
                "Check API key, model name, and billing. "
                "Set TEETH_ANALYZER_FALLBACK_TO_STUB=true only for offline dev."
            ) from exc
    
    elif backend == "openrouter":
        try:
            findings = analyze_with_openrouter(jpeg_bytes, locale)
            return findings, settings.openrouter_model
        except Exception as exc:
            logger.exception("OpenRouter vision failed: %s", exc)
            if settings.fallback_to_stub:
                logger.warning("Falling back to stub (disable TEETH_ANALYZER_FALLBACK_TO_STUB)")
                return analyze_with_stub(jpeg_bytes, locale), "stub-fallback"
            raise VisionBackendError(
                f"OpenRouter vision failed: {exc}. "
                "Check API key and model name. "
                "Set TEETH_ANALYZER_FALLBACK_TO_STUB=true only for offline dev."
            ) from exc
    
    return analyze_with_stub(jpeg_bytes, locale), settings.model_id


def analyze_image(request: AnalyzeRequest) -> AnalyzeResponse:
    start = time.perf_counter()
    pre = preprocess_frame(request.image_base64)

    if not pre.passed_gate and settings.reject_low_quality:
        raise ImageQualityError(pre.hint or "Low image quality", pre.quality_score)

    findings, model_id = _run_vision(pre.jpeg_bytes, request.locale)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return AnalyzeResponse(
        analysis_id=uuid4(),
        user_id=request.user_id,
        findings=findings,
        overall_quality_score=pre.quality_score,
        model_id=model_id,
        inference_ms=elapsed_ms,
    )
