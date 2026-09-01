"""Unit tests for the Qwen provider adapter (Phase 2A.2).

These tests use ``httpx.MockTransport`` only and make ZERO real Alibaba
Model Studio API calls. They verify payload construction, response
normalization, model selection, error mapping, and secret hygiene.
Async is driven with ``asyncio.run`` so no async pytest plugin is required.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from orchestrator.ai import (
    AIGateway,
    AIResult,
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

from tests.test_ai_gateway import FakeProvider

FAKE_KEY = "sk-test-SECRET-NOT-A-REAL-KEY"
BASE_URL = "https://example-workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"


def _completion_body(content: str = "hi", *, model: str = "qwen3.7-plus") -> dict:
    return {
        "id": "chatcmpl-1",
        "model": model,
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }


def _provider(
    handler,
    *,
    vision_model: str | None = None,
    timeout: float = 5.0,
) -> QwenProvider:
    return QwenProvider(
        api_key=FAKE_KEY,
        base_url=BASE_URL,
        default_model="qwen3.7-plus",
        chat_model="qwen3.7-plus",
        vision_model=vision_model,
        timeout_seconds=timeout,
        transport=httpx.MockTransport(handler),
    )


def _json_response(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


# ---------------------------------------------------------------------------
# Payload construction + normalization
# ---------------------------------------------------------------------------
def test_text_payload_and_auth_headers():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _json_response(_completion_body("hello back"))

    provider = _provider(handler)
    result = asyncio.run(
        provider.generate_text(
            TextRequest(prompt="hi", temperature=0.3, max_tokens=64)
        )
    )

    assert captured, "no HTTP request was issued"
    request = captured[0]
    assert request.url.path.endswith("/compatible-mode/v1/chat/completions")
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    payload = json.loads(request.content.decode())
    assert payload["model"] == "qwen3.7-plus"
    assert payload["messages"] == [{"role": "user", "content": "hi"}]
    assert payload["temperature"] == 0.3
    assert payload["max_tokens"] == 64
    assert "response_format" not in payload
    assert result.content == "hello back"


def test_text_success_normalization():
    provider = _provider(lambda request: _json_response(_completion_body("ok")))
    result = asyncio.run(provider.generate_text(TextRequest(prompt="hi")))

    assert isinstance(result, AIResult)
    assert result.provider == "qwen"
    assert result.model == "qwen3.7-plus"
    assert result.finish_reason == "stop"
    assert result.usage is not None
    assert result.usage.total_tokens == 7
    assert result.latency_ms >= 0.0
    assert result.raw_metadata == {"response_id": "chatcmpl-1"}
    assert result.fallback_used is False


def test_text_generation_defaults_to_chat_model():
    """Conversational text uses QWEN_CHAT_MODEL, not the general default model."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _json_response(_completion_body("ok", model="qwen-chat-special"))

    provider = QwenProvider(
        api_key=FAKE_KEY,
        base_url=BASE_URL,
        default_model="qwen-general-model",
        chat_model="qwen-chat-special",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(provider.generate_text(TextRequest(prompt="hi")))

    payload = json.loads(captured[0].content.decode())
    assert payload["model"] == "qwen-chat-special"
    assert result.model == "qwen-chat-special"


def test_messages_passthrough_and_model_override():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _json_response(_completion_body())

    provider = _provider(handler)
    req = TextRequest(
        messages=[
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
        ],
        model="qwen-max",
    )
    asyncio.run(provider.generate_text(req))

    payload = json.loads(captured[0].content.decode())
    assert payload["model"] == "qwen-max"
    assert payload["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
    ]


def test_vision_builds_data_url_and_uses_vision_model():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _json_response(_completion_body("teeth look fine", model="qwen3.7-plus"))

    provider = _provider(handler, vision_model="qwen-vision-special")
    result = asyncio.run(
        provider.generate_vision(
            VisionRequest(prompt="describe", image_base64="QUJD", content_type="image/png")
        )
    )

    payload = json.loads(captured[0].content.decode())
    assert payload["model"] == "qwen-vision-special"
    content_parts = payload["messages"][0]["content"]
    assert content_parts[0] == {"type": "text", "text": "describe"}
    assert content_parts[1]["image_url"]["url"] == "data:image/png;base64,QUJD"
    assert result.content == "teeth look fine"


def test_structured_success_sets_response_format_and_data():
    captured: list[httpx.Request] = []
    body = _completion_body('{"ok": true}')

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _json_response(body)

    provider = _provider(handler)
    result = asyncio.run(
        provider.generate_structured(
            StructuredRequest(prompt="give json", json_schema={"type": "object"})
        )
    )

    payload = json.loads(captured[0].content.decode())
    assert payload["response_format"] == {"type": "json_object"}
    assert "JSON schema" in payload["messages"][0]["content"]
    assert result.data == {"ok": True}


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------
def test_http_429_maps_to_rate_limit():
    provider = _provider(lambda request: _json_response({"error": "slow down"}, status=429))
    with pytest.raises(ProviderRateLimitError):
        asyncio.run(provider.generate_text(TextRequest(prompt="hi")))


def test_http_5xx_maps_to_server_error():
    provider = _provider(lambda request: _json_response({"error": "boom"}, status=503))
    with pytest.raises(ProviderServerError):
        asyncio.run(provider.generate_text(TextRequest(prompt="hi")))


def test_http_401_maps_to_configuration_error_without_leaking_key():
    provider = _provider(lambda request: _json_response({"error": "denied"}, status=401))
    with pytest.raises(ProviderConfigurationError) as exc_info:
        asyncio.run(provider.generate_text(TextRequest(prompt="hi")))
    assert FAKE_KEY not in str(exc_info.value)


def test_http_403_maps_to_configuration_error():
    provider = _provider(lambda request: _json_response({"error": "forbidden"}, status=403))
    with pytest.raises(ProviderConfigurationError):
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
    provider = _provider(lambda request: _json_response(_completion_body("not json at all")))
    with pytest.raises(StructuredOutputError):
        asyncio.run(
            provider.generate_structured(
                StructuredRequest(prompt="give json", json_schema={"type": "object"})
            )
        )


# ---------------------------------------------------------------------------
# Schema validation (Phase 2A.2 hardening)
# ---------------------------------------------------------------------------
_SCHEMA_WITH_REQUIRED = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer"},
    },
    "required": ["name", "age"],
}


