"""Tests for the Semantic Dental Relevance core (Phase 2B.1).

Fake gateways and in-memory providers only: ZERO external Qwen/Gemini calls,
no real images, no network, no database.
"""

from __future__ import annotations

import asyncio
import inspect
import logging

import pytest

from orchestrator.ai import AIGateway
from orchestrator.ai.base import AIProvider
from orchestrator.ai.exceptions import (
    AllProvidersFailedError,
    ProviderConfigurationError,
    ProviderInternalError,
    ProviderServerError,
    StructuredOutputError,
)
from orchestrator.ai.schemas import AIResult, StructuredRequest, TextRequest, VisionRequest
from orchestrator.clinical import relevance
from orchestrator.clinical.relevance import (
    RELEVANCE_PROMPT,
    DentalRelevanceResult,
    evaluate_dental_relevance,
)

# A recognizable stand-in for image bytes; must never leak anywhere.
FAKE_IMAGE_B64 = "SU1BR0VfQkFTRTY0X1NFbnRpbmVsX1NVQ0hfQVNGM0tFMg=="


def _run(coro):
    return asyncio.run(coro)


def _payload(
    classification: str,
    *,
    confidence: float = 0.9,
    relevance_score: float = 0.9,
    visible_regions: list[str] | None = None,
    reason: str = "ok",
    retake_reason: str | None = None,
) -> dict:
    return {
        "classification": classification,
        "confidence": confidence,
        "relevance_score": relevance_score,
        "visible_regions": visible_regions if visible_regions is not None else ["teeth"],
        "reason": reason,
        "retake_reason": retake_reason,
    }


class StructuredProvider(AIProvider):
    """In-memory adapter returning a canned structured payload or typed error."""

    def __init__(self, name: str, *, data: dict | None = None, failure: Exception | None = None) -> None:
        self.name = name
        self.default_model = f"{name}-configured-model"
        self.data = data
        self.failure = failure
        self.requests: list[StructuredRequest] = []

    async def generate_text(self, request: TextRequest) -> AIResult:  # pragma: no cover
        raise NotImplementedError

    async def generate_vision(self, request: VisionRequest) -> AIResult:  # pragma: no cover
        raise NotImplementedError

    async def generate_structured(self, request: StructuredRequest) -> AIResult:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return AIResult(content="{}", provider=self.name, model=self.default_model, data=self.data)


class SpyGateway:
    """Stands in for ``AIGateway`` so tests can inspect the request directly."""

    def __init__(self, result: AIResult | None = None, failure: Exception | None = None) -> None:
        self.result = result or AIResult(content="{}", provider="qwen", data=_payload("relevant"))
        self.failure = failure
        self.requests: list[StructuredRequest] = []

    async def generate_structured(self, request: StructuredRequest) -> AIResult:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return self.result


def _gateway_result(data: dict) -> AIResult:
    return AIResult(content="{}", provider="qwen", model="qwen3.7-plus", data=data)


# ---------------------------------------------------------------------------
# 1-3. Relevant images (teeth, gums/oral, external jaw swelling) -> continue
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("payload", "regions"),
    [
        (_payload("relevant", visible_regions=["teeth", "upper_arch"]), ["teeth", "upper_arch"]),
        (_payload("relevant", visible_regions=["gums", "oral_cavity"]), ["gums", "oral_cavity"]),
        (_payload("relevant", visible_regions=["cheek", "jaw_swelling"], reason="External jaw swelling"), ["cheek", "jaw_swelling"]),
    ],
)
def test_relevant_images_continue(payload, regions):
    gateway = SpyGateway(result=_gateway_result(payload))
    out = _run(evaluate_dental_relevance(FAKE_IMAGE_B64, "image/jpeg", gateway=gateway))

    assert out.classification == "relevant"
    assert out.is_dental_relevant is True
    assert out.recommended_action == "continue"
    assert out.visible_regions == regions


# ---------------------------------------------------------------------------
# 4. Insufficient mouth view -> retake
# ---------------------------------------------------------------------------
def test_retake_classification():
    payload = _payload("retake", confidence=0.7, relevance_score=0.4, retake_reason="mouth_too_far")
    gateway = SpyGateway(result=_gateway_result(payload))
    out = _run(evaluate_dental_relevance(FAKE_IMAGE_B64, "image/jpeg", gateway=gateway))

    assert out.classification == "retake"
    assert out.recommended_action == "retake"
    assert out.is_dental_relevant is False
    assert out.retake_reason == "mouth_too_far"


# ---------------------------------------------------------------------------
# 5-6. Unrelated images (object, body) -> reject
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "regions",
    [["laptop"], ["arm"]],
)
def test_unrelated_images_reject(regions):
    payload = _payload("unrelated", confidence=0.95, relevance_score=0.05, visible_regions=regions)
    gateway = SpyGateway(result=_gateway_result(payload))
    out = _run(evaluate_dental_relevance(FAKE_IMAGE_B64, "image/png", gateway=gateway))

    assert out.classification == "unrelated"
    assert out.recommended_action == "reject"
    assert out.is_dental_relevant is False


# ---------------------------------------------------------------------------
# 7. Deterministic action mapping (model-proposed action is ignored)
# ---------------------------------------------------------------------------
def test_action_mapping_is_deterministic():
    for classification, expected in [("relevant", "continue"), ("retake", "retake"), ("unrelated", "reject")]:
        data = _payload(classification)
        # Even a rogue "recommended_action" from the model cannot override mapping.
        data["recommended_action"] = "reject" if expected != "reject" else "continue"
        gateway = SpyGateway(result=_gateway_result(data))
        out = _run(evaluate_dental_relevance(FAKE_IMAGE_B64, "image/jpeg", gateway=gateway))
        assert out.recommended_action == expected


