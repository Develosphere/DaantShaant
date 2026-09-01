"""Tests for the migrated conversational chat caller (Phase 2A.4).

The orchestrator's chat text generation now goes through the shared
``AIGateway`` (Qwen primary -> Gemini technical fallback). These tests use
fake gateways/providers only: ZERO external Qwen/Gemini/OpenRouter calls and
no FAISS/embedding work (retrieval is stubbed at its existing boundary).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

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
from orchestrator.chat_schemas import SendMessageResponse
from orchestrator.conversation_engine import ConversationEngine

USER_MESSAGE = "Why do my gums bleed when I brush?"
RAG_MARKER = "[RAG CONTEXT] Brushing gently twice a day helps inflamed gums."


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
        self.result = result or AIResult(content="", provider="qwen", model="qwen3.7-plus")
        self.failure = failure
        self.requests: list[TextRequest] = []

    async def generate_text(self, request: TextRequest) -> AIResult:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return self.result


def _reply(text: str) -> AIResult:
    """A complete-sentence reply so post-processing adds nothing."""
    return AIResult(content=text, provider="qwen", model="qwen3.7-plus")


def _stub_rag(monkeypatch) -> None:
    """Keep the existing RAG boundary, but never touch FAISS/embeddings."""
    from orchestrator import conversation_engine as engine_module

    async def _fake_enhance(query, prompt, conversation_id=None):
        return f"{prompt}\n\n{RAG_MARKER}"

    monkeypatch.setattr(
        engine_module.retrieval_service, "get_enhanced_prompt", _fake_enhance
    )


def _generate(engine: ConversationEngine, message: str = USER_MESSAGE) -> str:
    return asyncio.run(
        engine.generate_conversational_response(message, [], conversation_id=None)
    )


@pytest.fixture(autouse=True)
def _keep_rag_offline(monkeypatch):
    """Preserve the RAG call boundary without loading FAISS/embeddings."""
    _stub_rag(monkeypatch)


# ---------------------------------------------------------------------------
# The migrated caller depends only on the gateway contract
# ---------------------------------------------------------------------------
def test_chat_uses_gateway_and_not_the_legacy_chain(monkeypatch):
    import orchestrator.llm_provider as legacy_llm
    import orchestrator.openrouter_client as legacy_openrouter

    def _never(*args, **kwargs):  # pragma: no cover - guard must not be reached
        raise AssertionError("Migrated chat path must not call the legacy provider chain")

    monkeypatch.setattr(legacy_llm.llm_provider, "generate", _never)
    monkeypatch.setattr(legacy_openrouter.openrouter_client, "generate_chat_response", _never)

    gateway = SpyGateway(_reply("Bleeding gums usually mean plaque is irritating the gumline."))
    engine = ConversationEngine(gateway=gateway)

    assert not hasattr(engine, "llm")
    assert not hasattr(engine, "client")
    assert _generate(engine) == "Bleeding gums usually mean plaque is irritating the gumline."
    assert len(gateway.requests) == 1


def test_gateway_receives_a_neutral_normalized_text_request():
    gateway = SpyGateway(_reply("Plaque buildup is the usual cause here. A soft brush helps."))
    engine = ConversationEngine(gateway=gateway)

    _generate(engine)
    request = gateway.requests[0]

    assert isinstance(request, TextRequest)
    assert [m.role for m in request.messages] == ["system", "user"]
    assert "DaantShaant" in request.messages[0].content
    assert USER_MESSAGE in request.messages[1].content
    assert request.temperature == 0.8
    assert request.max_tokens == 300
    # No provider-specific model id leaks from the business caller.
    assert request.model is None


def test_rag_context_still_flows_into_generation():
    gateway = SpyGateway(_reply("Inflamed gums respond well to gentle brushing and flossing."))
    engine = ConversationEngine(gateway=gateway)

    _generate(engine)

    assert RAG_MARKER in gateway.requests[0].messages[1].content


def test_conversation_history_is_still_passed_in():
    gateway = SpyGateway(_reply("Still sounds like plaque irritation to me. Keep flossing nightly."))
    engine = ConversationEngine(gateway=gateway)
    history = SimpleNamespace(sender="user", text="my gums hurt")

    asyncio.run(
        engine.generate_conversational_response(
            "it got worse", [history], conversation_id=None
        )
    )

    assert "my gums hurt" in gateway.requests[0].messages[1].content


# ---------------------------------------------------------------------------
# Provider priority + fallback through the real gateway
# ---------------------------------------------------------------------------
def test_qwen_primary_answers_and_gemini_is_not_called():
    qwen = ScriptedProvider("qwen", content="Cold water sensitivity is usually enamel exposure.")
    gemini = ScriptedProvider("gemini", content="SHOULD NOT BE USED")
    engine = ConversationEngine(gateway=AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5))

    answer = _generate(engine)

    assert answer == "Cold water sensitivity is usually enamel exposure."
    assert qwen.requests and not gemini.requests


def test_technical_qwen_failure_falls_back_to_gemini_for_chat():
    qwen = ScriptedProvider("qwen", failure=ProviderServerError("Qwen server error (HTTP 503)"))
    gemini = ScriptedProvider("gemini", content="Plaque near the gumline is the likely trigger.")
    engine = ConversationEngine(gateway=AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5))

    answer = _generate(engine)

    assert answer == "Plaque near the gumline is the likely trigger."
    assert qwen.requests and gemini.requests
    assert gemini.requests[0].model is None  # provider resolves GEMINI_MODEL itself


def test_configuration_error_propagates_instead_of_falling_back():
    qwen = ScriptedProvider("qwen", failure=ProviderConfigurationError("DASHSCOPE_API_KEY missing"))
    gemini = ScriptedProvider("gemini", content="MUST NOT BE REACHED")
    engine = ConversationEngine(gateway=AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5))

    with pytest.raises(ProviderConfigurationError):
        _generate(engine)
    assert not gemini.requests


def test_programming_error_propagates_instead_of_falling_back():
    qwen = ScriptedProvider("qwen", failure=ValueError("bug in request construction"))
    gemini = ScriptedProvider("gemini", content="MUST NOT BE REACHED")
    engine = ConversationEngine(gateway=AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5))

    with pytest.raises(ProviderInternalError):
        _generate(engine)
    assert not gemini.requests


def test_both_providers_technically_failed_degrades_to_deterministic_answer():
    qwen = ScriptedProvider("qwen", failure=ProviderServerError("down"))
    gemini = ScriptedProvider("gemini", failure=ProviderServerError("also down"))
    gateway = AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5)
    engine = ConversationEngine(gateway=gateway)

    with pytest.raises(AllProvidersFailedError):
        asyncio.run(gateway.generate_text(TextRequest(prompt="hi")))

    answer = _generate(engine)
    assert answer.startswith("Gums often bleed because plaque irritates the gum tissue.")


# ---------------------------------------------------------------------------
# Response contract compatibility
# ---------------------------------------------------------------------------
def test_chat_contract_returns_plain_text_string():
    engine = ConversationEngine(gateway=SpyGateway(_reply("Sounds like early gingivitis. Floss daily.")))
    assert isinstance(_generate(engine), str)


def test_send_message_response_contract_unchanged():
    assert set(SendMessageResponse.model_fields) == {
        "conversation_id",
        "user_message",
        "assistant_message",
    }


def test_engine_resolves_gateway_lazily_not_at_import(monkeypatch):
    from orchestrator.ai import factory

    monkeypatch.setattr(factory, "_gateway", None)
    engine = ConversationEngine()

    assert engine._gateway is None

    def _boom(*args, **kwargs):  # pragma: no cover - guard must not be reached
        raise AssertionError("Gateway composition must stay lazy and offline")

    monkeypatch.setattr("orchestrator.ai.factory.create_ai_gateway", _boom)
    with pytest.raises(AssertionError):
        engine.gateway
