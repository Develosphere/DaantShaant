"""Semantic integrity and context isolation tests for Central Dentist (Phase 12E).

Verifies:
1. Standalone dental questions (e.g. zirconia vs titanium implants) are completely
   isolated from unrelated prior conversation history (e.g. diabetes, AGEs/RAGE).
2. Standalone dental questions do not inject patient records unless explicitly referenced.
3. Curated knowledge is only injected when relevant; poor relevance returns None.
4. Anaphoric follow-up references retain scan and conversational context correctly.
5. Topic-shift works: scan inquiry -> follow-up -> standalone topic transition.
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from orchestrator.ai.schemas import AIResult, TextRequest
from orchestrator.central_dentist import (
    CentralDentistIntent,
    CentralDentistState,
    analyze_message,
    central_dentist_graph,
    has_personal_record_reference,
    is_conversational_follow_up,
)
from orchestrator.central_dentist.knowledge import lookup_dental_knowledge
from orchestrator.central_dentist.retrieval import FindingItem, ScanSummary


class RecordingSpyGateway:
    """Mock AI gateway that captures outgoing TextRequests without hitting live APIs."""

    def __init__(self, response_text: str = "Mock answer"):
        self.requests: list[TextRequest] = []
        self.response_text = response_text

    async def generate_text(self, request: TextRequest) -> AIResult:
        self.requests.append(request)
        return AIResult(
            content=self.response_text,
            provider="qwen",
            model="qwen3.7-flash",
            latency_ms=45.0,
        )


IMPLANT_QUESTION = (
    "Explain the mechanical and biological mechanisms behind the aseptic "
    "loosening of zirconia versus titanium dental implants in patients with "
    "a history of bruxism (severe teeth grinding).\n\n"
    "Specifically, address how micro-motion at the bone-implant interface "
    "triggers macrophage activation and osteoclastogenesis. Then, contrast "
    "how zirconia’s low thermal conductivity and susceptibility to "
    "low-temperature degradation (phase transformation from tetragonal to "
    "monoclinic) affect its long-term stress-distribution and fatigue limits "
    "under heavy occlusal loading compared to titanium's elastic modulus."
)


def test_implant_question_nlp_classification():
    """Verify that the complex implant question classifies as DENTAL_KNOWLEDGE."""
    nlp_res = analyze_message(IMPLANT_QUESTION)
    assert nlp_res.intent == CentralDentistIntent.DENTAL_KNOWLEDGE
    assert not has_personal_record_reference(IMPLANT_QUESTION)
    assert not is_conversational_follow_up(IMPLANT_QUESTION)


def test_exact_implant_question_isolation_from_diabetes_history():
    """Exact Phase 12E regression: standalone implant question must NOT contain diabetes context."""
    async def _test():
        gateway = RecordingSpyGateway(
            response_text="Zirconia and titanium implants exhibit distinct biomechanical behaviors."
        )
        patient_id = uuid4()
        conv_id = uuid4()

        # Simulate prior turn discussing diabetes in the same conversation
        prior_turns = [
            {
                "role": "user",
                "content": "Why can diabetes worsen periodontal disease?",
            },
            {
                "role": "assistant",
                "content": (
                    "Type 2 diabetes promotes accumulation of Advanced Glycation End-products (AGEs/RAGE), "
                    "which accelerates periodontal breakdown, impairs collagen synthesis, and elevates "
                    "bone resorption. Strict glycemic control and targeted antibiotics help manage it."
                ),
            },
        ]

        # Simulate existing patient scan with gingivitis finding
        latest_scan = ScanSummary(
            scan_id=str(uuid4()),
            created_at=datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc),
            input_mode="upload",
            status="completed",
            verdict="gingivitis_signs",
            urgency_level="routine",
            summary="AI screening observed signs of gum inflammation.",
            confidence=0.82,
            findings=[
                FindingItem(
                    finding_code="gingivitis_signs",
                    region="lower_anterior",
                    observation="Visible gum inflammation",
                    confidence=0.82,
                )
            ],
        )

        state: CentralDentistState = {
            "user_id": str(patient_id),
            "conversation_id": str(conv_id),
            "message": IMPLANT_QUESTION,
            "recent_turns": prior_turns,
            "latest_scan": latest_scan,
            "_gateway": gateway,
            "_db_session": None,
        }

        output = await central_dentist_graph.ainvoke(state)
        assert output.get("final_response") is not None
        assert len(gateway.requests) == 1

        request = gateway.requests[0]
        user_prompt = request.messages[1].content

        # MUST contain the core query terminology
        assert "zirconia" in user_prompt.lower()
        assert "titanium" in user_prompt.lower()
        assert "aseptic loosening" in user_prompt.lower()
        assert "bruxism" in user_prompt.lower()
        assert "micro-motion" in user_prompt.lower() or "micromotion" in user_prompt.lower()
        assert "macrophage" in user_prompt.lower()
        assert "osteoclastogenesis" in user_prompt.lower()

        # MUST NOT contain unrelated prior conversation context
        assert "diabetes" not in user_prompt.lower()
        assert "age/rage" not in user_prompt.lower()
        assert "glycemic" not in user_prompt.lower()
        assert "antibiotics" not in user_prompt.lower()
        assert "collagen synthesis" not in user_prompt.lower()

        # MUST NOT inject unrelated patient scan record
        assert "PATIENT RECORD" not in user_prompt
        assert "gingivitis_signs" not in user_prompt.lower()
        assert "gum inflammation" not in user_prompt.lower()

        # Telemetry verification
        sources = output.get("context_sources", [])
        assert "conversation_history" not in sources
        assert "latest_scan" not in sources

    asyncio.run(_test())


def test_knowledge_relevance_threshold():
    """Curated guidelines only trigger when query is genuinely relevant; unrelated queries return None."""
    # 1. Unrelated domain queries must return None
    assert lookup_dental_knowledge("Explain zirconia versus titanium implants") is None
    assert lookup_dental_knowledge("What causes temporomandibular joint pain?") is None
    assert lookup_dental_knowledge("How does a root canal remove infected pulp?") is None
    assert lookup_dental_knowledge("Why can diabetes worsen periodontal disease?") is None

    # 2. Curated hygiene topics must match appropriately
    brushing = lookup_dental_knowledge("How should I brush my teeth properly?")
    assert brushing is not None
    assert "soft-bristled toothbrush" in brushing

    flossing = lookup_dental_knowledge("What is the best way to floss?")
    assert flossing is not None
    assert "C-shape" in flossing

    # 3. Unrelated query with active_finding must NOT return guideline unless follow-up
    unrelated_with_finding = lookup_dental_knowledge(
        "Explain zirconia implant fatigue under bruxism",
        finding_key="gingivitis_signs",
        allow_finding_fallback=False,
    )
    assert unrelated_with_finding is None


def test_follow_up_preservation_and_topic_shift_sequence():
    """Verifies Turn 1 (scan) -> Turn 2 (follow-up with history) -> Turn 3 (fresh topic isolation)."""
    async def _test():
        gateway = RecordingSpyGateway()
        patient_id = uuid4()
        conv_id = uuid4()

        scan = ScanSummary(
            scan_id=str(uuid4()),
            created_at=datetime(2026, 9, 7, 10, 0, 0, tzinfo=timezone.utc),
            input_mode="upload",
            status="completed",
            verdict="cavity_suspect",
            urgency_level="soon",
            summary="Screening flagged possible tooth decay.",
            confidence=0.88,
            findings=[
                FindingItem(
                    finding_code="cavity_suspect",
                    region="upper_molar",
                    observation="possible cavity",
                    confidence=0.88,
                )
            ],
        )

        # TURN 1: "What did my latest scan show?"
        state_turn1: CentralDentistState = {
            "user_id": str(patient_id),
            "conversation_id": str(conv_id),
            "message": "What did my latest scan show?",
            "latest_scan": scan,
            "recent_turns": [],
            "_gateway": gateway,
            "_db_session": None,
        }
        await central_dentist_graph.ainvoke(state_turn1)
        prompt_turn1 = gateway.requests[-1].messages[1].content
        assert "PATIENT RECORD" in prompt_turn1
        assert "cavity" in prompt_turn1.lower()

        # TURN 2: "Why did it flag that?" (Follow-up reference)
        turns_after_turn1 = [
            {"role": "user", "content": "What did my latest scan show?"},
            {"role": "assistant", "content": "Your latest screening flagged a possible cavity."},
        ]
        state_turn2: CentralDentistState = {
            "user_id": str(patient_id),
            "conversation_id": str(conv_id),
            "message": "Why did it flag that?",
            "latest_scan": scan,
            "recent_turns": turns_after_turn1,
            "_gateway": gateway,
            "_db_session": None,
        }
        await central_dentist_graph.ainvoke(state_turn2)
        prompt_turn2 = gateway.requests[-1].messages[1].content
        # Follow-up MUST include recent turns and scan
        assert "RECENT TURNS" in prompt_turn2
        assert "PATIENT RECORD" in prompt_turn2

        # TURN 3: "How does a dental implant integrate with bone?" (New standalone topic)
        turns_after_turn2 = turns_after_turn1 + [
            {"role": "user", "content": "Why did it flag that?"},
            {"role": "assistant", "content": "The visual screening model detected an area of enamel demineralization."},
        ]
        state_turn3: CentralDentistState = {
            "user_id": str(patient_id),
            "conversation_id": str(conv_id),
            "message": "How does a dental implant integrate with bone?",
            "latest_scan": scan,
            "recent_turns": turns_after_turn2,
            "_gateway": gateway,
            "_db_session": None,
        }
        await central_dentist_graph.ainvoke(state_turn3)
        prompt_turn3 = gateway.requests[-1].messages[1].content
        # Turn 3 is a NEW standalone topic: old scan context and prior turns MUST NOT appear!
        assert "PATIENT RECORD" not in prompt_turn3
        assert "RECENT TURNS" not in prompt_turn3
        assert "cavity" not in prompt_turn3.lower()
        assert "demineralization" not in prompt_turn3.lower()
        assert "implant" in prompt_turn3.lower()

    asyncio.run(_test())