def _structured_provider(handler, schema: dict) -> QwenProvider:
    """Helper: build a provider that returns *handler*'s response for structured calls."""
    return _provider(handler)


def test_structured_valid_object_passes_schema_validation():
    body = _completion_body('{"name": "Alice", "age": 30}')
    provider = _provider(lambda request: _json_response(body))
    result = asyncio.run(
        provider.generate_structured(
            StructuredRequest(prompt="give json", json_schema=_SCHEMA_WITH_REQUIRED)
        )
    )
    assert result.data == {"name": "Alice", "age": 30}


def test_structured_missing_required_property_raises_structured_error():
    # "age" is required but missing.
    body = _completion_body('{"name": "Alice"}')
    provider = _provider(lambda request: _json_response(body))
    with pytest.raises(StructuredOutputError, match="does not match the requested schema"):
        asyncio.run(
            provider.generate_structured(
                StructuredRequest(prompt="give json", json_schema=_SCHEMA_WITH_REQUIRED)
            )
        )


def test_structured_wrong_property_type_raises_structured_error():
    # "age" should be integer but is a string.
    body = _completion_body('{"name": "Alice", "age": "thirty"}')
    provider = _provider(lambda request: _json_response(body))
    with pytest.raises(StructuredOutputError, match="does not match the requested schema"):
        asyncio.run(
            provider.generate_structured(
                StructuredRequest(prompt="give json", json_schema=_SCHEMA_WITH_REQUIRED)
            )
        )


# ---------------------------------------------------------------------------
# Configuration + secret hygiene
# ---------------------------------------------------------------------------
def test_missing_api_key_raises_configuration_error_without_leaking():
    with pytest.raises(ProviderConfigurationError) as exc_info:
        QwenProvider(api_key="", base_url=BASE_URL, default_model="qwen3.7-plus")
    assert FAKE_KEY not in str(exc_info.value)


def test_missing_base_url_raises_configuration_error():
    with pytest.raises(ProviderConfigurationError):
        QwenProvider(api_key=FAKE_KEY, base_url="", default_model="qwen3.7-plus")


def test_error_messages_never_contain_api_key():
    provider = _provider(lambda request: _json_response({"error": "denied"}, status=401))
    with pytest.raises(ProviderConfigurationError) as exc_info:
        asyncio.run(
            provider.generate_vision(
                VisionRequest(prompt="describe", image_base64="QUJD"*80, content_type="image/png")
            )
        )
    message = str(exc_info.value)
    assert FAKE_KEY not in message
    assert "QUJD" not in message  # image data must not be echoed into errors


# ---------------------------------------------------------------------------
# Gateway policy integration: programming errors stay non-fallback-eligible
# ---------------------------------------------------------------------------
def test_adapter_programming_error_is_not_fallback_eligible():
    """A TypeError escaping the adapter must NOT silently switch providers."""

    class BuggyQwen(QwenProvider):
        async def _chat(self, messages, **kwargs):  # noqa: ANN001, ANN003
            raise TypeError("programming bug")

    buggy = BuggyQwen(
        api_key=FAKE_KEY,
        base_url=BASE_URL,
        default_model="qwen3.7-plus",
        transport=httpx.MockTransport(lambda request: _json_response(_completion_body())),
    )
    fallback = FakeProvider("gemini")
    gateway = AIGateway(buggy, fallback)

    with pytest.raises(ProviderInternalError):
        asyncio.run(gateway.generate_text(TextRequest(prompt="hi")))
    assert fallback.calls == []
