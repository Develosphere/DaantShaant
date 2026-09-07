"""Concurrency and isolation audit for Central Dentist (Phase 12E).

Proves:
- Simultaneous chat requests do NOT cross-talk or overwrite each other's prompts.
- Running Question A (diabetes) and Question B (zirconia implants) concurrently returns
  strictly isolated responses matching their respective prompts.
- No shared mutable prompt or context state leaks between concurrent tasks.
"""

import asyncio
from uuid import uuid4

import pytest

from orchestrator.ai.schemas import AIResult, TextRequest
from orchestrator.central_dentist import CentralDentistState, central_dentist_graph


class EchoMockGateway:
    """Mock gateway that mirrors key topics from the prompt back in the response."""

    def __init__(self):
        self.received_prompts: list[str] = []
        self._lock = asyncio.Lock()

    async def generate_text(self, request: TextRequest) -> AIResult:
        # Simulate non-trivial async latency to stress concurrency
        await asyncio.sleep(0.05)
        user_prompt = request.messages[1].content
        async with self._lock:
            self.received_prompts.append(user_prompt)

        if "zirconia" in user_prompt.lower():
            content = "ZIRCONIA_IMPLANT_RESPONSE: Low thermal conductivity and phase transformation affect fatigue."
        elif "diabetes" in user_prompt.lower():
            content = "DIABETES_GUM_RESPONSE: Glycemic levels elevate inflammatory cytokines in periodontal tissue."
        else:
            content = "GENERIC_RESPONSE"

        return AIResult(
            content=content,
            provider="qwen",
            model="qwen3.7-flash",
            latency_ms=50.0,
        )


def test_concurrent_chat_requests_do_not_crosstalk():
    """Verify concurrent requests A and B are strictly isolated with zero prompt cross-talk."""
    async def _test():
        gateway = EchoMockGateway()

        user_a_id = uuid4()
        user_b_id = uuid4()
        conv_a = uuid4()
        conv_b = uuid4()

        state_a: CentralDentistState = {
            "user_id": str(user_a_id),
            "conversation_id": str(conv_a),
            "message": "What causes diabetes-related gum inflammation?",
            "recent_turns": [],
            "_gateway": gateway,
            "_db_session": None,
        }

        state_b: CentralDentistState = {
            "user_id": str(user_b_id),
            "conversation_id": str(conv_b),
            "message": "Explain zirconia implant fatigue under occlusal loading.",
            "recent_turns": [],
            "_gateway": gateway,
            "_db_session": None,
        }

        # Run both simultaneously
        res_a, res_b = await asyncio.gather(
            central_dentist_graph.ainvoke(state_a),
            central_dentist_graph.ainvoke(state_b),
        )

        resp_a = res_a.get("final_response", "")
        resp_b = res_b.get("final_response", "")

        # Assert response A strictly corresponds to Question A
        assert "DIABETES_GUM_RESPONSE" in resp_a
        assert "zirconia" not in resp_a.lower()
        assert "implant" not in resp_a.lower()

        # Assert response B strictly corresponds to Question B
        assert "ZIRCONIA_IMPLANT_RESPONSE" in resp_b
        assert "diabetes" not in resp_b.lower()
        assert "glycemic" not in resp_b.lower()

        # Assert both prompts in gateway were unique and independent
        assert len(gateway.received_prompts) == 2
        prompt_texts = [p.lower() for p in gateway.received_prompts]
        assert any("diabetes" in p and "zirconia" not in p for p in prompt_texts)
        assert any("zirconia" in p and "diabetes" not in p for p in prompt_texts)

    asyncio.run(_test())
