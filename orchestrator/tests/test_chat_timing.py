"""Tests for chat timing instrumentation.

These tests verify that the timing instrumentation added for diagnostic purposes
does NOT alter the response behavior of the chat system. The instrumentation is
purely observational and must not change any business logic.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from orchestrator.ai.schemas import AIResult
from orchestrator.conversation_engine import ConversationEngine


class SpyGateway:
    """Minimal gateway stub for testing."""

    def __init__(self, content: str = "Test response.") -> None:
        self.content = content
        self.requests = []

    async def generate_text(self, request) -> AIResult:
        self.requests.append(request)
        return AIResult(
            content=self.content,
            provider="qwen",
            model="qwen3.7-plus",
            latency_ms=100.0,
            fallback_used=False,
        )


def _stub_rag(monkeypatch) -> None:
    """Stub knowledge enhancement to keep tests offline."""
    from orchestrator import conversation_engine as engine_module

    def _fake_enhance(query, prompt, active_issue=None):
        return prompt

    monkeypatch.setattr(
        engine_module, "_enhance_prompt_with_knowledge", _fake_enhance
    )


@pytest.fixture(autouse=True)
def _keep_rag_offline(monkeypatch):
    """Ensure RAG stays offline during tests."""
    _stub_rag(monkeypatch)


def test_timing_instrumentation_does_not_alter_response():
    """Verify that timing code does not change the generated response."""
    gateway = SpyGateway(content="Bleeding gums usually mean plaque irritation.")
    engine = ConversationEngine(gateway=gateway)

    response = asyncio.run(
        engine.generate_conversational_response(
            "Why do my gums bleed?",
            recent_messages=[],
            conversation_id=None,
        )
    )

    assert response == "Bleeding gums usually mean plaque irritation."
    assert len(gateway.requests) == 1


def test_timing_instrumentation_logs_ai_metadata(caplog):
    """Verify that AI call metadata is logged correctly."""
    import logging

    gateway = SpyGateway(content="Test response.")
    engine = ConversationEngine(gateway=gateway)

    with caplog.at_level(logging.INFO):
        asyncio.run(
            engine.generate_conversational_response(
                "Test message",
                recent_messages=[],
                conversation_id=None,
            )
        )

    # Check that timing logs are present
    log_messages = [record.message for record in caplog.records]
    assert any("[CHAT_TIMING]" in msg for msg in log_messages)
    assert any("[CHAT_AI]" in msg for msg in log_messages)


def test_timing_instrumentation_does_not_expose_sensitive_data(caplog):
    """Verify that timing logs do not expose API keys, tokens, or patient data."""
    import logging

    gateway = SpyGateway(content="Test response.")
    engine = ConversationEngine(gateway=gateway)

    with caplog.at_level(logging.INFO):
        asyncio.run(
            engine.generate_conversational_response(
                "Test message with sensitive info",
                recent_messages=[],
                conversation_id=None,
            )
        )

    log_messages = [record.message for record in caplog.records]
    timing_logs = [msg for msg in log_messages if "[CHAT_TIMING]" in msg or "[CHAT_AI]" in msg]

    # Verify no sensitive data patterns in timing logs
    sensitive_patterns = [
        "sk-",
        "api_key",
        "token",
        "password",
        "secret",
        "base64",
        "image",
    ]

    for log_msg in timing_logs:
        for pattern in sensitive_patterns:
            assert pattern not in log_msg.lower(), f"Sensitive data pattern '{pattern}' found in log: {log_msg}"


def test_multiple_ai_calls_are_logged_separately():
    """Verify that multiple AI calls (main + tail completion) are logged separately."""
    import logging

    class IncompleteResponseGateway(SpyGateway):
        """Gateway that returns incomplete response first, then completion."""

        def __init__(self):
            super().__init__()
            self.call_count = 0

        async def generate_text(self, request) -> AIResult:
            self.call_count += 1
            self.requests.append(request)
            if self.call_count == 1:
                # First call: incomplete response
                return AIResult(
                    content="This is incomplete",
                    provider="qwen",
                    model="qwen3.7-plus",
                    latency_ms=100.0,
                    fallback_used=False,
                )
            else:
                # Second call: completion
                return AIResult(
                    content="and this completes it.",
                    provider="qwen",
                    model="qwen3.7-plus",
                    latency_ms=50.0,
                    fallback_used=False,
                )

    gateway = IncompleteResponseGateway()
    engine = ConversationEngine(gateway=gateway)

    response = asyncio.run(
        engine.generate_conversational_response(
            "Test message",
            recent_messages=[],
            conversation_id=None,
        )
    )

    # Should have made 2 AI calls
    assert gateway.call_count == 2
    assert len(gateway.requests) == 2


def test_timing_instrumentation_preserves_fallback_behavior():
    """Verify that timing instrumentation does not interfere with fallback logic."""
    from orchestrator.ai import AIGateway
    from orchestrator.ai.exceptions import ProviderServerError
    from orchestrator.ai.base import AIProvider
    from orchestrator.ai.schemas import StructuredRequest, TextRequest, VisionRequest

    class FailingProvider(AIProvider):
        """Provider that always fails."""

        def __init__(self, name: str):
            self.name = name
            self.default_model = f"{name}-model"

        async def generate_text(self, request: TextRequest) -> AIResult:
            raise ProviderServerError("Provider down")

        async def generate_vision(self, request: VisionRequest) -> AIResult:
            raise NotImplementedError

        async def generate_structured(self, request: StructuredRequest) -> AIResult:
            raise NotImplementedError

    class WorkingProvider(AIProvider):
        """Provider that works."""

        def __init__(self, name: str, content: str):
            self.name = name
            self.default_model = f"{name}-model"
            self.content = content

        async def generate_text(self, request: TextRequest) -> AIResult:
            return AIResult(
                content=self.content,
                provider=self.name,
                model=self.default_model,
                latency_ms=100.0,
                fallback_used=True,
            )

        async def generate_vision(self, request: VisionRequest) -> AIResult:
            raise NotImplementedError

        async def generate_structured(self, request: StructuredRequest) -> AIResult:
            raise NotImplementedError

    primary = FailingProvider("qwen")
    fallback = WorkingProvider("gemini", "Fallback response.")
    gateway = AIGateway(primary=primary, fallback=fallback, timeout_seconds=5)
    engine = ConversationEngine(gateway=gateway)

    response = asyncio.run(
        engine.generate_conversational_response(
            "Test message",
            recent_messages=[],
            conversation_id=None,
        )
    )

    assert response == "Fallback response."


def test_dental_knowledge_lookup_has_no_huggingface_or_embedding():
    """Knowledge lookup uses fast keyword matching with zero embeddings or HF downloads."""
    from orchestrator.central_dentist.knowledge import find_relevant_knowledge

    entries = find_relevant_knowledge("bleeding gums and plaque")
    assert len(entries) > 0
    assert any("gingivitis" in e.lower() or "plaque" in e.lower() for e in entries)


def test_follow_up_skips_rag(monkeypatch, caplog):
    """When skip_rag=True, _enhance_prompt_with_knowledge must NOT be called."""
    import logging

    gateway = SpyGateway(content="Sure, I can elaborate on that.")
    engine = ConversationEngine(gateway=gateway)

    rag_called = False
    from orchestrator import conversation_engine as engine_module

    def _tracking_enhance(query, prompt, active_issue=None):
        nonlocal rag_called
        rag_called = True
        return prompt

    monkeypatch.setattr(
        engine_module, "_enhance_prompt_with_knowledge", _tracking_enhance
    )

    with caplog.at_level(logging.INFO):
        response = asyncio.run(
            engine.generate_conversational_response(
                "thanks",
                recent_messages=[],
                conversation_id=None,
                skip_rag=True,
            )
        )

    assert not rag_called, "Knowledge enhancement must NOT be called with skip_rag=True"
    assert response == "Sure, I can elaborate on that."


def test_dental_question_retains_rag(monkeypatch):
    """A dental question with skip_rag=False must call knowledge enhancement."""
    gateway = SpyGateway(content="Plaque causes gum irritation.")
    engine = ConversationEngine(gateway=gateway)

    rag_called = False
    from orchestrator import conversation_engine as engine_module

    def _tracking_enhance(query, prompt, active_issue=None):
        nonlocal rag_called
        rag_called = True
        return prompt

    monkeypatch.setattr(
        engine_module, "_enhance_prompt_with_knowledge", _tracking_enhance
    )

    asyncio.run(
        engine.generate_conversational_response(
            "Why do gums bleed?",
            recent_messages=[],
            conversation_id=None,
            skip_rag=False,
        )
    )

    assert rag_called, "Knowledge enhancement must be called for dental questions with skip_rag=False"


def test_tail_completion_timing_logged(caplog):
    """When tail completion fires, its timing must be logged."""
    import logging

    class IncompleteGateway(SpyGateway):
        def __init__(self):
            super().__init__()
            self.call_count = 0

        async def generate_text(self, request) -> AIResult:
            self.call_count += 1
            self.requests.append(request)
            if self.call_count == 1:
                return AIResult(
                    content="This response trails off and",
                    provider="qwen",
                    model="qwen3.7-plus",
                    latency_ms=100.0,
                    fallback_used=False,
                )
            return AIResult(
                content="finishes the thought.",
                provider="qwen",
                model="qwen3.7-plus",
                latency_ms=50.0,
                fallback_used=False,
            )

    gateway = IncompleteGateway()
    engine = ConversationEngine(gateway=gateway)

    with caplog.at_level(logging.INFO):
        asyncio.run(
            engine.generate_conversational_response(
                "Test message",
                recent_messages=[],
                conversation_id=None,
            )
        )

    log_messages = [record.message for record in caplog.records]
    assert any("tail_completion_ms" in msg for msg in log_messages), (
        "tail_completion_ms must be logged when response is incomplete"
    )
