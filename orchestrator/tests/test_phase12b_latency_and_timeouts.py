"""Phase 12B tests for Central Dentist latency budgets, fast-paths, Qwen timeouts, and DB timeout protection."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from orchestrator.central_dentist.graph import (
    CentralDentistState,
    central_dentist_graph,
)
from orchestrator.central_dentist.retrieval import FindingItem, ScanSummary
from orchestrator.chat_schemas import MessageSender, SendMessageRequest
from orchestrator.chat_service import send_message
from orchestrator.config import settings


@pytest.fixture
def mock_scan():
    return ScanSummary(
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


def test_greeting_fast_path_latency():
    """Greeting must execute fast path, NOT call Qwen, and complete in milliseconds."""
    async def _test():
        mock_gateway = MagicMock()
        mock_gateway.generate_text = AsyncMock()

        state: CentralDentistState = {
            "user_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "message": "Hi",
            "locale": "en",
            "request_id": "test_greeting_01",
            "recent_turns": [],
            "_gateway": mock_gateway,
            "_db_session": None,
        }

        t0 = asyncio.get_event_loop().time()
        result = await central_dentist_graph.ainvoke(state)
        duration = asyncio.get_event_loop().time() - t0

        # Fast path verified
        assert result.get("is_fast_path") is True
        assert result.get("fast_path_type") == "greeting"
        assert "Hello" in (result.get("final_response") or "")

        # Zero Qwen calls
        assert mock_gateway.generate_text.call_count == 0

        # Timing verified (< 1.0 second)
        assert duration < 1.0
        latency = result.get("latency_metadata", {})
        assert latency.get("chat.qwen_ms") == 0.0

    asyncio.run(_test())


def test_confidence_fast_path_latency(mock_scan):
    """'What was the confidence?' must execute fast path without Qwen when scan is available."""
    async def _test():
        mock_gateway = MagicMock()
        mock_gateway.generate_text = AsyncMock()

        state: CentralDentistState = {
            "user_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "message": "What was the confidence?",
            "locale": "en",
            "request_id": "test_conf_01",
            "latest_scan": mock_scan,
            "recent_turns": [],
            "_gateway": mock_gateway,
            "_db_session": None,
        }

        t0 = asyncio.get_event_loop().time()
        result = await central_dentist_graph.ainvoke(state)
        duration = asyncio.get_event_loop().time() - t0

        assert result.get("is_fast_path") is True
        assert result.get("fast_path_type") == "confidence"
        assert "65%" in (result.get("final_response") or "")

        # Zero Qwen calls
        assert mock_gateway.generate_text.call_count == 0
        assert duration < 1.0

    asyncio.run(_test())


def test_qwen_timeout_cancellation_and_fallback(mock_scan, monkeypatch):
    """When Qwen hangs beyond chat_qwen_timeout_seconds, it must cancel and return grounded fallback."""
    async def _test():
        monkeypatch.setattr(settings, "chat_qwen_timeout_seconds", 0.3)

        mock_gateway = MagicMock()

        async def hanging_call(*args, **kwargs):
            await asyncio.sleep(5.0)
            return MagicMock(content="Delayed AI response")

        mock_gateway.generate_text = AsyncMock(side_effect=hanging_call)

        state: CentralDentistState = {
            "user_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "message": "Can you explain my last scan report in detail?",
            "locale": "en",
            "request_id": "test_qwen_hang_01",
            "latest_scan": mock_scan,
            "recent_turns": [],
            "_gateway": mock_gateway,
            "_db_session": None,
        }

        t0 = asyncio.get_event_loop().time()
        result = await central_dentist_graph.ainvoke(state)
        elapsed = asyncio.get_event_loop().time() - t0

        # Must finish around 0.3s timeout, NOT wait 5.0s
        assert elapsed < 1.5
        final_response = result.get("final_response") or ""
        # Grounded fallback returned using scan context
        assert "September 07, 2026" in final_response or "possible early cavity" in final_response

    asyncio.run(_test())


def test_global_deadline_in_chat_service(monkeypatch):
    """Global request deadline must abort execution and rollback DB session if graph exceeds 12s."""
    async def _test():
        monkeypatch.setattr(settings, "chat_request_timeout_seconds", 0.4)

        mock_session = AsyncMock()

        async def slow_graph(*args, **kwargs):
            await asyncio.sleep(5.0)
            return {"final_response": "Should not reach"}

        with patch(
            "orchestrator.chat_service.central_dentist_graph.ainvoke",
            side_effect=slow_graph,
        ):
            with patch("orchestrator.chat_service.ConversationRepository") as mock_repo_cls:
                mock_repo = MagicMock()
                mock_conv = MagicMock(id=uuid4(), title="Test Conversation")
                mock_repo.get_owned = AsyncMock(return_value=mock_conv)
                mock_repo.create = AsyncMock(return_value=mock_conv)
                mock_repo.list_messages = AsyncMock(return_value=[])
                mock_msg = MagicMock(id=uuid4(), role="user", content="Hello", created_at=datetime.now(timezone.utc))
                mock_repo.add_message = AsyncMock(return_value=mock_msg)
                mock_repo_cls.return_value = mock_repo

                t0 = asyncio.get_event_loop().time()
                req = SendMessageRequest(text="Explain my report")
                resp = await send_message(req, uuid4(), mock_session)
                elapsed = asyncio.get_event_loop().time() - t0

                # Did not hang for 5s
                assert elapsed < 1.5
                assert "couldn't complete that answer" in resp.assistant_message.text.lower()
                # Session rollback was attempted
                assert mock_session.rollback.called

    asyncio.run(_test())


def test_db_timeout_returns_controlled_503(monkeypatch):
    """If DB connection hangs or fails with OperationalError, FastAPI route returns 503."""
    async def _test():
        from orchestrator.main import send_chat_message

        mock_session = AsyncMock()

        with patch("orchestrator.main.send_message", side_effect=OperationalError("connection timeout", None, None)):
            req = SendMessageRequest(text="Hello")
            with pytest.raises(HTTPException) as exc_info:
                await send_chat_message(req, {"user_id": uuid4()}, mock_session)

            assert exc_info.value.status_code == 503
            assert "temporarily unavailable" in exc_info.value.detail

    asyncio.run(_test())
