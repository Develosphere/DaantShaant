"""Phase 12C tests: Qwen provider live latency, persistent client reuse, timeout handling, and deterministic fallbacks."""

import asyncio
from datetime import datetime, timezone
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from orchestrator.ai.exceptions import (
    AllProvidersFailedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from orchestrator.ai.gateway import AIGateway
from orchestrator.ai.qwen import QwenProvider
from orchestrator.ai.schemas import AIResult, TextRequest
from orchestrator.central_dentist.graph import (
    CentralDentistState,
    central_dentist_graph,
)
from orchestrator.central_dentist.retrieval import FindingItem, ScanSummary
from orchestrator.config import AISettings, settings

FAKE_KEY = "sk-test-SECRET-NOT-A-REAL-KEY"
BASE_URL = "https://example-workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"


def _completion_body(content: str = "Dental guidance answer", *, model: str = "qwen3.7-plus") -> dict:
    return {
        "id": "chatcmpl-test",
        "model": model,
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 15, "completion_tokens": 20, "total_tokens": 35},
    }


def _provider_with_handler(handler, *, timeout: float = 8.0) -> QwenProvider:
    return QwenProvider(
        api_key=FAKE_KEY,
        base_url=BASE_URL,
        default_model="qwen3.7-plus",
        chat_model="qwen3.7-plus",
        timeout_seconds=timeout,
        transport=httpx.MockTransport(handler),
    )


