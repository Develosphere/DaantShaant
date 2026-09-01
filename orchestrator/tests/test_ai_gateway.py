"""Unit tests for the shared DaantShaant AI Gateway core (Phase 2A.1).

These tests use FAKE providers only and make ZERO external AI API calls.
They verify: routing, normalized metadata, the fallback policy, and the
error contract. Async is driven with ``asyncio.run`` so no async pytest
plugin is required.
"""

from __future__ import annotations

import asyncio

import pytest

from orchestrator.ai import (
    AIProvider,
    AIGateway,
    AIResult,
    StructuredRequest,
    TextRequest,
    VisionRequest,
)
from orchestrator.ai.exceptions import (
    AllProvidersFailedError,
    ProviderConfigurationError,
    ProviderInternalError,
    ProviderRateLimitError,
    StructuredOutputError,
)


class FakeProvider(AIProvider):
    """Configurable fake: raises per-method failures or returns canned results."""

    def __init__(
        self,
        name: str,
        model: str = "fake-model",
        failures: dict[str, Exception] | None = None,
        sleep: float = 0.0,
    ) -> None:
        self.name = name
        self.default_model = model
        self.failures = failures or {}
        self.sleep = sleep
        self.calls: list[str] = []

    async def generate_text(self, request: TextRequest) -> AIResult:
        return await self._handle("generate_text", "text:" + self.name)

    async def generate_vision(self, request: VisionRequest) -> AIResult:
        return await self._handle("generate_vision", "vision:" + self.name)

    async def generate_structured(self, request: StructuredRequest) -> AIResult:
        return await self._handle(
            "generate_structured", '{"ok": true}', data={"ok": True}
        )

    async def _handle(self, method: str, content: str, data=None) -> AIResult:
        self.calls.append(method)
        if self.sleep:
            await asyncio.sleep(self.sleep)
        failure = self.failures.get(method)
        if failure is not None:
            raise failure
        # Deliberately omit provider/model so the gateway must normalize them.
        return AIResult(content=content, data=data)


def _text_req() -> TextRequest:
    return TextRequest(prompt="hello")


def test_primary_success_and_fallback_flag_false():
    primary = FakeProvider("qwen")
    gateway = AIGateway(primary)
    result = asyncio.run(gateway.generate_text(_text_req()))

    assert result.content == "text:qwen"
    assert result.fallback_used is False
    assert primary.calls == ["generate_text"]


def test_technical_failure_triggers_fallback_and_flag_true():
    primary = FakeProvider("qwen", failures={"generate_text": ProviderRateLimitError("429")})
    fallback = FakeProvider("gemini")
    gateway = AIGateway(primary, fallback)
    result = asyncio.run(gateway.generate_text(_text_req()))

    assert result.content == "text:gemini"
    assert result.fallback_used is True
    assert primary.calls == ["generate_text"]
    assert fallback.calls == ["generate_text"]


def test_config_error_does_not_fallback():
    primary = FakeProvider("qwen", failures={"generate_text": ProviderConfigurationError("no key")})
    fallback = FakeProvider("gemini")
    gateway = AIGateway(primary, fallback)

    with pytest.raises(ProviderConfigurationError):
        asyncio.run(gateway.generate_text(_text_req()))

    # Fallback must NOT be attempted for a local configuration error.
    assert fallback.calls == []


def test_normalized_provider_and_model_metadata():
    primary = FakeProvider("qwen", model="qwen3.7-plus")
    gateway = AIGateway(primary)
    result = asyncio.run(gateway.generate_text(_text_req()))

    assert result.provider == "qwen"
    assert result.model == "qwen3.7-plus"
    assert result.latency_ms >= 0.0


def test_text_routing():
    primary = FakeProvider("qwen")
    gateway = AIGateway(primary)
    result = asyncio.run(gateway.generate_text(_text_req()))
    assert primary.calls == ["generate_text"]
    assert result.content.startswith("text:")


def test_vision_routing():
    primary = FakeProvider("qwen")
    gateway = AIGateway(primary)
    req = VisionRequest(prompt="describe", image_base64="AAAA", content_type="image/png")
    result = asyncio.run(gateway.generate_vision(req))
    assert primary.calls == ["generate_vision"]
    assert result.content == "vision:qwen"


