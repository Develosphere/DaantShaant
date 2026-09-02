"""Phase 2C - Qwen clinical vision (primary) + Gemini fallback tests.

ZERO real AI calls: Qwen/Gemini HTTP is exercised with ``httpx.MockTransport``
or replaced with fakes; the mechanical-quality gate is stubbed so no OpenCV /
real image decoding runs. Tiny fake bytes stand in for an image.
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import inspect
import json
import logging
import uuid
from types import SimpleNamespace

import httpx
import pytest

from dantshaant_common.schemas import AnalyzeRequest, AnalyzeResponse, VisualFinding

from teeth_analyzer import inference, provider_policy
from teeth_analyzer.backends import gemini as gemini_backend
from teeth_analyzer.backends import qwen as qwen_backend
from teeth_analyzer.backends import vision_common
from teeth_analyzer.backends.errors import (
    InvalidProviderResponseError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from teeth_analyzer.provider_policy import ClinicalVisionOutcome, run_clinical_vision

FAKE_JPEG = b"\xff\xd8\xff\xe0FAKEJPEGBYTES"
FAKE_B64 = base64.b64encode(FAKE_JPEG).decode()


def _run(coro):
    return asyncio.run(coro)


def _structured() -> dict:
    return {
        "oral_regions_visible": ["teeth", "gums"],
        "findings": [
            {
                "finding_code": "plaque_detected",
                "observation": "visible plaque film",
                "region": "lower_anterior",
                "tooth_reference": None,
                "confidence": 0.6,
                "visibility": "clear",
            },
            {
                "finding_code": "cavity_suspect",
                "observation": "dark spot possibly consistent with early decay",
                "region": "upper_right",
                "tooth_reference": None,
                "confidence": 0.4,
                "visibility": "partial",
            },
        ],
        "overall_observation": "plaque with a possible early cavity",
        "limitations": ["limited lighting"],
    }


def _qwen_body(content: dict | None = None) -> dict:
    return {
        "choices": [{"message": {"content": json.dumps(content or _structured())}}],
        "model": "qwen3.7-plus",
    }


def _gemini_body(content: dict | None = None) -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": json.dumps(content or _structured())}]}}],
        "modelVersion": "gemini-flash-lite-latest",
    }


def _patch_qwen(monkeypatch, *, key="sk-test-dashscope", base="https://qwen.test/compatible-mode/v1", model="qwen3.7-plus"):
    monkeypatch.setattr(qwen_backend.settings, "dashscope_api_key", key)
    monkeypatch.setattr(qwen_backend.settings, "qwen_base_url", base)
    monkeypatch.setattr(qwen_backend.settings, "qwen_vision_model", model)
    monkeypatch.setattr(qwen_backend.settings, "ai_request_timeout_seconds", 5.0)


def _patch_gemini(monkeypatch, *, key="gem-test-key", model="gemini-flash-lite-latest"):
    monkeypatch.setattr(gemini_backend.settings, "gemini_api_key", key)
    monkeypatch.setattr(gemini_backend.settings, "gemini_model", model)
    monkeypatch.setattr(gemini_backend.settings, "gemini_base_url", "")
    monkeypatch.setattr(gemini_backend.settings, "ai_request_timeout_seconds", 5.0)


# ---------------------------------------------------------------------------
# 1-4. Qwen primary backend
# ---------------------------------------------------------------------------
def test_1_qwen_vision_success(monkeypatch):
    _patch_qwen(monkeypatch)

    def handler(request):
        return httpx.Response(200, json=_qwen_body())

    findings, model, latency = _run(
        qwen_backend.analyze_with_qwen(FAKE_JPEG, "en", transport=httpx.MockTransport(handler))
    )
    assert model == "qwen3.7-plus"
    assert isinstance(latency, float)
    assert [f.label for f in findings] == ["plaque_detected", "cavity_suspect"]
    assert findings[0].confidence == 0.6
    assert findings[0].region == "lower_anterior"


def test_2_qwen_multimodal_payload_correct(monkeypatch):
    _patch_qwen(monkeypatch, key="sk-secret-key")
    captured = {}

    def handler(request):
        captured["req"] = request
        return httpx.Response(200, json=_qwen_body())

    _run(qwen_backend.analyze_with_qwen(FAKE_JPEG, "en", transport=httpx.MockTransport(handler)))
    req = captured["req"]
    assert str(req.url).endswith("/chat/completions")
    assert req.headers["authorization"] == "Bearer sk-secret-key"
    body = json.loads(req.content)
    content = body["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == f"data:image/jpeg;base64,{FAKE_B64}"


def test_3_qwen_uses_configured_vision_model(monkeypatch):
    _patch_qwen(monkeypatch, model="qwen-custom-vision")
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_qwen_body())

    _, model, _ = _run(
        qwen_backend.analyze_with_qwen(FAKE_JPEG, "en", transport=httpx.MockTransport(handler))
    )
    assert captured["body"]["model"] == "qwen-custom-vision"
    assert model == "qwen-custom-vision"


def test_4_qwen_structured_result_normalized():
    findings = vision_common.parse_findings(json.dumps(_structured()))
    assert [f.label for f in findings] == ["plaque_detected", "cavity_suspect"]
    # Legacy simple shape still parses.
    legacy = json.dumps({"findings": [{"label": "Tartar", "confidence": 0.7, "region": "gums"}]})
    assert vision_common.parse_findings(legacy)[0].label == "tartar"
    # Markdown fences tolerated.
    fenced = "```json\n" + json.dumps(_structured()) + "\n```"
    assert vision_common.parse_findings(fenced)[0].label == "plaque_detected"
    # Confidence clamped to [0, 1].
    clamped = vision_common.parse_findings(json.dumps({"findings": [{"finding_code": "x", "confidence": 5}]}))
    assert clamped[0].confidence == 1.0
    # Unparseable output degrades to a single low-confidence 'unknown'.
    assert vision_common.parse_findings("not json")[0].label == "unknown"


# ---------------------------------------------------------------------------
# 5-10. Policy: Qwen primary -> Gemini technical fallback
# ---------------------------------------------------------------------------
def _install_policy_fakes(monkeypatch, *, qwen_error=None, qwen_result=None, gemini_error=None):
    calls = {"qwen": 0, "gemini": 0}

    async def fake_qwen(jpeg, locale, **kw):
        calls["qwen"] += 1
        if qwen_error is not None:
            raise qwen_error
        return qwen_result or ([VisualFinding(label="healthy_tissue", confidence=0.9, region="general")], "qwen3.7-plus", 4.0)

    async def fake_gemini(jpeg, locale, **kw):
        calls["gemini"] += 1
        if gemini_error is not None:
            raise gemini_error
        return ([VisualFinding(label="plaque_detected", confidence=0.5, region="gums")], "gemini-flash-lite-latest", 6.0)

    monkeypatch.setattr(provider_policy.qwen_backend, "analyze_with_qwen", fake_qwen)
    monkeypatch.setattr(provider_policy.gemini_backend, "analyze_with_gemini", fake_gemini)
    return calls


def test_5_gemini_fallback_on_qwen_technical_failure(monkeypatch):
    calls = _install_policy_fakes(monkeypatch, qwen_error=ProviderServerError("Qwen HTTP 503"))
    out = _run(run_clinical_vision(FAKE_JPEG, "en"))
    assert out.provider == "gemini" and out.fallback_used is True
    assert calls == {"qwen": 1, "gemini": 1}


def test_6_no_fallback_on_qwen_configuration_error(monkeypatch):
    calls = _install_policy_fakes(monkeypatch, qwen_error=ProviderConfigurationError("DASHSCOPE_API_KEY missing"))
    with pytest.raises(ProviderConfigurationError):
        _run(run_clinical_vision(FAKE_JPEG, "en"))
    assert calls["gemini"] == 0  # never fell back on a config error


@pytest.mark.parametrize(
    "error",
    [
        ProviderRateLimitError("429"),      # 7
        ProviderServerError("503"),         # 8
        ProviderTimeoutError("timeout"),    # 9
        InvalidProviderResponseError("bad envelope"),  # 10
    ],
)
def test_7_10_technical_failures_trigger_fallback(monkeypatch, error):
    calls = _install_policy_fakes(monkeypatch, qwen_error=error)
    out = _run(run_clinical_vision(FAKE_JPEG, "en"))
    assert out.provider == "gemini" and out.fallback_used is True
    assert calls["gemini"] == 1


def test_qwen_success_does_not_call_gemini(monkeypatch):
    calls = _install_policy_fakes(monkeypatch)
    out = _run(run_clinical_vision(FAKE_JPEG, "en"))
    assert out.provider == "qwen" and out.fallback_used is False
    assert calls == {"qwen": 1, "gemini": 0}


def test_backend_http_error_mapping(monkeypatch):
    _patch_qwen(monkeypatch)

    def make(status):
        def handler(request):
            return httpx.Response(status, text='{"error":"boom"}')
        return httpx.MockTransport(handler)

    with pytest.raises(ProviderRateLimitError):
        _run(qwen_backend.analyze_with_qwen(FAKE_JPEG, "en", transport=make(429)))
    with pytest.raises(ProviderServerError):
        _run(qwen_backend.analyze_with_qwen(FAKE_JPEG, "en", transport=make(503)))
    with pytest.raises(ProviderConfigurationError):
        _run(qwen_backend.analyze_with_qwen(FAKE_JPEG, "en", transport=make(401)))

    # Malformed 200 envelope (no choices) is a technical invalid-response error.
    def bad_envelope(request):
        return httpx.Response(200, json={"unexpected": True})

    with pytest.raises(InvalidProviderResponseError):
        _run(qwen_backend.analyze_with_qwen(FAKE_JPEG, "en", transport=httpx.MockTransport(bad_envelope)))

    # Transport-level failures map to timeout / unavailable.
    def timeout(request):
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(ProviderTimeoutError):
        _run(qwen_backend.analyze_with_qwen(FAKE_JPEG, "en", transport=httpx.MockTransport(timeout)))

    def connect_error(request):
        raise httpx.ConnectError("dns failure")

    with pytest.raises(ProviderUnavailableError):
        _run(qwen_backend.analyze_with_qwen(FAKE_JPEG, "en", transport=httpx.MockTransport(connect_error)))


def test_gemini_backend_success_and_mapping(monkeypatch):
    _patch_gemini(monkeypatch)

    def ok(request):
        assert request.headers["x-goog-api-key"] == "gem-test-key"
        assert str(request.url).endswith(":generateContent")
        return httpx.Response(200, json=_gemini_body())

    findings, model, _ = _run(
        gemini_backend.analyze_with_gemini(FAKE_JPEG, "en", transport=httpx.MockTransport(ok))
    )
    assert model == "gemini-flash-lite-latest"
    assert [f.label for f in findings] == ["plaque_detected", "cavity_suspect"]

    def bad(request):
        return httpx.Response(400, text='{"error":"bad key"}')

    with pytest.raises(ProviderConfigurationError):
        _run(gemini_backend.analyze_with_gemini(FAKE_JPEG, "en", transport=httpx.MockTransport(bad)))


# ---------------------------------------------------------------------------
# 11. No base64 / key leakage
# ---------------------------------------------------------------------------
def test_11_base64_and_key_not_leaked(monkeypatch, caplog):
    _patch_qwen(monkeypatch, key="sk-super-secret")

    def handler(request):
        # Server echoes the key so we can prove it is redacted from errors.
        return httpx.Response(500, text='{"error":"invalid key sk-super-secret"}')

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ProviderServerError) as ei:
            _run(qwen_backend.analyze_with_qwen(FAKE_JPEG, "en", transport=httpx.MockTransport(handler)))

    msg = str(ei.value)
    assert FAKE_B64 not in msg
    assert "sk-super-secret" not in msg
    assert FAKE_B64 not in caplog.text
    assert "sk-super-secret" not in caplog.text


# ---------------------------------------------------------------------------
# 12-15. Inference integration
# ---------------------------------------------------------------------------
def _good_pre():
    return SimpleNamespace(
        jpeg_bytes=b"x", quality_score=0.9, passed_gate=True, hint=None, blur_variance=200.0, brightness=0.6
    )


def _bad_pre():
    return SimpleNamespace(
        jpeg_bytes=b"x", quality_score=0.2, passed_gate=False, hint="too blurry", blur_variance=1.0, brightness=0.1
    )


def test_12_quality_rejection_skips_ai(monkeypatch):
    called = {"vision": 0}

    async def fake_vision(jpeg, locale):
        called["vision"] += 1
        return ClinicalVisionOutcome(findings=[], provider="qwen", model="m", latency_ms=1.0)

    monkeypatch.setattr(inference, "run_clinical_vision", fake_vision)
    monkeypatch.setattr(inference, "preprocess_frame", lambda b64: _bad_pre())
    monkeypatch.setattr(inference.settings, "reject_low_quality", True)
    monkeypatch.setattr(inference.settings, "backend", "qwen")

    req = AnalyzeRequest(user_id=uuid.uuid4(), image_base64="anything")
    with pytest.raises(inference.ImageQualityError):
        _run(inference.analyze_image(req))
    assert called["vision"] == 0  # AI never called for a mechanical-quality reject


def test_13_structured_findings_become_downstream_labels():
    findings = vision_common.parse_findings(json.dumps(_structured()))
    assert all(isinstance(f, VisualFinding) for f in findings)
    assert [f.label for f in findings] == ["plaque_detected", "cavity_suspect"]


def test_14_no_definitive_diagnosis_field():
    assert "diagnosis" not in AnalyzeResponse.model_fields
    assert "condition_label" not in AnalyzeResponse.model_fields
    prompt = vision_common.CLINICAL_VISION_PROMPT.lower()
    assert "screening" in prompt
    assert "not a definitive diagnosis" in prompt
    assert "treatment" in prompt


def test_15_provider_metadata_does_not_break_public_response(monkeypatch):
    async def fake_vision(jpeg, locale):
        return ClinicalVisionOutcome(
            findings=[VisualFinding(label="plaque_detected", confidence=0.6, region="gums")],
            provider="qwen",
            model="qwen3.7-plus",
            latency_ms=12.0,
            fallback_used=False,
        )

    monkeypatch.setattr(inference, "run_clinical_vision", fake_vision)
    monkeypatch.setattr(inference, "preprocess_frame", lambda b64: _good_pre())
    monkeypatch.setattr(inference.settings, "backend", "qwen")

    resp = _run(inference.analyze_image(AnalyzeRequest(user_id=uuid.uuid4(), image_base64="x")))
    assert isinstance(resp, AnalyzeResponse)
    assert resp.model_id == "qwen3.7-plus"
    assert resp.findings[0].label == "plaque_detected"
    dumped = resp.model_dump(mode="json")
    assert "provider" not in dumped  # provider metadata stays internal
    assert "fallback_used" not in dumped


# ---------------------------------------------------------------------------
# 16. OpenRouter fully removed from runtime
# ---------------------------------------------------------------------------
def test_16_openrouter_has_zero_runtime_callers():
    assert importlib.util.find_spec("teeth_analyzer.backends.openrouter") is None
    for mod in (inference, provider_policy, qwen_backend, gemini_backend, vision_common):
        source = inspect.getsource(mod).lower()
        assert "openrouter" not in source
        assert "analyze_with_openrouter" not in source
