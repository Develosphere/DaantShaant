"""DentAssist Recommendation Agent — LangGraph Framework.

This module defines the StateGraph, nodes, and the run_recommendation runner
function using the LangGraph framework.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, TypedDict

try:
    import langchain  # type: ignore[import]
    if not hasattr(langchain, "debug"):
        langchain.debug = False
except ImportError:
    pass

from langgraph.graph import StateGraph, START, END

from orchestrator.recommendation_ai_system.tools import (
    get_product_details,
    log_recommendation_session,
    rank_recommendations,
    search_products_by_issue,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps runtime import cheap
    from orchestrator.ai.gateway import AIGateway

logger = logging.getLogger(__name__)

# Module-level gateway handle; resolved lazily so no provider/HTTP client is
# composed at import time. Business code depends only on the shared AIGateway.
_gateway: "AIGateway | None" = None


def _get_gateway() -> "AIGateway":
    """Return the shared AI gateway, composing it on first use (never at import)."""
    global _gateway
    if _gateway is None:
        from orchestrator.ai.factory import get_ai_gateway

        _gateway = get_ai_gateway()
    return _gateway

# ---------------------------------------------------------------------------
# LangGraph State Definition
# ---------------------------------------------------------------------------
class RecommendationState(TypedDict):
    """The state schema for the recommendation workflow."""
    issue: str
    patient_id: str
    session_id: str
    candidates: List[Dict[str, Any]]
    detailed_candidates: List[Dict[str, Any]]
    ranked_candidates: List[Dict[str, Any]]
    final_output: str


# ---------------------------------------------------------------------------
# Node Functions
# ---------------------------------------------------------------------------
async def search_products_node(state: RecommendationState) -> Dict[str, Any]:
    """Search for dental products that address the patient's issue."""
    logger.info("[LANGGRAPH] Node: search_products for issue='%s'", state["issue"])
    candidates = await search_products_by_issue(state["issue"])
    return {"candidates": candidates}


async def get_details_node(state: RecommendationState) -> Dict[str, Any]:
    """Fetch complete details for the top 3-4 candidate products."""
    logger.info("[LANGGRAPH] Node: get_details")
    candidates = state.get("candidates", [])
    detailed = []
    # Fetch details for the top 4 candidates
    for c in candidates[:4]:
        detail = await get_product_details(c["product_id"])
        if "error" not in detail:
            detailed.append({**c, **detail})
        else:
            detailed.append(c)
    return {"detailed_candidates": detailed}


async def rank_node(state: RecommendationState) -> Dict[str, Any]:
    """Rerank candidates using LLM or fallback, adding recommendation reasons."""
    logger.info("[LANGGRAPH] Node: rank")
    candidates = state.get("detailed_candidates", []) or state.get("candidates", [])[:5]
    ranked = await rank_recommendations(candidates, state["issue"])
    return {"ranked_candidates": ranked}


async def log_session_node(state: RecommendationState) -> Dict[str, Any]:
    """Log the recommendation session to PostgreSQL."""
    logger.info("[LANGGRAPH] Node: log_session")
    ranked = state.get("ranked_candidates", [])
    top_ids = [r["product_id"] for r in ranked[:5]]
    await log_recommendation_session(
        state["session_id"],
        state["patient_id"],
        state["issue"],
        top_ids
    )
    return {}