def test_structured_routing_returns_parsed_data():
    primary = FakeProvider("qwen")
    gateway = AIGateway(primary)
    req = StructuredRequest(
        prompt="give json", json_schema={"type": "object"}
    )
    result = asyncio.run(gateway.generate_structured(req))
    assert primary.calls == ["generate_structured"]
    assert result.data == {"ok": True}


def test_structured_parse_failure_does_not_fallback():
    primary = FakeProvider(
        "qwen", failures={"generate_structured": StructuredOutputError("bad json")}
    )
    fallback = FakeProvider("gemini")
    gateway = AIGateway(primary, fallback)
    req = StructuredRequest(prompt="give json", json_schema={"type": "object"})

    with pytest.raises(StructuredOutputError):
        asyncio.run(gateway.generate_structured(req))
    assert fallback.calls == []


def test_timeout_on_primary_falls_back():
    primary = FakeProvider("qwen", sleep=0.2)
    fallback = FakeProvider("gemini")
    gateway = AIGateway(primary, fallback, timeout_seconds=0.01)
    result = asyncio.run(gateway.generate_text(_text_req()))

    assert result.content == "text:gemini"
    assert result.fallback_used is True
    assert fallback.calls == ["generate_text"]


def test_both_providers_technical_failure_raises_clear_error():
    primary = FakeProvider("qwen", failures={"generate_text": ProviderRateLimitError("429")})
    fallback = FakeProvider("gemini", failures={"generate_text": ProviderRateLimitError("429")})
    gateway = AIGateway(primary, fallback)

    with pytest.raises(AllProvidersFailedError) as exc_info:
        asyncio.run(gateway.generate_text(_text_req()))

    assert set(exc_info.value.provider_errors) == {"qwen", "gemini"}


def test_arbitrary_value_error_does_not_fallback():
    """A programming-bug ValueError must NOT trigger fallback."""

    class BoomProvider(AIProvider):
        name = "boom"
        default_model = "boom-1"

        async def generate_text(self, request):  # noqa: ANN001
            raise ValueError("unexpected SDK crash")

        async def generate_vision(self, request):  # noqa: ANN001
            raise NotImplementedError

        async def generate_structured(self, request):  # noqa: ANN001
            raise NotImplementedError

    fallback = FakeProvider("gemini")
    gateway = AIGateway(BoomProvider(), fallback)

    with pytest.raises(ProviderInternalError):
        asyncio.run(gateway.generate_text(_text_req()))

    # Fallback must NOT be attempted for an unexpected programming error.
    assert fallback.calls == []


def test_arbitrary_runtime_error_does_not_fallback():
    """An arbitrary RuntimeError must NOT trigger fallback."""

    class CrashProvider(AIProvider):
        name = "crash"
        default_model = "crash-1"

        async def generate_text(self, request):  # noqa: ANN001
            raise RuntimeError("something broke internally")

        async def generate_vision(self, request):  # noqa: ANN001
            raise NotImplementedError

        async def generate_structured(self, request):  # noqa: ANN001
            raise NotImplementedError

    fallback = FakeProvider("gemini")
    gateway = AIGateway(CrashProvider(), fallback)

    with pytest.raises(ProviderInternalError):
        asyncio.run(gateway.generate_text(_text_req()))
    assert fallback.calls == []


def test_arbitrary_type_error_does_not_fallback():
    """A TypeError from a buggy adapter must NOT trigger fallback."""

    class BuggyProvider(AIProvider):
        name = "buggy"
        default_model = "buggy-1"

        async def generate_text(self, request):  # noqa: ANN001
            raise TypeError("bad operand type")

        async def generate_vision(self, request):  # noqa: ANN001
            raise NotImplementedError

        async def generate_structured(self, request):  # noqa: ANN001
            raise NotImplementedError

    fallback = FakeProvider("gemini")
    gateway = AIGateway(BuggyProvider(), fallback)

    with pytest.raises(ProviderInternalError):
        asyncio.run(gateway.generate_text(_text_req()))
    assert fallback.calls == []
