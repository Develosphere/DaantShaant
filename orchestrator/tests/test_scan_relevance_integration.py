"""Tests for Phase 2B.2 - production semantic-relevance integration.

Snapshot and upload both route through ``POST /v1/teeth/analyze`` -> the shared
``run_scan_with_relevance`` helper, and the live WebSocket frame handler calls
that same helper.  These tests therefore exercise the single integration point
for all three scan modes.

Fake relevance + fake clinical analyzer only: ZERO external Qwen/Gemini calls,
no real images, no network, no database.
"""

from __future__ import annotations

import asyncio
import inspect
import uuid

import pytest

from dantshaant_common.schemas import (
    ActionTrigger,
    AnalyzeResponse,
    ConditionLabel,
    DiagnoseResponse,
    Severity,
    VisualFinding,
)
from orchestrator import live_session, pipeline
from orchestrator.ai.exceptions import AllProvidersFailedError
from orchestrator.clinical.relevance import DentalRelevanceResult
from orchestrator.pipeline import TeethAnalyzePipelineRequest, run_scan_with_relevance

FAKE_IMAGE_B64 = "SU1BR0VfQkFTRTY0X1NFbnRpbmVsX1NVQ0hfQVNGM0tFMg=="

_ACTION = {"relevant": "continue", "retake": "retake", "unrelated": "reject"}


def _run(coro):
    return asyncio.run(coro)


def _relevance(
    classification: str,
    *,
    confidence: float = 0.9,
    relevance_score: float = 0.9,
    visible_regions: list[str] | None = None,
    reason: str = "ok",
    retake_reason: str | None = None,
) -> DentalRelevanceResult:
    return DentalRelevanceResult(
        classification=classification,  # type: ignore[arg-type]
        is_dental_relevant=classification == "relevant",
        confidence=confidence,
        relevance_score=relevance_score,
        visible_regions=visible_regions if visible_regions is not None else ["teeth"],
        reason=reason,
        retake_reason=retake_reason,
        recommended_action=_ACTION[classification],  # type: ignore[return-value]
    )


def _pipeline_response() -> pipeline.TeethAnalyzePipelineResponse:
    uid = uuid.uuid4()
    analysis = AnalyzeResponse(
        user_id=uid,
        findings=[VisualFinding(label="plaque", confidence=0.6)],
        overall_quality_score=0.8,
        model_id="stub-v0",
    )
    diagnosis = DiagnoseResponse(
        user_id=uid,
        analysis_id=uuid.uuid4(),
        condition_label=ConditionLabel.HEALTHY,
        severity=Severity.NONE,
        confidence=0.7,
        confidence_threshold=0.5,
        meets_threshold=True,
        action_trigger=ActionTrigger.MAINTENANCE_REMINDER,
    )
    return pipeline.TeethAnalyzePipelineResponse(analysis=analysis, diagnosis=diagnosis)


class SpyAnalyzer:
    """Stands in for the clinical Teeth Analyzer pipeline boundary."""

    def __init__(self, response=None) -> None:
        self.calls = 0
        self.response = response or _pipeline_response()

    async def __call__(self, request: TeethAnalyzePipelineRequest):
        self.calls += 1
        return self.response


class FakeRelevance:
    """Injectable relevance evaluator returning a canned result or raising."""

    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    async def __call__(self, image_base64, content_type, gateway=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


def _make_session() -> live_session.LiveSessionState:
    return live_session.LiveSessionState(
        session_id=uuid.uuid4(), user_id=uuid.uuid4(), locale="en"
    )


def _patch(monkeypatch, relevance_fake, analyzer_spy):
    monkeypatch.setattr(pipeline, "evaluate_dental_relevance", relevance_fake)
    monkeypatch.setattr(pipeline, "run_teeth_analysis_pipeline", analyzer_spy)
    # Keep the live event logger off the database/network.
    monkeypatch.setattr(live_session, "log_event", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# SNAPSHOT / UPLOAD (shared helper)
# ---------------------------------------------------------------------------
def test_relevant_image_calls_clinical_analyzer(monkeypatch):
    rel = FakeRelevance(result=_relevance("relevant"))
    spy = SpyAnalyzer()
    _patch(monkeypatch, rel, spy)

    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64)
        )
    )

    assert spy.calls == 1
    assert outcome.status == "analyzed"
    assert outcome.analysis is not None and outcome.diagnosis is not None


def test_retake_image_skips_clinical_analyzer(monkeypatch):
    rel = FakeRelevance(
        result=_relevance("retake", relevance_score=0.4, retake_reason="mouth_too_far")
    )
    spy = SpyAnalyzer()
    _patch(monkeypatch, rel, spy)

    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64)
        )
    )

    assert spy.calls == 0  # no expensive clinical vision
    assert outcome.status == "retake"
    assert outcome.analysis is None and outcome.diagnosis is None
    assert outcome.relevance.recommended_action == "retake"
    assert outcome.relevance.retake_reason == "mouth_too_far"


