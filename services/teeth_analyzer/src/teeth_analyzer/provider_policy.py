"""Clinical-vision provider policy for the Teeth Analyzer (Phase 2C).

Locked policy, implemented SERVICE-LOCAL (no orchestrator HTTP call, no circular
dependency):

    Qwen PRIMARY  ->  (technical failure only)  ->  Gemini FALLBACK

- Technical failures (timeout, connection, 429, 5xx, malformed envelope) on Qwen
  trigger a single attempt on Gemini.
- Configuration / programming errors on Qwen propagate immediately and are NEVER
  masked by fallback or by the offline stub.
- If both providers fail technically, ``AllProvidersFailedError`` is raised.

Both providers return the SAME normalized internal result, so the caller never
needs to know which provider responded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from dantshaant_common.schemas import VisualFinding

from teeth_analyzer.backends import gemini as gemini_backend
from teeth_analyzer.backends import qwen as qwen_backend
from teeth_analyzer.backends.errors import AllProvidersFailedError, ClinicalVisionError

logger = logging.getLogger(__name__)


@dataclass
class ClinicalVisionOutcome:
    """Provider-neutral clinical-vision result."""

    findings: list[VisualFinding]
    provider: str
    model: str
    latency_ms: float
    fallback_used: bool = False


async def run_clinical_vision(jpeg_bytes: bytes, locale: str) -> ClinicalVisionOutcome:
    """Run Qwen primary, falling back to Gemini on technical failure only."""
    errors: dict[str, Exception] = {}

    # --- PRIMARY: Qwen ---
    try:
        findings, model, latency = await qwen_backend.analyze_with_qwen(jpeg_bytes, locale)
        logger.info(
            "[CLINICAL_VISION] provider=qwen model=%s fallback_used=false latency_ms=%s",
            model,
            latency,
        )
        return ClinicalVisionOutcome(
            findings=findings, provider="qwen", model=model, latency_ms=latency, fallback_used=False
        )
    except ClinicalVisionError as exc:
        if not exc.fallback_eligible:
            # Configuration / programming error: surface it, never fall back.
            logger.warning(
                "[CLINICAL_VISION] provider=qwen non-fallback error: %s", type(exc).__name__
            )
            raise
        errors["qwen"] = exc
        logger.warning(
            "[CLINICAL_VISION] qwen technical failure (%s); trying Gemini fallback",
            type(exc).__name__,
        )

    # --- FALLBACK: Gemini (reached only after a Qwen technical failure) ---
    try:
        findings, model, latency = await gemini_backend.analyze_with_gemini(jpeg_bytes, locale)
        logger.info(
            "[CLINICAL_VISION] provider=gemini model=%s fallback_used=true latency_ms=%s",
            model,
            latency,
        )
        return ClinicalVisionOutcome(
            findings=findings, provider="gemini", model=model, latency_ms=latency, fallback_used=True
        )
    except ClinicalVisionError as exc:
        errors["gemini"] = exc
        if not exc.fallback_eligible:
            # e.g. Gemini not configured - surface the real cause, do not mask it.
            logger.warning(
                "[CLINICAL_VISION] provider=gemini non-fallback error: %s", type(exc).__name__
            )
            raise
        logger.error(
            "[CLINICAL_VISION] gemini fallback also failed (%s)", type(exc).__name__
        )

    raise AllProvidersFailedError("Clinical vision failed on both Qwen and Gemini", errors)


__all__ = ["ClinicalVisionOutcome", "run_clinical_vision"]
