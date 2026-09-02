"""Semantic Dental Relevance core (Phase 2B.1).

Answers exactly one question about an image:

    "Is this image semantically relevant enough for dental/oral screening?"

It is deliberately distinct from mechanical image-quality checks, clinical
vision findings, and diagnosis/triage.  Three classifications are supported:

- ``relevant``  - usable oral/dental content (teeth, gums, oral cavity, or an
  external jaw/cheek swelling plausibly related to a dental concern; teeth do
  NOT need to be visible in every relevant image)
- ``retake``    - the oral region appears intended but visibility is inadequate
- ``unrelated`` - no meaningful dental/oral relevance

The request goes through the shared provider-neutral ``AIGateway``
(Qwen primary -> Gemini technical fallback) via ``StructuredRequest``.
Provider failures propagate as typed gateway errors and are NEVER converted
into an ``unrelated`` classification.  Image base64 is never logged,
persisted, or embedded in errors.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from orchestrator.ai.exceptions import StructuredOutputError
from orchestrator.ai.factory import get_ai_gateway
from orchestrator.ai.gateway import AIGateway
from orchestrator.ai.schemas import StructuredRequest

logger = logging.getLogger(__name__)

RelevanceClassification = Literal["relevant", "retake", "unrelated"]
RecommendedAction = Literal["continue", "retake", "reject"]

#: Deterministic action mapping - no arbitrary confidence thresholds.
_ACTION_BY_CLASSIFICATION: dict[str, RecommendedAction] = {
    "relevant": "continue",
    "retake": "retake",
    "unrelated": "reject",
}


class DentalRelevanceResult(BaseModel):
    """Normalized semantic-relevance outcome for one image."""

    classification: RelevanceClassification
    #: Derived deterministically from ``classification`` below; a model may
    #: omit these two fields and any model-supplied values are overridden.
    is_dental_relevant: bool = False
    confidence: float = Field(..., ge=0.0, le=1.0)
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    visible_regions: list[str] = Field(default_factory=list)
    reason: str = ""
    retake_reason: str | None = None
    recommended_action: RecommendedAction = "reject"

    @field_validator("confidence", "relevance_score", mode="before")
    @classmethod
    def _clamp_score(cls, value: Any) -> float:
        """Tolerate minor model drift without changing semantics."""
        try:
            return min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            return value  # let pydantic raise a clean validation error


RELEVANCE_PROMPT = """\
Classify this image for dental/oral screening relevance as exactly one of:
"relevant", "retake", or "unrelated".

Rules:
- "relevant": visible teeth, gums, oral cavity, mouth/dental close-up, mouth \
injury, clinically relevant lips/oral region, or external cheek/jaw/facial \
swelling plausibly related to an oral/dental concern. Teeth do NOT need to be \
visible - external jaw/cheek swelling can still be relevant.
- "retake": the mouth/oral region appears intended, but the image is too far, \
obstructed, poorly framed, has insufficient oral visibility, or the angle is \
wrong for useful screening.
- "unrelated": objects, rooms, food, documents, landscapes, unrelated body \
parts, or an ordinary face selfie with no meaningful mouth/jaw relevance.

Do NOT diagnose any disease or condition. Do NOT provide treatment advice. \
This is a relevance judgment only.
Return ONLY a JSON object matching the provided schema.\
"""

#: JSON schema the structured output must satisfy (validated by the gateway
#: providers and again by this service before returning).
RELEVANCE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "classification": {
            "type": "string",
            "enum": ["relevant", "retake", "unrelated"],
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "relevance_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "visible_regions": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
        "retake_reason": {"type": ["string", "null"]},
    },
    "required": ["classification", "confidence", "relevance_score", "visible_regions", "reason"],
}


async def evaluate_dental_relevance(
    image_base64: str,
    content_type: str,
    gateway: AIGateway | None = None,
) -> DentalRelevanceResult:
    """Judge whether an image is semantically suitable for dental screening.

    ``gateway`` is injectable for tests; application code may omit it and the
    shared production gateway (Qwen primary, Gemini fallback) is resolved
    lazily.  Technical/config/programming errors from the gateway propagate
    unchanged - a provider outage is never reported as ``unrelated``.
    """
    gw = gateway or get_ai_gateway()

    request = StructuredRequest(
        prompt=RELEVANCE_PROMPT,
        json_schema=RELEVANCE_JSON_SCHEMA,
        image_base64=image_base64,
        content_type=content_type,
        temperature=0.0,
        max_tokens=300,
        model=None,  # each provider resolves its own configured default
    )

    result = await gw.generate_structured(request)

    if not result.data:
        raise StructuredOutputError("Dental relevance: provider returned no structured JSON payload")

    try:
        parsed = DentalRelevanceResult.model_validate(result.data)
    except ValidationError as exc:
        # Unusable model output is a structured-output problem, never an
        # "unrelated" classification.  Field names only - no image data.
        raise StructuredOutputError(
            f"Dental relevance output failed schema validation: {exc.errors(include_url=False, include_input=False)}"
        ) from None

    normalized = parsed.model_copy(
        update={
            # Action is deterministic, never model-chosen.
            "recommended_action": _ACTION_BY_CLASSIFICATION[parsed.classification],
            # "relevant enough to proceed with screening" - retake is not.
            "is_dental_relevant": parsed.classification == "relevant",
        }
    )

    # Safe-by-construction logging: no image data, no payload dump.
    logger.info(
        "Dental relevance evaluated: classification=%s action=%s provider=%s model=%s fallback_used=%s",
        normalized.classification,
        normalized.recommended_action,
        result.provider,
        result.model,
        result.fallback_used,
    )
    return normalized


__all__ = [
    "DentalRelevanceResult",
    "RELEVANCE_PROMPT",
    "RELEVANCE_JSON_SCHEMA",
    "evaluate_dental_relevance",
]