def test_unrelated_image_skips_clinical_analyzer(monkeypatch):
    rel = FakeRelevance(
        result=_relevance("unrelated", relevance_score=0.05, visible_regions=["laptop"])
    )
    spy = SpyAnalyzer()
    _patch(monkeypatch, rel, spy)

    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64)
        )
    )

    assert spy.calls == 0
    assert outcome.status == "rejected"
    assert outcome.relevance.recommended_action == "reject"


def test_provider_failure_is_not_treated_as_unrelated(monkeypatch):
    rel = FakeRelevance(error=AllProvidersFailedError("both providers down"))
    spy = SpyAnalyzer()
    _patch(monkeypatch, rel, spy)

    with pytest.raises(AllProvidersFailedError):
        _run(
            run_scan_with_relevance(
                TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64)
            )
        )
    assert spy.calls == 0  # failure did not silently proceed nor fabricate a verdict


def test_outcome_exposes_relevance_action_and_reason(monkeypatch):
    rel = FakeRelevance(result=_relevance("unrelated", reason="no oral region", visible_regions=["room"]))
    _patch(monkeypatch, rel, SpyAnalyzer())

    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64)
        )
    )

    assert outcome.relevance.classification == "unrelated"
    assert outcome.relevance.recommended_action == "reject"
    assert outcome.relevance.reason == "no oral region"


# ---------------------------------------------------------------------------
# LIVE (process_frame)
# ---------------------------------------------------------------------------
def test_live_relevant_frame_analyzes(monkeypatch):
    rel = FakeRelevance(result=_relevance("relevant"))
    spy = SpyAnalyzer()
    _patch(monkeypatch, rel, spy)
    session = _make_session()
    session.last_frame_at = 0.0
    ws = FakeWS()

    _run(live_session.process_frame(ws, session, FAKE_IMAGE_B64, seq=1))

    assert spy.calls == 1
    assert session.frames_analyzed == 1
    assert session.best is not None


def test_live_retake_frame_skips_analyzer(monkeypatch):
    rel = FakeRelevance(result=_relevance("retake", retake_reason="too_far"))
    spy = SpyAnalyzer()
    _patch(monkeypatch, rel, spy)
    session = _make_session()
    session.last_frame_at = 0.0
    ws = FakeWS()

    _run(live_session.process_frame(ws, session, FAKE_IMAGE_B64, seq=2))

    assert spy.calls == 0
    assert session.frames_analyzed == 0
    assert any(m.get("type") == "relevance.retake" for m in ws.sent)


def test_live_unrelated_frame_skips_analyzer(monkeypatch):
    rel = FakeRelevance(result=_relevance("unrelated", visible_regions=["desk"]))
    spy = SpyAnalyzer()
    _patch(monkeypatch, rel, spy)
    session = _make_session()
    session.last_frame_at = 0.0
    ws = FakeWS()

    _run(live_session.process_frame(ws, session, FAKE_IMAGE_B64, seq=3))

    assert spy.calls == 0
    assert any(m.get("type") == "relevance.rejected" for m in ws.sent)


def test_live_bad_frame_does_not_error_and_later_frame_is_analyzable(monkeypatch):
    # A bad frame must not emit a session-killer error, and a later relevant
    # frame must still go through clinical analysis on the same session.
    spy = SpyAnalyzer()
    bad = FakeRelevance(result=_relevance("unrelated", visible_regions=["floor"]))
    _patch(monkeypatch, bad, spy)
    session = _make_session()
    session.last_frame_at = 0.0
    ws = FakeWS()

    _run(live_session.process_frame(ws, session, FAKE_IMAGE_B64, seq=4))
    assert not any(m.get("type") == "error" for m in ws.sent)

    good = FakeRelevance(result=_relevance("relevant"))
    monkeypatch.setattr(pipeline, "evaluate_dental_relevance", good)
    session.last_frame_at = 0.0
    _run(live_session.process_frame(ws, session, FAKE_IMAGE_B64, seq=5))

    assert spy.calls == 1  # analyzer ran only for the later relevant frame
    assert session.frames_analyzed == 1
    assert session.busy is False  # session remains usable


# ---------------------------------------------------------------------------
# GENERAL
# ---------------------------------------------------------------------------
def test_jaw_cheek_swelling_passes_through_as_relevant(monkeypatch):
    rel = FakeRelevance(
        result=_relevance("relevant", visible_regions=["cheek", "jaw_swelling"])
    )
    spy = SpyAnalyzer()
    _patch(monkeypatch, rel, spy)

    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64)
        )
    )

    assert spy.calls == 1
    assert outcome.status == "analyzed"
    assert outcome.relevance.visible_regions == ["cheek", "jaw_swelling"]


def test_scan_business_logic_has_no_concrete_provider_imports():
    for module in (pipeline, live_session):
        source = inspect.getsource(module)
        assert "QwenProvider" not in source
        assert "GeminiProvider" not in source


def test_analyzed_outcome_preserves_scan_response_shape(monkeypatch):
    # Compatibility: the relevant path still exposes analysis + diagnosis keys.
    rel = FakeRelevance(result=_relevance("relevant"))
    _patch(monkeypatch, rel, SpyAnalyzer())

    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64)
        )
    )
    dumped = outcome.model_dump(mode="json")
    assert dumped["analysis"] is not None
    assert dumped["diagnosis"] is not None
    assert dumped["status"] == "analyzed"
