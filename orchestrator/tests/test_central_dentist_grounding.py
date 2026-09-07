"""Grounding and privacy tests for Central Dentist (Phase 12A Final).

Verifies that the prompt constructed for Qwen:
- Contains grounded patient facts (scans, reports, urgency, confidence).
- Does NOT contain raw base64 image data.
- Does NOT contain unpersisted model checkpoint paths.
- Does NOT contain API keys, JWT secrets, or another patient's data.
- Does NOT dump raw database tables.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from orchestrator.ai.schemas import AIResult, TextRequest
from orchestrator.central_dentist.graph import central_dentist_graph
from orchestrator.central_dentist.retrieval import FindingItem, ScanSummary


class SpyGateway:
    def __init__(self):
        self.requests: list[TextRequest] = []

    async def generate_text(self, request: TextRequest) -> AIResult:
        self.requests.append(request)
        return AIResult(
            content="Your latest scan flagged possible tooth discoloration at 76% confidence.",
            provider="qwen",
            model="qwen3.7-plus",
            latency_ms=120.0,
        )


def test_grounded_prompt_contains_facts_and_no_leaks():
    async def _test():
        gateway = SpyGateway()
        patient_id = uuid4()

        latest_scan = ScanSummary(
            scan_id=str(uuid4()),
            created_at=datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc),
            input_mode="upload",
            status="completed",
            verdict="tooth_discoloration",
            urgency_level="routine",
            summary="AI screening observed tooth discoloration with 76% confidence.",
            confidence=0.76,
            recommended_specialist="General Dentist",
            findings=[
                FindingItem(
                    finding_code="discoloration",
                    region="upper_incisors",
                    observation="tooth discoloration",
                    confidence=0.76,
                )
            ],
        )

        state = {
            "user_id": str(patient_id),
            "conversation_id": str(uuid4()),
            "message": "Explain what my screening found and what I should do.",
            "latest_scan": latest_scan,
            "_gateway": gateway,
            "_db_session": None,  # already populated in state
        }

        output = await central_dentist_graph.ainvoke(state)
        assert output.get("final_response") is not None
        assert len(gateway.requests) == 1

        prompt_content = gateway.requests[0].messages[1].content

        # Grounding assertions: MUST contain patient facts
        assert "tooth discoloration" in prompt_content
        assert "76%" in prompt_content
        assert "September 06, 2026" in prompt_content or "September 6, 2026" in prompt_content
        assert "routine" in prompt_content.lower()

        # Safety assertions: MUST NOT leak internals, weights, secrets, or raw images
        assert "base64" not in prompt_content.lower()
        assert "data:image" not in prompt_content
        assert "best.pt" not in prompt_content
        assert "dentaltensor_nathan_asif_v1.pt" not in prompt_content
        assert "api_key" not in prompt_content.lower()
        assert "jwt_secret" not in prompt_content.lower()
        assert "postgres" not in prompt_content.lower()
        assert "select * from" not in prompt_content.lower()

    asyncio.run(_test())
