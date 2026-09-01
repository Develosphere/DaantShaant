"""Dentist Recommendation Agent — LangGraph workflow."""

from __future__ import annotations

import logging
from typing import Any, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph

from orchestrator.db.models import DentistRecommendation
from orchestrator.db.session import async_session_factory
from orchestrator.repositories import RecommendationRepository
from orchestrator.dentist_recommendation.places_service import search_nearby_dentists
from orchestrator.dentist_recommendation.platform_query import search_platform_dentists

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
    places_results: list[dict[str, Any]]
    merged: list[dict[str, Any]]


async def query_platform_node(state: DentistRecState) -> dict[str, Any]:
    logger.info("[DENTIST-GRAPH] query_platform issue=%s", state["issue"])
    results = await search_platform_dentists(
        state["lat"], state["lng"], state["issue"], state["radius_km"]
    )
    return {"platform_results": results}


async def query_places_node(state: DentistRecState) -> dict[str, Any]:
    logger.info("[DENTIST-GRAPH] query_places")
    radius_m = int(state["radius_km"] * 1000)
    min_general = max(5, 10 - len(state.get("platform_results", [])))
    results = await search_nearby_dentists(
        state["lat"], state["lng"], state["issue"], radius_m=radius_m, limit=min_general
    )
    return {"places_results": results}


async def merge_rank_node(state: DentistRecState) -> dict[str, Any]:
    logger.info("[DENTIST-GRAPH] merge_rank")
    platform = state.get("platform_results", [])
    places = state.get("places_results", [])

    seen_place_ids: set[str] = set()
    merged: list[dict[str, Any]] = []

    for item in platform:
        merged.append({**item, "is_best": False})
        if item.get("place_id"):
            seen_place_ids.add(item["place_id"])

    for item in places:
        pid = item.get("place_id")
        if pid and pid in seen_place_ids:
            continue
        merged.append({**item, "is_best": False})

    merged.sort(key=lambda x: (
        0 if x.get("tier") == "platform" else 1,
        -x.get("rank_score", 0),
    ))

    for i, item in enumerate(merged[:BEST_MATCH_COUNT]):
        item["is_best"] = True
        item["rank"] = i + 1
        item["recommendation_reason"] = (
            f"Best match #{i + 1} for your {state['issue'].replace('_', ' ')} scan"
            if item.get("tier") == "platform"
            else f"Top nearby clinic (#{i + 1}) for {state['issue'].replace('_', ' ')}"
        )

    for i, item in enumerate(merged):
        if "rank" not in item:
            item["rank"] = i + 1

    return {"merged": merged}


async def log_session_node(state: DentistRecState) -> dict[str, Any]:
    logger.info("[DENTIST-GRAPH] log_session")
    scan_id = UUID(state["scan_id"]) if state.get("scan_id") else None
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
    return {}


workflow = StateGraph(DentistRecState)
workflow.add_node("query_platform", query_platform_node)
workflow.add_node("query_places", query_places_node)
workflow.add_node("merge_rank", merge_rank_node)
workflow.add_node("log_session", log_session_node)

workflow.add_edge(START, "query_platform")
workflow.add_edge("query_platform", "query_places")
workflow.add_edge("query_places", "merge_rank")
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
        "places_results": [],
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
