"""Unified Clinical LangGraph — deterministic scan-to-care orchestration (Phase 4-lite).

# Third-party: LangGraph
# Purpose: deterministic orchestration of the DaantShaant clinical screening
# pipeline. Clinical decisions remain in explicit services/rules, not LangGraph.

This graph wraps the EXISTING working clinical flow:

    START → intake → relevance → [relevant?] → clinical_vision → triage → report → persist → END
                                 [retake?]   → END
                                 [unrelated?] → END

Graph nodes are thin orchestration wrappers. They call existing service
boundaries (``evaluate_dental_relevance``, ``run_teeth_analysis_pipeline``,
``triage_findings``) and never duplicate prompts, triage rules, or provider
logic.

Mechanical image quality remains inside the Teeth Analyzer service for MVP.

**Trace**: each node appends a safe ``{node, status, duration_ms}`` entry.
No base64, API keys, prompts, or private patient text is included.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal, TypedDict
from uuid import UUID

try:
    import langchain
    if not hasattr(langchain, "debug"):
        setattr(langchain, "debug", False)
except Exception:
    pass

from langgraph.graph import END, START, StateGraph

from dantshaant_common.schemas import (
    AnalyzeResponse,
    DiagnoseResponse,
    TriageResult,
)
from orchestrator.ai.gateway import AIGateway
from orchestrator import pipeline as pipeline_mod
from orchestrator.pipeline import (
    RelevanceInfo,
    ScanOutcome,
    TeethAnalyzePipelineRequest,
    TeethAnalyzePipelineResponse,
    _relevance_info,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph State
# ---------------------------------------------------------------------------

class ClinicalGraphState(TypedDict, total=False):
    """Minimal typed state for the clinical screening graph."""

    # --- Input ---
    user_id: str  # UUID serialized as string for LangGraph state
    scan_id: str | None
    input_mode: str  # "snapshot" | "upload" | "live"
    image_base64: str
    content_type: str

    # --- Intermediate results ---
    relevance_result: dict[str, Any] | None
    analysis_result: dict[str, Any] | None
    diagnosis_result: dict[str, Any] | None
    triage_result: dict[str, Any] | None

    # --- Output ---
    status: str  # "analyzed" | "retake" | "rejected" | "error"
    recommended_action: str | None
    errors: list[str]
    trace: list[dict[str, Any]]

    # --- Injection (optional, not serialized into trace) ---
    _gateway: Any  # AIGateway or None
    _db_session: Any  # AsyncSession or None
    _pipeline_request: Any  # TeethAnalyzePipelineRequest


# ---------------------------------------------------------------------------
# Trace helper
# ---------------------------------------------------------------------------

def _trace_entry(
    node: str,
    status: str,
    started: float,
) -> dict[str, Any]:
    """Build a safe trace record — no base64, keys, or prompts."""
    return {
        "node": node,
        "status": status,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def intake_node(state: ClinicalGraphState) -> dict[str, Any]:
    """Validate inputs and initialize trace."""
    started = time.perf_counter()
    errors: list[str] = []
    if not state.get("image_base64"):
        errors.append("missing image_base64")
    if not state.get("user_id"):
        errors.append("missing user_id")

    trace = list(state.get("trace") or [])
    status = "error" if errors else "intake_complete"
    trace.append(_trace_entry("intake", "completed" if not errors else "failed", started))

    result: dict[str, Any] = {"trace": trace, "errors": errors}
    if errors:
        result["status"] = "error"
    return result


async def relevance_node(state: ClinicalGraphState) -> dict[str, Any]:
    """Evaluate semantic dental relevance via the existing service."""
    started = time.perf_counter()
    trace = list(state.get("trace") or [])
    gateway: AIGateway | None = state.get("_gateway")

    # Call existing relevance service — provider failures propagate unchanged.
    relevance = await pipeline_mod.evaluate_dental_relevance(
        state["image_base64"],
        state.get("content_type", "image/jpeg"),
        gateway=gateway,
    )

    action = relevance.recommended_action  # "continue" | "retake" | "reject"

    # Map to graph status
    if action == "continue":
        status = "relevance_passed"
    elif relevance.classification == "retake":
        status = "retake"
    else:
        status = "rejected"

    trace.append(_trace_entry("relevance", "completed", started))

    return {
        "relevance_result": relevance.model_dump(mode="json"),
        "status": status,
        "recommended_action": action,
        "trace": trace,
    }


async def clinical_vision_node(state: ClinicalGraphState) -> dict[str, Any]:
    """Run the existing Teeth Analyzer → Diagnosis pipeline."""
    started = time.perf_counter()
    trace = list(state.get("trace") or [])

    # Use the injected pipeline request or build one from state.
    pipeline_request: TeethAnalyzePipelineRequest | None = state.get("_pipeline_request")
    if pipeline_request is None:
        pipeline_request = TeethAnalyzePipelineRequest(
            user_id=UUID(state["user_id"]),
            image_base64=state["image_base64"],
            image_mime_type=state.get("content_type", "image/jpeg"),
        )

    result: TeethAnalyzePipelineResponse = await pipeline_mod.run_teeth_analysis_pipeline(
        pipeline_request,
    )

    trace.append(_trace_entry("clinical_vision", "completed", started))

    return {
        "analysis_result": result.analysis.model_dump(mode="json"),
        "diagnosis_result": result.diagnosis.model_dump(mode="json"),
        "trace": trace,
    }


def triage_node(state: ClinicalGraphState) -> dict[str, Any]:
    """Extract the deterministic triage result from the Diagnosis response.

    The Diagnosis HTTP service already applies triage rules (Phase 3B-lite)
    and returns the ``TriageResult`` in ``DiagnoseResponse.triage``. This
    node extracts it from the diagnosis response — it does NOT duplicate the
    triage rules or import the diagnosis service's internal modules.
    """
    started = time.perf_counter()
    trace = list(state.get("trace") or [])

    diagnosis_data = state.get("diagnosis_result") or {}
    triage_data = diagnosis_data.get("triage")

    trace.append(_trace_entry("triage", "completed", started))

    return {
        "triage_result": triage_data,
        "trace": trace,
    }


def report_node(state: ClinicalGraphState) -> dict[str, Any]:
    """Assemble the final analyzed status."""
    started = time.perf_counter()
    trace = list(state.get("trace") or [])
    trace.append(_trace_entry("report", "completed", started))

    return {
        "status": "analyzed",
        "trace": trace,
    }


async def persist_node(state: ClinicalGraphState) -> dict[str, Any]:
    """Persist the scan using the existing ScanRepository."""
    started = time.perf_counter()
    trace = list(state.get("trace") or [])

    db_session = state.get("_db_session")
    if db_session is None:
        # Live mode / no session injected — skip persistence here.
        # Live finalize_session handles its own persistence.
        trace.append(_trace_entry("persist", "skipped_no_session", started))
        return {"trace": trace}

    from orchestrator.repositories import ScanRepository

    analysis = AnalyzeResponse.model_validate(state["analysis_result"])
    diagnosis = DiagnoseResponse.model_validate(state["diagnosis_result"])
    relevance_data = state.get("relevance_result")
    relevance_info = RelevanceInfo.model_validate(relevance_data) if relevance_data else None

    scan, _report = await ScanRepository(db_session).add_result(
        patient_user_id=UUID(state["user_id"]),
        input_mode=state.get("input_mode", "snapshot"),
        analysis=analysis,
        diagnosis=diagnosis,
        relevance=relevance_info,
    )

    trace.append(_trace_entry("persist", "completed", started))

    return {
        "scan_id": str(scan.id),
        "trace": trace,
    }


# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------

def relevance_router(state: ClinicalGraphState) -> str:
    """Route after the relevance node.

    ``relevant`` → clinical vision pipeline.
    ``retake``/``unrelated`` → terminal (END).
    """
    action = state.get("recommended_action")
    if action == "continue":
        return "clinical_vision"
    # retake / reject both terminate. Status already set by relevance_node.
    return "__end__"


# ---------------------------------------------------------------------------
# Graph compilation
# ---------------------------------------------------------------------------

# Third-party: LangGraph
# Purpose: deterministic orchestration of the DaantShaant clinical screening
# pipeline. Clinical decisions remain in explicit services/rules, not LangGraph.
_workflow = StateGraph(ClinicalGraphState)

_workflow.add_node("intake", intake_node)
_workflow.add_node("relevance", relevance_node)
_workflow.add_node("clinical_vision", clinical_vision_node)
_workflow.add_node("triage", triage_node)
_workflow.add_node("report", report_node)
_workflow.add_node("persist", persist_node)

_workflow.add_edge(START, "intake")
_workflow.add_edge("intake", "relevance")
_workflow.add_conditional_edges(
    "relevance",
    relevance_router,
    {
        "clinical_vision": "clinical_vision",
        "__end__": END,
    },
)
_workflow.add_edge("clinical_vision", "triage")
_workflow.add_edge("triage", "report")
_workflow.add_edge("report", "persist")
_workflow.add_edge("persist", END)

clinical_graph = _workflow.compile()
"""Compiled clinical screening graph. Invoke with ``ainvoke(state)``."""


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------

async def run_clinical_graph(
    request: TeethAnalyzePipelineRequest,
    *,
    gateway: AIGateway | None = None,
    db_session: Any | None = None,
    input_mode: str = "snapshot",
) -> ScanOutcome:
    """Run the unified clinical graph and return a ``ScanOutcome``.

    This is the primary orchestration entry point. It preserves the exact same
    ``ScanOutcome`` response shape that ``run_scan_with_relevance`` returned
    before the graph existed, so callers (HTTP route, live frame handler) see
    no contract change.
    """
    initial_state: ClinicalGraphState = {
        "user_id": str(request.user_id),
        "image_base64": request.image_base64,
        "content_type": request.image_mime_type,
        "input_mode": input_mode,
        "scan_id": None,
        "relevance_result": None,
        "analysis_result": None,
        "diagnosis_result": None,
        "triage_result": None,
        "status": "pending",
        "recommended_action": None,
        "errors": [],
        "trace": [],
        "_gateway": gateway,
        "_db_session": db_session,
        "_pipeline_request": request,
    }

    final_state = await clinical_graph.ainvoke(initial_state)

    # --- Reconstruct ScanOutcome from final graph state ---
    status = final_state.get("status", "error")
    relevance_data = final_state.get("relevance_result")

    if relevance_data:
        rel_info = RelevanceInfo.model_validate(relevance_data)
    else:
        # Should not happen in normal flow, but safety fallback.
        rel_info = RelevanceInfo(
            classification="unrelated",
            recommended_action="reject",
            reason="no relevance result",
        )

    if status == "analyzed":
        analysis = AnalyzeResponse.model_validate(final_state["analysis_result"])
        diagnosis = DiagnoseResponse.model_validate(final_state["diagnosis_result"])
        return ScanOutcome(
            status="analyzed",
            relevance=rel_info,
            analysis=analysis,
            diagnosis=diagnosis,
        )

    if status == "retake":
        return ScanOutcome(status="retake", relevance=rel_info)

    if status == "rejected":
        return ScanOutcome(status="rejected", relevance=rel_info)

    # Error or unexpected — surface as rejected to avoid fabricating a clinical result.
    return ScanOutcome(status="rejected", relevance=rel_info)


__all__ = [
    "ClinicalGraphState",
    "clinical_graph",
    "run_clinical_graph",
]
