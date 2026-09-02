"""Tests for Phase 4-lite — Unified Clinical LangGraph.

Validates the deterministic clinical screening graph:

    START → intake → relevance → [route] → clinical_vision → triage → report → persist → END

12 tests, ZERO real AI / provider / network calls.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dantshaant_common.schemas import (
    ActionTrigger,
    AnalyzeResponse,
    ConditionLabel,
    DiagnoseResponse,
    Severity,
    TriageResult,
    UrgencyLevel,
    VisualFinding,
)
from orchestrator.ai.exceptions import AllProvidersFailedError
from orchestrator.clinical.relevance import DentalRelevanceResult
from orchestrator.pipeline import (
    RelevanceInfo,
    ScanOutcome,
    TeethAnalyzePipelineRequest,
    TeethAnalyzePipelineResponse,
    run_scan_with_relevance,
)

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


def _pipeline_response(triage: TriageResult | None = None) -> TeethAnalyzePipelineResponse:
    uid = uuid.uuid4()
    analysis = AnalyzeResponse(
        user_id=uid,
        findings=[VisualFinding(label="plaque_detected", confidence=0.6)],
        overall_quality_score=0.8,
        model_id="stub-v0",
    )
    if triage is None:
        triage = TriageResult(
            verdict="Routine Dental Visit Recommended",
            condition_summary="Mild plaque detected.",
            possible_concerns=["plaque_detected"],
            urgency_level=UrgencyLevel.ROUTINE,
            recommended_actions=["Schedule regular dental cleaning."],
            recommended_specialist="General Dentist",
            visit_timeframe="Within 6 months",
            disclaimer="Screening awareness only.",
        )
    diagnosis = DiagnoseResponse(
        user_id=uid,
        analysis_id=uuid.uuid4(),
        condition_label=ConditionLabel.PLAQUE_TARTAR,
        severity=Severity.MILD,
        confidence=0.7,
        confidence_threshold=0.5,
        meets_threshold=True,
        action_trigger=ActionTrigger.PRODUCT_SUGGEST_BRUSHING,
        triage=triage,
    )
    return TeethAnalyzePipelineResponse(analysis=analysis, diagnosis=diagnosis)


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


class SpyAnalyzer:
    """Stands in for the clinical Teeth Analyzer pipeline boundary."""

    def __init__(self, response=None) -> None:
        self.calls = 0
        self.response = response or _pipeline_response()

    async def __call__(self, request: TeethAnalyzePipelineRequest):
        self.calls += 1
        return self.response


class SpyRepository:
    """Tracks calls to ScanRepository.add_result."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def add_result(self, **kwargs):
        self.calls.append(kwargs)
        scan = MagicMock()
        scan.id = uuid.uuid4()
        report = MagicMock()
        return scan, report


def _patch_graph(monkeypatch, relevance_fake, analyzer_spy, repo_spy=None):
    """Patch the graph's dependencies without touching existing service code."""
    from orchestrator import pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "evaluate_dental_relevance", relevance_fake)
    monkeypatch.setattr(pipeline_mod, "run_teeth_analysis_pipeline", analyzer_spy)


# ---------------------------------------------------------------------------
# 1. Relevant image: full pipeline
# ---------------------------------------------------------------------------
def test_relevant_image_full_pipeline(monkeypatch):
    rel = FakeRelevance(result=_relevance("relevant"))
    spy = SpyAnalyzer()
    _patch_graph(monkeypatch, rel, spy)

    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64)
        )
    )

    assert spy.calls == 1
    assert outcome.status == "analyzed"
    assert outcome.analysis is not None
    assert outcome.diagnosis is not None
    assert outcome.relevance.classification == "relevant"
    assert outcome.relevance.recommended_action == "continue"


# ---------------------------------------------------------------------------
# 2. Retake image: clinical vision NOT called
# ---------------------------------------------------------------------------
def test_retake_image_skips_clinical_vision(monkeypatch):
    rel = FakeRelevance(
        result=_relevance("retake", relevance_score=0.4, retake_reason="mouth_too_far")
    )
    spy = SpyAnalyzer()
    _patch_graph(monkeypatch, rel, spy)

    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64)
        )
    )

    assert spy.calls == 0
    assert outcome.status == "retake"
    assert outcome.analysis is None and outcome.diagnosis is None
    assert outcome.relevance.recommended_action == "retake"


# ---------------------------------------------------------------------------
# 3. Unrelated image: clinical vision NOT called
# ---------------------------------------------------------------------------
def test_unrelated_image_skips_clinical_vision(monkeypatch):
    rel = FakeRelevance(
        result=_relevance("unrelated", relevance_score=0.05, visible_regions=["laptop"])
    )
    spy = SpyAnalyzer()
    _patch_graph(monkeypatch, rel, spy)

    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64)
        )
    )

    assert spy.calls == 0
    assert outcome.status == "rejected"
    assert outcome.relevance.recommended_action == "reject"


