"""Tests for the migrated product description generator (Phase 2A.5a).

The dentist portal's product description generation now goes through the
shared ``AIGateway`` (Qwen primary -> Gemini technical fallback). These tests
use fake gateways/providers only: ZERO external Qwen/Gemini/OpenRouter calls.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from orchestrator.ai import AIGateway
from orchestrator.ai.base import AIProvider
from orchestrator.ai.exceptions import (
    AllProvidersFailedError,
    ProviderConfigurationError,
    ProviderInternalError,
    ProviderServerError,
)
from orchestrator.ai.schemas import AIResult, StructuredRequest, TextRequest, VisionRequest
from orchestrator.dentist_portal.description_generator import generate_product_description


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
VALID_JSON_RESPONSE = json.dumps({
    "ai_description": "This toothbrush cleans gently and effectively.",
    "problems_solved": ["plaque buildup", "gingivitis"],
})

MARKDOWN_FENCED_RESPONSE = f"```json\n{VALID_JSON_RESPONSE}\n```"


class ScriptedProvider(AIProvider):
    """Minimal in-memory adapter: returns canned text or raises a typed error."""

    def __init__(self, name: str, *, content: str = "", failure: Exception | None = None) -> None:
        self.name = name
        self.default_model = f"{name}-configured-model"
        self.content = content
        self.failure = failure
        self.requests: list[TextRequest] = []

    async def generate_text(self, request: TextRequest) -> AIResult:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return AIResult(content=self.content, model=self.default_model)

    async def generate_vision(self, request: VisionRequest) -> AIResult:  # pragma: no cover
        raise NotImplementedError

    async def generate_structured(self, request: StructuredRequest) -> AIResult:  # pragma: no cover
        raise NotImplementedError


class SpyGateway:
    """Stands in for ``AIGateway`` so tests can inspect the normalized request."""

    def __init__(self, result: AIResult | None = None, failure: Exception | None = None) -> None:
        self.result = result or AIResult(content=VALID_JSON_RESPONSE, provider="qwen", model="qwen3.7-plus")
        self.failure = failure
        self.requests: list[TextRequest] = []

    async def generate_text(self, request: TextRequest) -> AIResult:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return self.result


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. Description generator uses AIGateway
# ---------------------------------------------------------------------------
def test_description_generator_uses_gateway_and_not_openrouter(monkeypatch):
    import orchestrator.openrouter_client as legacy_openrouter

    def _never(*args, **kwargs):  # pragma: no cover - guard must not be reached
        raise AssertionError("Migrated description path must not call OpenRouter")

    monkeypatch.setattr(legacy_openrouter.openrouter_client, "generate_chat_response", _never)

    gateway = SpyGateway()
    result = _run(generate_product_description("SoftBrush", "Gentle bristles", "Toothbrushes", gateway=gateway))

    assert result["ai_description"] == "This toothbrush cleans gently and effectively."
    assert result["problems_solved"] == ["plaque buildup", "gingivitis"]
    assert len(gateway.requests) == 1


# ---------------------------------------------------------------------------
# 2. Primary success returns expected description
# ---------------------------------------------------------------------------
def test_primary_success_returns_expected_description():
    qwen = ScriptedProvider("qwen", content=VALID_JSON_RESPONSE)
    gemini = ScriptedProvider("gemini", content="SHOULD NOT BE USED")
    gateway = AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5)

    result = _run(generate_product_description("FlossPack", "Waxed floss", "Floss", gateway=gateway))

    assert result["ai_description"] == "This toothbrush cleans gently and effectively."
    assert result["problems_solved"] == ["plaque buildup", "gingivitis"]
    assert qwen.requests and not gemini.requests


# ---------------------------------------------------------------------------
# 3. Qwen technical failure -> Gemini fallback succeeds
# ---------------------------------------------------------------------------
def test_qwen_technical_failure_falls_back_to_gemini():
    qwen = ScriptedProvider("qwen", failure=ProviderServerError("Qwen HTTP 503"))
    gemini = ScriptedProvider("gemini", content=VALID_JSON_RESPONSE)
    gateway = AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5)

    result = _run(generate_product_description("FlossPack", "Waxed floss", "Floss", gateway=gateway))

    assert result["ai_description"] == "This toothbrush cleans gently and effectively."
    assert qwen.requests and gemini.requests
    assert gemini.requests[0].model is None  # provider resolves GEMINI_MODEL itself


# ---------------------------------------------------------------------------
# 4. Existing return/API shape preserved
# ---------------------------------------------------------------------------
def test_return_shape_is_dict_with_expected_keys():
    gateway = SpyGateway()
    result = _run(generate_product_description("TestProduct", "Some note", "Category", gateway=gateway))

    assert isinstance(result, dict)
    assert "ai_description" in result
    assert "problems_solved" in result
    assert isinstance(result["problems_solved"], list)


def test_markdown_fenced_response_is_still_stripped():
    gateway = SpyGateway(result=AIResult(content=MARKDOWN_FENCED_RESPONSE, provider="qwen", model="qwen-model"))
    result = _run(generate_product_description("TestProduct", "Some note", "Category", gateway=gateway))

    assert result["ai_description"] == "This toothbrush cleans gently and effectively."
    assert result["problems_solved"] == ["plaque buildup", "gingivitis"]


# ---------------------------------------------------------------------------
# 5. Direct OpenRouter client is not called
# ---------------------------------------------------------------------------
def test_openrouter_client_is_not_imported_at_runtime(monkeypatch):
    """The migrated module must not import openrouter_client at all."""
    import orchestrator.dentist_portal.description_generator as dg_module
    import sys

    # Verify no openrouter_client import in the module's namespace
    assert not hasattr(dg_module, "openrouter_client")

    # Also verify the module source doesn't contain the old import
    import inspect
    source = inspect.getsource(dg_module)
    assert "openrouter_client" not in source


# ---------------------------------------------------------------------------
# 6. Programming/config error behavior remains safe and explicit
# ---------------------------------------------------------------------------
def test_configuration_error_propagates_instead_of_falling_back():
    qwen = ScriptedProvider("qwen", failure=ProviderConfigurationError("DASHSCOPE_API_KEY missing"))
    gemini = ScriptedProvider("gemini", content="MUST NOT BE REACHED")
    gateway = AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5)

    with pytest.raises(ProviderConfigurationError):
        _run(generate_product_description("TestProduct", "note", "cat", gateway=gateway))
    assert not gemini.requests


def test_programming_error_propagates_as_provider_internal_error():
    qwen = ScriptedProvider("qwen", failure=ValueError("bug in request construction"))
    gemini = ScriptedProvider("gemini", content="MUST NOT BE REACHED")
    gateway = AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5)

    with pytest.raises(ProviderInternalError):
        _run(generate_product_description("TestProduct", "note", "cat", gateway=gateway))
    assert not gemini.requests


def test_both_providers_failed_degrades_to_deterministic_fallback():
    qwen = ScriptedProvider("qwen", failure=ProviderServerError("down"))
    gemini = ScriptedProvider("gemini", failure=ProviderServerError("also down"))
    gateway = AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5)

    result = _run(generate_product_description("TestProduct", "special note", "TestCategory", gateway=gateway))

    # Deterministic fallback must still return the expected shape
    assert isinstance(result, dict)
    assert "ai_description" in result
    assert "problems_solved" in result
    assert "TestProduct" in result["ai_description"]
    assert "special note" in result["ai_description"]
    assert result["problems_solved"] == ["TestCategory"]


def test_empty_response_degrades_to_deterministic_fallback():
    gateway = SpyGateway(result=AIResult(content="", provider="qwen", model="qwen-model"))
    result = _run(generate_product_description("EmptyProduct", "some note", "Cat", gateway=gateway))

    assert "EmptyProduct" in result["ai_description"]
    assert result["problems_solved"] == ["Cat"]


def test_malformed_json_degrades_to_deterministic_fallback():
    gateway = SpyGateway(result=AIResult(content="not valid json at all", provider="qwen", model="qwen-model"))
    result = _run(generate_product_description("BadJSON", "note", "Cat", gateway=gateway))

    assert "BadJSON" in result["ai_description"]
    assert result["problems_solved"] == ["Cat"]


# ---------------------------------------------------------------------------
# Gateway request contract
# ---------------------------------------------------------------------------
def test_gateway_receives_neutral_normalized_text_request():
    gateway = SpyGateway()
    _run(generate_product_description("MyProduct", "Dentist note here", "Whitening", gateway=gateway))

    request = gateway.requests[0]
    assert isinstance(request, TextRequest)
    assert [m.role for m in request.messages] == ["system", "user"]
    assert "dental product description expert" in request.messages[0].content
    assert "MyProduct" in request.messages[1].content
    assert "Whitening" in request.messages[1].content
    assert "Dentist note here" in request.messages[1].content
    assert request.temperature == 0.3
    assert request.max_tokens == 400
    # No provider-specific model id leaks from the business caller.
    assert request.model is None