# ---------------------------------------------------------------------------
# 8. Structured result validation
# ---------------------------------------------------------------------------
def test_structured_result_schema():
    gateway = SpyGateway(result=_gateway_result(_payload("relevant")))
    out = _run(evaluate_dental_relevance(FAKE_IMAGE_B64, "image/jpeg", gateway=gateway))

    assert isinstance(out, DentalRelevanceResult)
    assert 0.0 <= out.confidence <= 1.0
    assert 0.0 <= out.relevance_score <= 1.0
    assert isinstance(out.visible_regions, list)

    # Out-of-classification model output is a structured-output error, not "unrelated".
    bad = SpyGateway(result=_gateway_result(_payload("probably_relevant")))
    with pytest.raises(StructuredOutputError):
        _run(evaluate_dental_relevance(FAKE_IMAGE_B64, "image/jpeg", gateway=bad))

    # Missing payload is also a structured-output error.
    empty = SpyGateway(result=AIResult(content="", provider="qwen", data=None))
    with pytest.raises(StructuredOutputError):
        _run(evaluate_dental_relevance(FAKE_IMAGE_B64, "image/jpeg", gateway=empty))


# ---------------------------------------------------------------------------
# 9. Provider failure propagates (never becomes "unrelated")
# ---------------------------------------------------------------------------
def test_technical_failure_propagates_not_unrelated():
    qwen = StructuredProvider("qwen", failure=ProviderServerError("Qwen HTTP 503"))
    gemini = StructuredProvider("gemini", failure=ProviderServerError("Gemini HTTP 500"))
    gateway = AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5)

    with pytest.raises(AllProvidersFailedError):
        _run(evaluate_dental_relevance(FAKE_IMAGE_B64, "image/jpeg", gateway=gateway))


def test_qwen_failure_falls_back_to_gemini():
    qwen = StructuredProvider("qwen", failure=ProviderServerError("Qwen HTTP 503"))
    gemini = StructuredProvider("gemini", data=_payload("relevant"))
    gateway = AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5)

    out = _run(evaluate_dental_relevance(FAKE_IMAGE_B64, "image/jpeg", gateway=gateway))

    assert out.classification == "relevant"
    assert qwen.requests and gemini.requests
    assert gemini.requests[0].model is None  # provider resolves GEMINI_MODEL itself


# ---------------------------------------------------------------------------
# 10. Config / internal / structured errors propagate unchanged
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "error",
    [
        ProviderConfigurationError("QWEN_API_KEY missing"),
        ProviderInternalError("bug in request construction"),
        StructuredOutputError("provider JSON invalid"),
    ],
)
def test_non_fallback_errors_propagate(error):
    gateway = SpyGateway(failure=error)
    with pytest.raises(type(error)):
        _run(evaluate_dental_relevance(FAKE_IMAGE_B64, "image/jpeg", gateway=gateway))


# ---------------------------------------------------------------------------
# 11. Base64 never leaks into logs or error representations
# ---------------------------------------------------------------------------
def test_image_base64_does_not_leak(caplog):
    gateway = SpyGateway(failure=ProviderServerError("upstream rejected request"))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ProviderServerError) as excinfo:
            _run(evaluate_dental_relevance(FAKE_IMAGE_B64, "image/jpeg", gateway=gateway))

    assert FAKE_IMAGE_B64 not in str(excinfo.value)
    assert FAKE_IMAGE_B64 not in repr(excinfo.value)
    assert FAKE_IMAGE_B64 not in caplog.text


def test_successful_path_logs_no_image_data(caplog):
    gateway = SpyGateway(result=_gateway_result(_payload("relevant")))
    with caplog.at_level(logging.DEBUG):
        _run(evaluate_dental_relevance(FAKE_IMAGE_B64, "image/jpeg", gateway=gateway))

    assert FAKE_IMAGE_B64 not in caplog.text


# ---------------------------------------------------------------------------
# 12. Service depends on AIGateway only, never a concrete provider
# ---------------------------------------------------------------------------
def test_service_is_provider_neutral():
    source = inspect.getsource(relevance)
    assert "QwenProvider" not in source
    assert "GeminiProvider" not in source
    assert "get_ai_gateway" in source  # lazy shared gateway when none injected


def test_gateway_request_contract():
    gateway = SpyGateway(result=_gateway_result(_payload("relevant")))
    _run(evaluate_dental_relevance(FAKE_IMAGE_B64, "image/webp", gateway=gateway))

    request = gateway.requests[0]
    assert isinstance(request, StructuredRequest)
    assert request.image_base64 == FAKE_IMAGE_B64
    assert request.content_type == "image/webp"
    assert request.model is None
    assert request.json_schema["properties"]["classification"]["enum"] == ["relevant", "retake", "unrelated"]


# ---------------------------------------------------------------------------
# 13-14. Prompt rules
# ---------------------------------------------------------------------------
def test_prompt_includes_jaw_cheek_swelling_rule():
    lowered = RELEVANCE_PROMPT.lower()
    assert "swelling" in lowered
    assert "jaw" in lowered and "cheek" in lowered
    assert "do not need to be" in lowered.replace("'", "")  # teeth not mandatory


def test_prompt_prohibits_diagnosis_and_treatment():
    lowered = RELEVANCE_PROMPT.lower()
    assert "do not diagnose" in lowered
    assert "treatment advice" in lowered
