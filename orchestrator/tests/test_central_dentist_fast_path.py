"""Fast-path deterministic evaluation unit tests.

Verifies that simple factual queries (scan date, appointment date, confidence %,
urgency level) are resolved deterministically in < 5ms without calling Qwen or any LLM.
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from orchestrator.ai.base import AIProvider
from orchestrator.ai.schemas import AIResult, TextRequest
from orchestrator.central_dentist.graph import central_dentist_graph
from orchestrator.central_dentist.retrieval import AppointmentSummary, ScanSummary


class FailingSpyGateway:
    def __init__(self):
        self.invoked = False

    async def generate_text(self, request: TextRequest) -> AIResult:
        self.invoked = True
        raise AssertionError("Qwen should NOT be called for fast-path deterministic requests!")


def test_fast_path_scan_date_bypasses_qwen():
    async def _test():
        gateway = FailingSpyGateway()
        patient_id = uuid4()

        latest_scan = ScanSummary(
            scan_id=str(uuid4()),
            created_at=datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc),
            input_mode="upload",
            status="completed",
            verdict="tooth_discoloration",
            urgency_level="routine",
            summary="Summary of scan.",
            confidence=0.76,
        )

        state = {
            "user_id": str(patient_id),
            "conversation_id": str(uuid4()),
            "message": "When was my latest scan?",
            "latest_scan": latest_scan,
            "_gateway": gateway,
            "_db_session": None,
        }

        output = await central_dentist_graph.ainvoke(state)
        assert not gateway.invoked
        assert output.get("is_fast_path") is True
        resp = output.get("final_response", "")
        assert "September 06, 2026" in resp or "September 6, 2026" in resp

    asyncio.run(_test())


def test_fast_path_appointment_date_bypasses_qwen():
    async def _test():
        gateway = FailingSpyGateway()
        patient_id = uuid4()

        appt = AppointmentSummary(
            appointment_id=str(uuid4()),
            dentist_id=str(uuid4()),
            dentist_name="Dr. Sarah Khan",
            clinic_name="Karachi Dental Care",
            clinic_address="Clifton, Karachi",
            clinic_phone="+92-21-1234567",
            status="confirmed",
            preferred_time="Tuesday at 3:00 PM",
            issue="Routine checkup",
            created_at=datetime.now(timezone.utc),
        )

        state = {
            "user_id": str(patient_id),
            "conversation_id": str(uuid4()),
            "message": "When is my appointment?",
            "appointments": [appt],
            "_gateway": gateway,
            "_db_session": None,
        }

        output = await central_dentist_graph.ainvoke(state)
        assert not gateway.invoked
        assert output.get("is_fast_path") is True
        resp = output.get("final_response", "")
        assert "Dr. Sarah Khan" in resp
        assert "Tuesday at 3:00 PM" in resp
        assert "confirmed" in resp

    asyncio.run(_test())


def test_fast_path_confidence_bypasses_qwen():
    async def _test():
        gateway = FailingSpyGateway()
        patient_id = uuid4()

        latest_scan = ScanSummary(
            scan_id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            input_mode="upload",
            status="completed",
            verdict="tooth discoloration",
            urgency_level="routine",
            confidence=0.76,
        )

        state = {
            "user_id": str(patient_id),
            "conversation_id": str(uuid4()),
            "message": "What was the confidence?",
            "latest_scan": latest_scan,
            "_gateway": gateway,
            "_db_session": None,
        }

        output = await central_dentist_graph.ainvoke(state)
        assert not gateway.invoked
        assert output.get("is_fast_path") is True
        resp = output.get("final_response", "")
        assert "76%" in resp

    asyncio.run(_test())


def test_fast_path_urgency_bypasses_qwen():
    async def _test():
        gateway = FailingSpyGateway()
        patient_id = uuid4()

        latest_scan = ScanSummary(
            scan_id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            input_mode="upload",
            status="completed",
            verdict="calculus",
            urgency_level="soon",
        )

        state = {
            "user_id": str(patient_id),
            "conversation_id": str(uuid4()),
            "message": "What is my urgency?",
            "latest_scan": latest_scan,
            "_gateway": gateway,
            "_db_session": None,
        }

        output = await central_dentist_graph.ainvoke(state)
        assert not gateway.invoked
        assert output.get("is_fast_path") is True
        resp = output.get("final_response", "")
        assert "Soon" in resp or "soon" in resp

    asyncio.run(_test())