# ---------------------------------------------------------------------------
# 4. Provider failure: not converted to unrelated/rejected
# ---------------------------------------------------------------------------
def test_provider_failure_not_converted_to_rejection(monkeypatch):
    rel = FakeRelevance(error=AllProvidersFailedError("both providers down"))
    spy = SpyAnalyzer()
    _patch_graph(monkeypatch, rel, spy)

    with pytest.raises(AllProvidersFailedError):
        _run(
            run_scan_with_relevance(
                TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64)
            )
        )
    assert spy.calls == 0


# ---------------------------------------------------------------------------
# 5. Triage result propagated
# ---------------------------------------------------------------------------
def test_triage_result_propagated_in_graph(monkeypatch):
    rel = FakeRelevance(result=_relevance("relevant"))
    spy = SpyAnalyzer()
    _patch_graph(monkeypatch, rel, spy)

    from orchestrator.clinical.graph import clinical_graph, run_clinical_graph

    request = TeethAnalyzePipelineRequest(
        user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64
    )
    initial_state = {
        "user_id": str(request.user_id),
        "image_base64": request.image_base64,
        "content_type": request.image_mime_type,
        "input_mode": "snapshot",
        "scan_id": None,
        "relevance_result": None,
        "analysis_result": None,
        "diagnosis_result": None,
        "triage_result": None,
        "status": "pending",
        "recommended_action": None,
        "errors": [],
        "trace": [],
        "_gateway": None,
        "_db_session": None,
        "_pipeline_request": request,
    }

    final_state = _run(clinical_graph.ainvoke(initial_state))

    assert final_state.get("triage_result") is not None
    triage = final_state["triage_result"]
    assert "verdict" in triage
    assert "urgency_level" in triage
    assert "possible_concerns" in triage


# ---------------------------------------------------------------------------
# 6. Trace contains expected node order
# ---------------------------------------------------------------------------
def test_trace_contains_expected_node_order(monkeypatch):
    rel = FakeRelevance(result=_relevance("relevant"))
    spy = SpyAnalyzer()
    _patch_graph(monkeypatch, rel, spy)

    from orchestrator.clinical.graph import clinical_graph

    request = TeethAnalyzePipelineRequest(
        user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64
    )
    initial_state = {
        "user_id": str(request.user_id),
        "image_base64": request.image_base64,
        "content_type": request.image_mime_type,
        "input_mode": "snapshot",
        "scan_id": None,
        "relevance_result": None,
        "analysis_result": None,
        "diagnosis_result": None,
        "triage_result": None,
        "status": "pending",
        "recommended_action": None,
        "errors": [],
        "trace": [],
        "_gateway": None,
        "_db_session": None,
        "_pipeline_request": request,
    }

    final_state = _run(clinical_graph.ainvoke(initial_state))
    trace = final_state.get("trace", [])
    node_names = [entry["node"] for entry in trace]

    assert node_names == ["intake", "relevance", "clinical_vision", "triage", "report", "persist"]

    # Every entry has the expected shape
    for entry in trace:
        assert "node" in entry
        assert "status" in entry
        assert "duration_ms" in entry
        assert isinstance(entry["duration_ms"], int)


# ---------------------------------------------------------------------------
# 7. Trace contains no image/base64 payload
# ---------------------------------------------------------------------------
def test_trace_contains_no_image_or_base64(monkeypatch):
    rel = FakeRelevance(result=_relevance("relevant"))
    spy = SpyAnalyzer()
    _patch_graph(monkeypatch, rel, spy)

    from orchestrator.clinical.graph import clinical_graph

    request = TeethAnalyzePipelineRequest(
        user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64
    )
    initial_state = {
        "user_id": str(request.user_id),
        "image_base64": request.image_base64,
        "content_type": request.image_mime_type,
        "input_mode": "snapshot",
        "scan_id": None,
        "relevance_result": None,
        "analysis_result": None,
        "diagnosis_result": None,
        "triage_result": None,
        "status": "pending",
        "recommended_action": None,
        "errors": [],
        "trace": [],
        "_gateway": None,
        "_db_session": None,
        "_pipeline_request": request,
    }

    final_state = _run(clinical_graph.ainvoke(initial_state))
    trace_str = json.dumps(final_state.get("trace", []))

    # No image data should leak into trace.
    assert "base64" not in trace_str.lower() or "image_base64" not in trace_str
    assert FAKE_IMAGE_B64 not in trace_str
    # No API keys or prompts.
    assert "api_key" not in trace_str.lower()
    assert "DASHSCOPE" not in trace_str


# ---------------------------------------------------------------------------
# 8. Persistence invoked for analyzed scan
# ---------------------------------------------------------------------------
def test_persistence_invoked_for_analyzed_scan(monkeypatch):
    rel = FakeRelevance(result=_relevance("relevant"))
    spy = SpyAnalyzer()
    _patch_graph(monkeypatch, rel, spy)

    repo_spy = SpyRepository()

    from orchestrator.clinical import graph as graph_mod

    monkeypatch.setattr(
        "orchestrator.clinical.graph.ScanRepository",
        lambda session: repo_spy,
        raising=False,
    )
    # Patch via import inside persist_node
    import orchestrator.repositories as repos_mod
    original_scan_repo = repos_mod.ScanRepository
    monkeypatch.setattr(repos_mod, "ScanRepository", lambda session: repo_spy)

    db_session = MagicMock()

    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64),
            db_session=db_session,
            input_mode="snapshot",
        )
    )

    assert outcome.status == "analyzed"
    assert len(repo_spy.calls) == 1
    assert repo_spy.calls[0]["input_mode"] == "snapshot"