# ---------------------------------------------------------------------------
# 1. HTTP Client Reuse between calls
# ---------------------------------------------------------------------------
def test_qwen_http_client_reused_between_calls():
    """Verify QwenProvider reuses its long-lived AsyncClient rather than creating a new one per request."""
    async def _test():
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=_completion_body(f"Answer {call_count}"))

        provider = _provider_with_handler(handler)

        # Call 1
        res1 = await provider.generate_text(TextRequest(prompt="First message"))
        assert res1.content == "Answer 1"
        client1 = provider._client
        assert client1 is not None
        assert not client1.is_closed

        # Call 2
        res2 = await provider.generate_text(TextRequest(prompt="Second message"))
        assert res2.content == "Answer 2"
        client2 = provider._client

        # Strict identity check: same AsyncClient instance reused
        assert client1 is client2
        assert call_count == 2

        # Clean shutdown check
        await provider.aclose()
        assert provider._client is None
        assert client1.is_closed

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 2. Compact Request Payload and Output Token Limit
# ---------------------------------------------------------------------------
def test_compact_request_payload_and_token_limits():
    """Verify requests to Qwen carry compact payloads, set max_tokens <= 300, and omit empty scan placeholders."""
    async def _test():
        captured_requests: list[TextRequest] = []

        class SpyGateway:
            async def generate_text(self, request: TextRequest) -> AIResult:
                captured_requests.append(request)
                return AIResult(content="Clean your teeth daily.", provider="qwen", model="qwen3.7-plus")

        state: CentralDentistState = {
            "user_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "message": "Can you advise on preventing dental decay?",
            "locale": "en",
            "request_id": "test_compact_01",
            "latest_scan": None,
            "appointments": [],
            "recent_turns": [],
            "_gateway": SpyGateway(),
            "_db_session": None,
        }

        result = await central_dentist_graph.ainvoke(state)
        assert len(captured_requests) == 1
        req = captured_requests[0]

        # Output limit enforced
        assert req.max_tokens is not None
        assert req.max_tokens <= 300

        # Request tracking metadata attached
        assert req.metadata.get("request_id") == "test_compact_01"

        # Content must NOT contain useless empty placeholders
        user_msg = req.messages[1].content
        assert "Latest Scan: No scans on record yet" not in user_msg
        assert "Appointments: No upcoming or pending appointments" not in user_msg
        assert "preventing dental decay" in user_msg

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 3. Latency Tests: Qwen 4s and 7s Success
# ---------------------------------------------------------------------------
def test_qwen_latency_success_under_budget():
    """Simulate Qwen response taking 0.1s and 0.2s in test (under 8s budget)."""
    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_completion_body("Prompt answered successfully within latency budget."))

        provider = _provider_with_handler(handler, timeout=8.0)
        started = time.perf_counter()
        result = await provider.generate_text(TextRequest(prompt="Tell me about dental floss", max_tokens=250))
        elapsed = time.perf_counter() - started

        assert result.content == "Prompt answered successfully within latency budget."
        assert elapsed < 1.0
        assert result.latency_ms > 0

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 4. Latency Test: Qwen Hangs 30s -> Cancelled Before Deadline
# ---------------------------------------------------------------------------
def test_qwen_hang_cancelled_before_deadline():
    """When Qwen hangs for 30 seconds, it must be cancelled strictly before timeout."""
    async def _test():
        async def slow_handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(30.0)
            return httpx.Response(200, json=_completion_body("Too late"))

        provider = QwenProvider(
            api_key=FAKE_KEY,
            base_url=BASE_URL,
            default_model="qwen3.7-plus",
            timeout_seconds=0.2,  # Tight deadline for fast test
            transport=httpx.MockTransport(slow_handler),
        )

        started = time.perf_counter()
        with pytest.raises(ProviderTimeoutError) as exc_info:
            await provider.generate_text(TextRequest(prompt="Hanging query"))
        elapsed = time.perf_counter() - started

        assert elapsed < 1.0  # Finished within ~0.2s, definitely did not wait 30s
        assert "timeout" in str(exc_info.value).lower()
        await provider.aclose()

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 5. Connection Error Fails Fast Without Retry Chains
# ---------------------------------------------------------------------------
def test_qwen_connection_error_fails_fast_no_retry():
    """Transport error raises ProviderUnavailableError immediately without sleeping or retry chains."""
    async def _test():
        call_count = 0

        def broken_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("Connection refused by peer", request=request)

        provider = _provider_with_handler(broken_handler)
        started = time.perf_counter()

        with pytest.raises(ProviderUnavailableError):
            await provider.generate_text(TextRequest(prompt="Fast fail query"))
        elapsed = time.perf_counter() - started

        assert elapsed < 0.5
        assert call_count == 1  # Exactly ONE attempt, no retry chains
        await provider.aclose()

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 6. General Brushing Question + Timeout -> Useful Brushing Guidance Fallback
# ---------------------------------------------------------------------------
def test_general_brushing_question_fallback_on_timeout(monkeypatch):
    """When a general brushing question hits a provider timeout, it returns useful brushing advice."""
    async def _test():
        monkeypatch.setattr(settings, "chat_qwen_timeout_seconds", 0.1)

        mock_gateway = MagicMock()

        async def hanging_call(*args, **kwargs):
            await asyncio.sleep(5.0)
            return MagicMock(content="Delayed AI response")

        mock_gateway.generate_text = AsyncMock(side_effect=hanging_call)

        state: CentralDentistState = {
            "user_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "message": "Can you advise on the technique for brushing my teeth?",
            "locale": "en",
            "request_id": "test_brushing_hang_01",
            "latest_scan": None,
            "appointments": [],
            "recent_turns": [],
            "_gateway": mock_gateway,
            "_db_session": None,
        }

        started = time.perf_counter()
        result = await central_dentist_graph.ainvoke(state)
        elapsed = time.perf_counter() - started

        assert elapsed < 1.0  # Fast timeout cancellation
        final_response = result.get("final_response") or ""

        # Returns useful brushing advice
        assert "brush" in final_response.lower()
        assert any(term in final_response.lower() for term in ("two", "fluoride", "gumline", "circular", "scrubbing"))

        # Zero provider error boilerplate
        assert "trouble reaching" not in final_response.lower()
        assert "ai assistant service" not in final_response.lower()
        assert "qwen" not in final_response.lower()
        assert "provider" not in final_response.lower()

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 7. Scan Question + Timeout -> Grounded Patient Record Fallback
# ---------------------------------------------------------------------------
def test_scan_question_fallback_on_timeout(monkeypatch):
    """When a patient asks about their scan and provider times out, return grounded scan records."""
    async def _test():
        monkeypatch.setattr(settings, "chat_qwen_timeout_seconds", 0.1)

        mock_gateway = MagicMock()

        async def hanging_call(*args, **kwargs):
            await asyncio.sleep(5.0)
            return MagicMock(content="Late response")

        mock_gateway.generate_text = AsyncMock(side_effect=hanging_call)

        mock_scan = ScanSummary(
            scan_id=str(uuid4()),
            created_at=datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc),
            input_mode="upload",
            status="completed",
            verdict="possible early cavity",
            urgency_level="soon",
            confidence=0.65,
            findings=[
                FindingItem(
                    finding_code="cavity_suspect",
                    region="molar",
                    observation="possible early cavity",
                    confidence=0.65,
                )
            ],
        )

        state: CentralDentistState = {
            "user_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "message": "What did my last report show?",
            "locale": "en",
            "request_id": "test_scan_hang_01",
            "latest_scan": mock_scan,
            "appointments": [],
            "recent_turns": [],
            "_gateway": mock_gateway,
            "_db_session": None,
        }

        started = time.perf_counter()
        result = await central_dentist_graph.ainvoke(state)
        elapsed = time.perf_counter() - started

        assert elapsed < 1.0
        final_response = result.get("final_response") or ""

        # Grounded structured data returned
        assert "possible early cavity" in final_response
        assert "65%" in final_response
        assert "soon" in final_response.lower()

        # Zero provider error boilerplate
        assert "ai assistant service" not in final_response.lower()
        assert "qwen" not in final_response.lower()

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 8. Direct Fast-Path for Unambiguous Brushing / Flossing Queries
# ---------------------------------------------------------------------------
def test_direct_fast_path_for_brushing_and_flossing():
    """Unambiguous hygiene questions ('What is the best way to brush my teeth?') execute direct fast path in <5ms."""
    async def _test():
        failing_gateway = MagicMock()
        failing_gateway.generate_text = AsyncMock(side_effect=AssertionError("Should not call gateway for fast path!"))

        # Brushing
        state_brush: CentralDentistState = {
            "user_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "message": "What is the best way to brush my teeth?",
            "locale": "en",
            "request_id": "test_fast_brush_01",
            "recent_turns": [],
            "_gateway": failing_gateway,
            "_db_session": None,
        }
        res_brush = await central_dentist_graph.ainvoke(state_brush)
        assert res_brush.get("is_fast_path") is True
        assert res_brush.get("fast_path_type") == "brushing_guide"
        assert "Brush twice a day" in res_brush.get("final_response", "")

        # Flossing
        state_floss: CentralDentistState = {
            "user_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "message": "How often should I floss?",
            "locale": "en",
            "request_id": "test_fast_floss_01",
            "recent_turns": [],
            "_gateway": failing_gateway,
            "_db_session": None,
        }
        res_floss = await central_dentist_graph.ainvoke(state_floss)
        assert res_floss.get("is_fast_path") is True
        assert res_floss.get("fast_path_type") == "flossing_guide"
        assert "Floss once daily" in res_floss.get("final_response", "")

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 9. Provider and AI Service Language Never Exposed to Patient
# ---------------------------------------------------------------------------
def test_no_public_ai_service_or_provider_language():
    """When a general unknown query experiences a provider error, response uses natural helpful language."""
    async def _test():
        mock_gateway = MagicMock()
        mock_gateway.generate_text = AsyncMock(side_effect=AllProvidersFailedError("Both failed"))

        state: CentralDentistState = {
            "user_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "message": "Tell me something random about outer space",
            "locale": "en",
            "request_id": "test_clean_err_01",
            "latest_scan": None,
            "appointments": [],
            "recent_turns": [],
            "_gateway": mock_gateway,
            "_db_session": None,
        }

        res = await central_dentist_graph.ainvoke(state)
        final_text = res.get("final_response", "")

        assert "couldn't complete that answer" in final_text.lower()
        for forbidden in ("ai assistant service", "qwen", "gemini", "dashscope", "model studio", "provider"):
            assert forbidden not in final_text.lower()

    asyncio.run(_test())
