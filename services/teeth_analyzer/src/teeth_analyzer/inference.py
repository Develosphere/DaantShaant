"""Vision inference: OpenCV preprocess -> Qwen primary / Gemini fallback clinical
vision -> VisualFinding[] (Phase 2C).

The mechanical-quality gate is preserved exactly: a low-quality image is
rejected BEFORE any AI clinical-vision call. Clinical vision now runs through
the service-local provider policy (Qwen primary, Gemini technical fallback);
the legacy third-party router backend has been removed.
"""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from dantshaant_common.schemas import AnalyzeRequest, AnalyzeResponse

from teeth_analyzer.backends.errors import AllProvidersFailedError, ClinicalVisionError
from teeth_analyzer.backends.stub import analyze_with_stub
from teeth_analyzer.config import settings
from teeth_analyzer.preprocess import preprocess_frame
from teeth_analyzer.provider_policy import run_clinical_vision

logger = logging.getLogger(__name__)


class ImageQualityError(ValueError):
    def __init__(self, hint: str, quality_score: float) -> None:
        super().__init__(hint)
        self.hint = hint
        self.quality_score = quality_score


class VisionBackendError(RuntimeError):
    pass


async def analyze_image(request: AnalyzeRequest) -> AnalyzeResponse:
    start = time.perf_counter()
    pre = preprocess_frame(request.image_base64)

    # Mechanical-quality gate: reject BEFORE calling Qwen/Gemini. A quality
    # rejection is distinct from semantic-relevance rejection and from a
    # clinical finding.
    if not pre.passed_gate and settings.reject_low_quality:
        raise ImageQualityError(pre.hint or "Low image quality", pre.quality_score)

    if settings.backend.lower() == "stub":
        # Offline/dev deterministic backend - no AI call.
        findings = analyze_with_stub(pre.jpeg_bytes, request.locale)
        model_id = settings.model_id
    else:
        try:
            outcome = await run_clinical_vision(pre.jpeg_bytes, request.locale)
            findings, model_id = outcome.findings, outcome.model
        except AllProvidersFailedError as exc:
            # Both providers failed technically. Only an explicit offline-dev
            # opt-in degrades to the stub; otherwise surface a backend error.
            if settings.fallback_to_stub:
                logger.warning(
                    "Clinical vision providers failed; using offline stub "
                    "(disable TEETH_ANALYZER_FALLBACK_TO_STUB in production)"
                )
                findings = analyze_with_stub(pre.jpeg_bytes, request.locale)
                model_id = "stub-fallback"
            else:
                raise VisionBackendError(f"Clinical vision failed on all providers: {exc}") from exc
        except ClinicalVisionError as exc:
            # Configuration / programming errors propagate (never masked by stub).
            raise VisionBackendError(str(exc)) from exc

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return AnalyzeResponse(
        analysis_id=uuid4(),
        user_id=request.user_id,
        findings=findings,
        overall_quality_score=pre.quality_score,
        model_id=model_id,
        inference_ms=elapsed_ms,
    )
