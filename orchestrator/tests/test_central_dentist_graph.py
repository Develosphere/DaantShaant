"""End-to-end LangGraph execution tests for Central Dentist (Phase 12A Final)."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from orchestrator.ai.schemas import AIResult, TextRequest
from orchestrator.central_dentist.graph import central_dentist_graph
from orchestrator.central_dentist.retrieval import FindingItem, ScanSummary
from orchestrator.db.models import ClinicalReport, Conversation, Message, Scan


class MockGateway:
    def __init__(self, content: str = "Your latest scan flagged discoloration."):
        self.content = content
        self.requests = []

    async def generate_text(self, request: TextRequest) -> AIResult:
        self.requests.append(request)
        return AIResult(
            content=self.content,
            provider="qwen",
            model="qwen3.7-plus",
            latency_ms=150.0,
        )


def test_central_dentist_graph_end_to_end():
    async def _test():
        user_id = uuid4()
        conv_id = uuid4()
        gateway = MockGateway(content="Your latest scan flagged possible tooth discoloration at 76%.")

        # Mock DB session and conversation repository
        session = AsyncMock()
        mock_scan = Scan(
            id=uuid4(),
            patient_user_id=user_id,
            status="completed",
            created_at=datetime.now(timezone.utc),
        )
        mock_report = ClinicalReport(
            id=uuid4(),
            scan_id=mock_scan.id,
            patient_user_id=user_id,
            verdict="tooth discoloration",
            urgency_level="routine",
            created_at=datetime.now(timezone.utc),
        )
        mock_conv = Conversation(id=conv_id, patient_user_id=user_id, title="Test Chat")
        mock_msg = Message(id=uuid4(), conversation_id=conv_id, role="assistant", content="test response")

        def mock_execute(query):
            res = MagicMock()
            res.first.return_value = (mock_scan, mock_report)
            res.all.return_value = [(mock_scan, mock_report)]
            res.scalars.return_value = []
            res.scalar_one_or_none.return_value = mock_conv
            return res

        session.execute = AsyncMock(side_effect=mock_execute)
        session.add = MagicMock()
        session.flush = AsyncMock()

        state = {
            "user_id": str(user_id),
            "conversation_id": str(conv_id),
            "message": "What did my last scan say?",
            "locale": "en",
            "_db_session": session,
            "_gateway": gateway,
        }

        output = await central_dentist_graph.ainvoke(state)

        assert output.get("intent") == "SCAN_LATEST"
        assert output.get("final_response") is not None
        assert "discoloration" in output.get("final_response", "").lower()

        # Verify stage timing instrumentation
        latency = output.get("latency_metadata", {})
        assert "chat.nlp_ms" in latency
        assert "chat.retrieval_ms" in latency
        assert "chat.total_ms" in latency
        assert latency["chat.nlp_ms"] < 50.0  # target: <50ms

    asyncio.run(_test())
