"""Dentist Recommendation Agent — LangGraph workflow with OSM & Platform Discovery."""

from __future__ import annotations

import logging
from typing import Any, TypedDict
from uuid import UUID, uuid4

try:
    import langchain  # type: ignore[import]
    if not hasattr(langchain, "debug"):
        langchain.debug = False
except ImportError:
    pass

from langgraph.graph import END, START, StateGraph

from orchestrator.db.models import DentistRecommendation
from orchestrator.db.session import async_session_factory
from orchestrator.repositories import RecommendationRepository
from orchestrator.dentist_recommendation.osm_dentists import search_osm_dentists
from orchestrator.dentist_recommendation.platform_query import search_platform_dentists
from orchestrator.dentist_recommendation.ranking import rank_dentists

logger = logging.getLogger(__name__)

BEST_MATCH_COUNT = 3


class DentistRecState(TypedDict):
    patient_id: str
    session_id: str
    issue: str
    severity: str
    lat: float
    lng: float
    radius_km: float
    scan_id: str | None
    platform_results: list[dict[str, Any]]
    osm_results: list[dict[str, Any]]
    merged: list[dict[str, Any]]


async def query_platform_node(state: DentistRecState) -> dict[str, Any]:
    logger.info("[DENTIST-GRAPH] query_platform issue=%s", state["issue"])
    try:
        results = await search_platform_dentists(
            state["lat"], state["lng"], state["issue"], state["radius_km"]
        )
    except Exception as exc:
        logger.warning("[DENTIST-GRAPH] Platform query failed: %s", exc)
        results = []
    return {"platform_results": results}


async def query_osm_node(state: DentistRecState) -> dict[str, Any]:
    logger.info("[DENTIST-GRAPH] query_osm")
    try:
        results = await search_osm_dentists(
            state["lat"], state["lng"], radius_km=state["radius_km"]
        )
    except Exception as exc:
        logger.warning("[DENTIST-GRAPH] OSM query failed: %s", exc)
        results = []
    return {"osm_results": results}


async def merge_rank_node(state: DentistRecState) -> dict[str, Any]:
    logger.info("[DENTIST-GRAPH] merge_rank")
    platform = state.get("platform_results", [])
    osm = state.get("osm_results", [])

    merged = rank_dentists(
        platform_dentists=platform,
        osm_dentists=osm,
        issue=state["issue"],
        limit=15,
    )
    return {"merged": merged}


async def log_session_node(state: DentistRecState) -> dict[str, Any]:
    logger.info("[DENTIST-GRAPH] log_session")
    scan_id = UUID(state["scan_id"]) if state.get("scan_id") else None
    try:
        async with async_session_factory() as session:
            async with session.begin():
                await RecommendationRepository(session).add_dentist(
                    DentistRecommendation(
                        session_id=UUID(state["session_id"]),
                        patient_user_id=UUID(state["patient_id"]),
                        scan_id=scan_id,
                        specialist=state["issue"],
                        severity=state.get("severity", ""),
                        patient_lat=state["lat"],
                        patient_lng=state["lng"],
                        results={"dentists": state.get("merged", [])},
                    )
                )
    except Exception as exc:
        logger.warning("[DENTIST-GRAPH] Failed to persist recommendation session: %s", exc)
    return {}


workflow = StateGraph(DentistRecState)
workflow.add_node("query_platform", query_platform_node)
workflow.add_node("query_osm", query_osm_node)
workflow.add_node("merge_rank", merge_rank_node)
workflow.add_node("log_session", log_session_node)

workflow.add_edge(START, "query_platform")
workflow.add_edge("query_platform", "query_osm")
workflow.add_edge("query_osm", "merge_rank")
workflow.add_edge("merge_rank", "log_session")
workflow.add_edge("log_session", END)

dentist_recommendation_graph = workflow.compile()


async def run_dentist_recommendation(
    *,
    patient_id: str,
    issue: str,
    lat: float,
    lng: float,
    severity: str = "moderate",
    scan_id: str | None = None,
    session_id: str | None = None,
    radius_km: float = 25.0,
) -> dict[str, Any]:
    sid = session_id or str(uuid4())
    initial: DentistRecState = {
        "patient_id": patient_id,
        "session_id": sid,
        "issue": issue,
        "severity": severity,
        "lat": lat,
        "lng": lng,
        "radius_km": radius_km,
        "scan_id": scan_id,
        "platform_results": [],
        "osm_results": [],
        "merged": [],
    }
    result = await dentist_recommendation_graph.ainvoke(initial)
    return {
        "session_id": sid,
        "patient_lat": lat,
        "patient_lng": lng,
        "issue": issue,
        "dentists": result.get("merged", []),
    }