async def generate_response_node(state: RecommendationState) -> Dict[str, Any]:
    """Format and generate the final recommended products message."""
    logger.info("[LANGGRAPH] Node: generate_response")
    ranked = state.get("ranked_candidates", [])
    if not ranked:
        return {"final_output": "No recommended products are currently available from registered dental providers."}

    product_lines = "\n".join(
        f"- {r['name']} (${r['price']:.2f}): {r.get('recommendation_reason', r.get('ai_description', ''))}"
        for r in ranked[:5]
    )

    prompt = (
        f"Patient dental issue: {state['issue']}\n\n"
        f"Top recommended products:\n{product_lines}\n\n"
        "Write a warm, patient-friendly recommendation message presenting these products. "
        "Use simple, empathetic language. Explain briefly why each product helps their specific issue.\n\n"
        "You MUST present the top 3-5 recommendations exactly in this format:\n\n"
        "🦷 Recommended for: [brief issue summary]\n\n"
        "1. [Product Name] — $[price]\n"
        "   Why: [recommendation_reason]\n"
        "   Helps with: [problems_solved list]\n\n"
        "2. [Product Name] — $[price]\n"
        "   Why: [recommendation_reason]\n"
        "   Helps with: [problems_solved list]\n\n"
        "..."
    )

    from orchestrator.ai.exceptions import AllProvidersFailedError
    from orchestrator.ai.schemas import ChatMessage, TextRequest

    request = TextRequest(
        messages=[
            ChatMessage(
                role="system",
                content="You are DentAssist, a friendly dental product advisor.",
            ),
            ChatMessage(role="user", content=prompt),
        ],
        temperature=0.4,
        max_tokens=800,
    )

    try:
        result = await _get_gateway().generate_text(request)
        text = (result.content or "").strip()
    except AllProvidersFailedError as exc:
        logger.warning(
            "[LANGGRAPH] All AI providers failed for recommendation formatting: %s — using fallback text formatting",
            type(exc).__name__,
        )
        text = ""

    if text:
        return {"final_output": text}

    # Deterministic/template fallback (also used when the gateway returns empty).
    lines = [f"🦷 Recommended for: {state['issue']}\n"]
    for i, r in enumerate(ranked[:5], 1):
        problems_solved_str = ", ".join(r.get("problems_solved", []))
        lines.append(
            f"{i}. {r['name']} — ${r['price']:.2f}\n"
            f"   Why: {r.get('recommendation_reason', r.get('ai_description', ''))}\n"
            f"   Helps with: [{problems_solved_str}]\n"
        )
    return {"final_output": "\n".join(lines)}


async def terminate_low_similarity_node(state: RecommendationState) -> Dict[str, Any]:
    """Node executed when no relevant products match the patient's issue."""
    logger.info("[LANGGRAPH] Node: terminate_low_similarity")
    return {"final_output": "No recommended products are currently available from registered dental providers."}


# ---------------------------------------------------------------------------
# Conditional Router Function
# ---------------------------------------------------------------------------
def should_continue(state: RecommendationState) -> str:
    """Route based on candidate products similarity scores."""
    candidates = state.get("candidates", [])
    if not candidates or all(c.get("similarity_score", 0) < 0.3 for c in candidates):
        logger.info("[LANGGRAPH] Router: low similarity scores (< 0.3) -> terminating early")
        return "terminate_low_similarity"
    logger.info("[LANGGRAPH] Router: matching candidates found -> continuing workflow")
    return "continue"


# ---------------------------------------------------------------------------
# Graph Compilation
# ---------------------------------------------------------------------------
workflow = StateGraph(RecommendationState)

# Add Nodes
workflow.add_node("search_products", search_products_node)
workflow.add_node("get_details", get_details_node)
workflow.add_node("rank", rank_node)
workflow.add_node("log_session", log_session_node)
workflow.add_node("generate_response", generate_response_node)
workflow.add_node("terminate_low_similarity", terminate_low_similarity_node)

# Define Transitions
workflow.add_edge(START, "search_products")

workflow.add_conditional_edges(
    "search_products",
    should_continue,
    {
        "continue": "get_details",
        "terminate_low_similarity": "terminate_low_similarity",
    }
)

workflow.add_edge("get_details", "rank")
workflow.add_edge("rank", "log_session")
workflow.add_edge("log_session", "generate_response")
workflow.add_edge("generate_response", END)
workflow.add_edge("terminate_low_similarity", END)

# Compile
recommendation_graph = workflow.compile()


# ---------------------------------------------------------------------------
# API Entry Point
# ---------------------------------------------------------------------------
async def run_recommendation(issue: str, patient_id: str, session_id: str) -> str:
    """Run the recommendation agent workflow using LangGraph."""
    logger.info("[RECOMMEND] Running recommendation workflow using LangGraph for session=%s", session_id)
    initial_state = {
        "issue": issue,
        "patient_id": patient_id,
        "session_id": session_id,
        "candidates": [],
        "detailed_candidates": [],
        "ranked_candidates": [],
        "final_output": "",
    }
    
    result = await recommendation_graph.ainvoke(initial_state)
    return result["final_output"]
