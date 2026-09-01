"""Unit tests for the Gemini provider adapter (Phase 2A.3).

These tests use ``httpx.MockTransport`` only and make ZERO real Google Gemini
API calls. They verify payload construction, response normalization, model
selection, error mapping, secret hygiene, and structured-output consistency
with the Qwen adapter. Async is driven with ``asyncio.run`` so no async pytest
plugin is required.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from orchestrator.ai import (
    AIGateway,
    AIResult,
    GeminiProvider,
    QwenProvider,
    StructuredRequest,
    TextRequest,
    VisionRequest,
)
from orchestrator.ai.exceptions import (
    InvalidProviderResponseError,
    ProviderConfigurationError,
    ProviderInternalError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    StructuredOutputError,
)

from orchestrator.config import AISettings

FAKE_KEY = "AIza-SECRET-NOT-A-REAL-KEY"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _content_body(text: str = "hi", *, model: str = "gemini-flash-lite-latest") -> dict:
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": text}], "role": "model"},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 5,
            "candidatesTokenCount": 2,
            "totalTokenCount": 7,
        },
        "modelVersion": model,
        "responseId": "resp-1",
    }


def _provider(
    handler,
    *,
    default_model: str | None = None,
    timeout: float = 5.0,
) -> GeminiProvider:
    return GeminiProvider(
        api_key=FAKE_KEY,
        base_url=BASE_URL,
        default_model=default_model or "gemini-flash-lite-latest",
        timeout_seconds=timeout,
        transport=httpx.MockTransport(handler),
    )


def _json_response(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


# ---------------------------------------------------------------------------
# Payload construction + normalization
# ---------------------------------------------------------------------------
def test_text_payload_and_api_key_header():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _json_response(_content_body("hello back"))

    provider = _provider(handler)
    result = asyncio.run(
        provider.generate_text(TextRequest(prompt="hi", temperature=0.3, max_tokens=64))
    )

    assert captured, "no HTTP request was issued"
    request = captured[0]
    assert request.url.path.endswith("/v1beta/models/gemini-flash-lite-latest:generateContent")
    # Key travels in a header, never in the query string.
    assert request.headers["x-goog-api-key"] == FAKE_KEY
    assert "key" not in request.url.query.decode()
    payload = json.loads(request.content.decode())
    assert payload["contents"] == [{"role": "user", "parts": [{"text": "hi"}]}]
    assert payload["generationConfig"]["temperature"] == 0.3
    assert payload["generationConfig"]["maxOutputTokens"] == 64
    assert "responseMimeType" not in payload["generationConfig"]
    assert result.content == "hello back"


def test_messages_map_roles_and_system_instruction():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _json_response(_content_body())

    provider = _provider(handler)
    asyncio.run(
        provider.generate_text(
            TextRequest(
                messages=[
                    {"role": "system", "content": "be brief"},
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "yo"},
                    {"role": "user", "content": "again"},
                ]
            )
        )
    )

    payload = json.loads(captured[0].content.decode())
    assert payload["systemInstruction"] == {"parts": [{"text": "be brief"}]}
    # assistant -> model, ordering preserved.
    assert payload["contents"] == [
        {"role": "user", "parts": [{"text": "hi"}]},
        {"role": "model", "parts": [{"text": "yo"}]},
        {"role": "user", "parts": [{"text": "again"}]},
    ]


def test_text_success_normalization():
    provider = _provider(lambda request: _json_response(_content_body("ok")))
    result = asyncio.run(provider.generate_text(TextRequest(prompt="hi")))

    assert isinstance(result, AIResult)
    assert result.provider == "gemini"
    assert result.model == "gemini-flash-lite-latest"
    assert result.finish_reason == "stop"
    assert result.usage is not None
    assert result.usage.prompt_tokens == 5
    assert result.usage.completion_tokens == 2
    assert result.usage.total_tokens == 7
    assert result.latency_ms >= 0.0
    assert result.raw_metadata == {"response_id": "resp-1"}
    assert result.fallback_used is False


def test_per_request_model_override():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _json_response(_content_body(model="gemini-pro"))

    provider = _provider(handler)
    result = asyncio.run(provider.generate_text(TextRequest(prompt="hi", model="gemini-pro")))

    assert captured[0].url.path.endswith("/models/gemini-pro:generateContent")
    assert result.model == "gemini-pro"


def test_vision_builds_inline_data():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _json_response(_content_body("teeth look fine"))

    provider = _provider(handler)
    result = asyncio.run(
        provider.generate_vision(
            VisionRequest(prompt="describe", image_base64="QUJD", content_type="image/png")
        )
    )

    payload = json.loads(captured[0].content.decode())
    parts = payload["contents"][0]["parts"]
    assert parts[0] == {"text": "describe"}
    assert parts[1]["inlineData"] == {"mimeType": "image/png", "data": "QUJD"}
    assert result.content == "teeth look fine"


def test_structured_success_sets_mime_and_data():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _json_response(_content_body('{"ok": true}'))

    provider = _provider(handler)
    result = asyncio.run(
        provider.generate_structured(
            StructuredRequest(prompt="give json", json_schema={"type": "object"})
        )
    )

    payload = json.loads(captured[0].content.decode())
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "JSON schema" in payload["contents"][0]["parts"][0]["text"]
    assert result.data == {"ok": True}


def test_structured_valid_object_passes_schema_validation():
    body = _content_body('{"name": "Alice", "age": 30}')
    provider = _provider(lambda request: _json_response(body))
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name", "age"],
    }
    result = asyncio.run(
        provider.generate_structured(StructuredRequest(prompt="give json", json_schema=schema))
    )
    assert result.data == {"name": "Alice", "age": 30}


def test_structured_missing_required_property_raises_structured_error():
    body = _content_body('{"name": "Alice"}')
    provider = _provider(lambda request: _json_response(body))
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name", "age"],
    }
    with pytest.raises(StructuredOutputError, match="does not match the requested schema"):
        asyncio.run(
            provider.generate_structured(StructuredRequest(prompt="give json", json_schema=schema))
        )


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------
def test_http_403_maps_to_configuration_error():
    provider = _provider(lambda request: _json_response({"error": "denied"}, status=403))
    with pytest.raises(ProviderConfigurationError) as exc_info:
        asyncio.run(provider.generate_text(TextRequest(prompt="hi")))
    assert FAKE_KEY not in str(exc_info.value)


def test_http_400_bad_key_maps_to_configuration_error():
    body = {"error": {"message": f"API key not valid. Pass as x-goog-api-key. {FAKE_KEY}"}}
    provider = _provider(lambda request: _json_response(body, status=400))
    with pytest.raises(ProviderConfigurationError) as exc_info:
        asyncio.run(provider.generate_text(TextRequest(prompt="hi")))
    # Even if echoed in the body, the key must be redacted.
    assert FAKE_KEY not in str(exc_info.value)


def test_http_429_maps_to_rate_limit():
    provider = _provider(lambda request: _json_response({"error": "slow down"}, status=429))
    with pytest.raises(ProviderRateLimitError):
        asyncio.run(provider.generate_text(TextRequest(prompt="hi")))


def test_http_5xx_maps_to_server_error():
    provider = _provider(lambda request: _json_response({"error": "boom"}, status=503))
    with pytest.raises(ProviderServerError):
        asyncio.run(provider.generate_text(TextRequest(prompt="hi")))


def test_http_timeout_maps_to_provider_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = _provider(handler)
    with pytest.raises(ProviderTimeoutError):
        asyncio.run(provider.generate_text(TextRequest(prompt="hi")))


def test_transport_error_maps_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("name or service not known")

    provider = _provider(handler)
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.generate_text(TextRequest(prompt="hi")))


def test_malformed_success_payload_is_invalid_response():
    provider = _provider(lambda request: _json_response({"unexpected": True}))
    with pytest.raises(InvalidProviderResponseError):
        asyncio.run(provider.generate_text(TextRequest(prompt="hi")))


def test_non_json_body_is_invalid_response():
    provider = _provider(lambda request: httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(InvalidProviderResponseError):
        asyncio.run(provider.generate_text(TextRequest(prompt="hi")))


def test_malformed_structured_output_raises_structured_error():
    provider = _provider(lambda request: _json_response(_content_body("not json at all")))
    with pytest.raises(StructuredOutputError):
        asyncio.run(
            provider.generate_structured(
                StructuredRequest(prompt="give json", json_schema={"type": "object"})
            )
        )


# ---------------------------------------------------------------------------
# Configuration + secret hygiene
# ---------------------------------------------------------------------------
def test_missing_api_key_raises_configuration_error_without_leaking():
    with pytest.raises(ProviderConfigurationError) as exc_info:
        GeminiProvider(api_key="", base_url=BASE_URL, default_model="gemini-flash-lite-latest")
    assert FAKE_KEY not in str(exc_info.value)


def test_missing_model_raises_configuration_error():
    # Only when BOTH the explicit value and the configured GEMINI_MODEL are
    # empty should the adapter reject with a configuration error.
    empty = AISettings(gemini_model="")
    with pytest.raises(ProviderConfigurationError):
        GeminiProvider(api_key=FAKE_KEY, base_url=BASE_URL, default_model="", settings=empty)


def test_error_messages_never_contain_key_or_image():
    provider = _provider(lambda request: _json_response({"error": "denied"}, status=403))
    image = "QUJD" * 80
    with pytest.raises(ProviderConfigurationError) as exc_info:
        asyncio.run(
            provider.generate_vision(
                VisionRequest(prompt="describe", image_base64=image, content_type="image/png")
            )
        )
    message = str(exc_info.value)
    assert FAKE_KEY not in message
    assert "QUJD" not in message


# ---------------------------------------------------------------------------
# Gateway policy: programming errors stay non-fallback-eligible
# ---------------------------------------------------------------------------
def test_adapter_programming_error_is_not_fallback_eligible():
    """A TypeError escaping the adapter must NOT silently switch providers."""

    class BuggyGemini(GeminiProvider):
        async def _generate(self, contents, **kwargs):  # noqa: ANN001, ANN003
            raise TypeError("programming bug")

    buggy = BuggyGemini(
        api_key=FAKE_KEY,
        base_url=BASE_URL,
        default_model="gemini-flash-lite-latest",
        transport=httpx.MockTransport(lambda request: _json_response(_content_body())),
    )
    from tests.test_ai_gateway import FakeProvider

    gateway = AIGateway(buggy, FakeProvider("other"))
    with pytest.raises(ProviderInternalError):
        asyncio.run(gateway.generate_text(TextRequest(prompt="hi")))


# ---------------------------------------------------------------------------
# Gateway integration: Qwen technical failure -> Gemini fallback succeeds
# ---------------------------------------------------------------------------
def test_gateway_qwen_failure_falls_back_to_gemini():
    def qwen_fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    qwen = QwenProvider(
        api_key="sk-qwen-fake",
        base_url="https://example.cn/compatible-mode/v1",
        default_model="qwen3.7-plus",
        transport=httpx.MockTransport(qwen_fail),
    )
    gemini = _provider(lambda request: _json_response(_content_body("gemini answered")))
    gateway = AIGateway(qwen, gemini)

    result = asyncio.run(gateway.generate_text(TextRequest(prompt="hi")))

    assert result.fallback_used is True
    assert result.provider == "gemini"
    assert result.content == "gemini answered"