# ---------------------------------------------------------------------------
# 9. No persistence for retake/unrelated
# ---------------------------------------------------------------------------
def test_no_persistence_for_retake(monkeypatch):
    rel = FakeRelevance(result=_relevance("retake", retake_reason="too_far"))
    spy = SpyAnalyzer()
    _patch_graph(monkeypatch, rel, spy)

    repo_spy = SpyRepository()
    import orchestrator.repositories as repos_mod
    monkeypatch.setattr(repos_mod, "ScanRepository", lambda session: repo_spy)

    db_session = MagicMock()
    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64),
            db_session=db_session,
        )
    )

    assert outcome.status == "retake"
    assert len(repo_spy.calls) == 0


def test_no_persistence_for_unrelated(monkeypatch):
    rel = FakeRelevance(result=_relevance("unrelated"))
    spy = SpyAnalyzer()
    _patch_graph(monkeypatch, rel, spy)

    repo_spy = SpyRepository()
    import orchestrator.repositories as repos_mod
    monkeypatch.setattr(repos_mod, "ScanRepository", lambda session: repo_spy)

    db_session = MagicMock()
    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64),
            db_session=db_session,
        )
    )

    assert outcome.status == "rejected"
    assert len(repo_spy.calls) == 0


# ---------------------------------------------------------------------------
# 10. ScanOutcome response shape preserved
# ---------------------------------------------------------------------------
def test_scan_outcome_response_shape_preserved(monkeypatch):
    rel = FakeRelevance(result=_relevance("relevant"))
    spy = SpyAnalyzer()
    _patch_graph(monkeypatch, rel, spy)

    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64)
        )
    )

    dumped = outcome.model_dump(mode="json")
    assert dumped["status"] == "analyzed"
    assert dumped["analysis"] is not None
    assert dumped["diagnosis"] is not None
    assert "classification" in dumped["relevance"]
    assert "recommended_action" in dumped["relevance"]


# ---------------------------------------------------------------------------
# 11. Snapshot/upload common path uses graph
# ---------------------------------------------------------------------------
def test_snapshot_path_uses_graph(monkeypatch):
    """run_scan_with_relevance is the shared path and now invokes the graph."""
    rel = FakeRelevance(result=_relevance("relevant"))
    spy = SpyAnalyzer()
    _patch_graph(monkeypatch, rel, spy)

    # Track that the graph runner was actually invoked.
    from orchestrator.clinical import graph as graph_mod

    original_runner = graph_mod.run_clinical_graph
    invoked = {"count": 0}

    async def tracking_runner(*args, **kwargs):
        invoked["count"] += 1
        return await original_runner(*args, **kwargs)

    monkeypatch.setattr(graph_mod, "run_clinical_graph", tracking_runner)

    outcome = _run(
        run_scan_with_relevance(
            TeethAnalyzePipelineRequest(user_id=uuid.uuid4(), image_base64=FAKE_IMAGE_B64)
        )
    )

    assert invoked["count"] == 1
    assert outcome.status == "analyzed"


# ---------------------------------------------------------------------------
# 12. Live analyzed frame uses same graph path
# ---------------------------------------------------------------------------
def test_live_frame_uses_graph_via_shared_helper(monkeypatch):
    """Live process_frame calls run_scan_with_relevance which now uses the graph."""
    from orchestrator import live_session

    rel = FakeRelevance(result=_relevance("relevant"))
    spy = SpyAnalyzer()
    _patch_graph(monkeypatch, rel, spy)
    monkeypatch.setattr(live_session, "log_event", lambda *a, **k: None)

    session = live_session.LiveSessionState(
        session_id=uuid.uuid4(), user_id=uuid.uuid4(), locale="en"
    )
    session.last_frame_at = 0.0

    class FakeWS:
        def __init__(self):
            self.sent: list[dict] = []

        async def send_json(self, payload: dict):
            self.sent.append(payload)

    ws = FakeWS()

    _run(live_session.process_frame(ws, session, FAKE_IMAGE_B64, seq=1))

    assert spy.calls == 1
    assert session.frames_analyzed == 1
    assert session.best is not None


# ---------------------------------------------------------------------------
# 13. Graph does NOT import diagnosis.triage directly
# ---------------------------------------------------------------------------
def test_graph_does_not_import_diagnosis_triage_directly():
    """Verify architectural boundary: graph does not import diagnosis internals."""
    import inspect
    from orchestrator.clinical import graph as graph_mod

    source = inspect.getsource(graph_mod)
    assert "diagnosis.triage" not in source
    assert "from diagnosis" not in source
    assert "import diagnosis" not in source
