"""Dentist Recommendation Agent — LangGraph workflow with Adaptive Radius & Multi-Source Discovery."""

from __future__ import annotations

import logging
import os
import time
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
from orchestrator.dentist_recommendation.external_providers import (
    discover_external_dentists,
    search_foursquare_dentists,
    search_geoapify_dentists,
)
from orchestrator.dentist_recommendation.platform_query import search_platform_dentists
from orchestrator.dentist_recommendation.ranking import rank_dentists

logger = logging.getLogger(__name__)

BEST_MATCH_COUNT = 3
SEARCH_RADII_KM: list[float] = [3.0, 5.0, 8.0, 10.0]
MIN_RESULT_TARGET: int = 5


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
    final_radius_km: float


async def _discover_external(lat: float, lng: float, radius: float) -> list[dict[str, Any]]:
    """Helper to discover external candidates while respecting dentist_agent mocks."""
    candidates: list[dict[str, Any]] = []
    try:
        osm_res = await search_osm_dentists(lat, lng, radius_km=radius)
        candidates.extend(osm_res)
    except Exception as exc:
        logger.warning("[DENTIST-AGENT] OSM query failed: %s", exc)

    if os.getenv("FOURSQUARE_API_KEY", "").strip():
        try:
            fsq_res = await search_foursquare_dentists(lat, lng, radius_km=radius)
            candidates.extend(fsq_res)
        except Exception as exc:
            logger.warning("[DENTIST-AGENT] Foursquare query failed: %s", exc)

    if os.getenv("GEOAPIFY_API_KEY", "").strip():
        try:
            geo_res = await search_geoapify_dentists(lat, lng, radius_km=radius)
            candidates.extend(geo_res)
        except Exception as exc:
            logger.warning("[DENTIST-AGENT] Geoapify query failed: %s", exc)

    return candidates


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
        results = await _discover_external(state["lat"], state["lng"], state["radius_km"])
    except Exception as exc:
        logger.warning("[DENTIST-GRAPH] External query failed: %s", exc)
        results = []
    return {"osm_results": results}


async def merge_rank_node(state: DentistRecState) -> dict[str, Any]:
    logger.info("[DENTIST-GRAPH] merge_rank")
    platform = state.get("platform_results", [])
    osm = state.get("osm_results", [])

    merged = rank_dentists(
        platform_dentists=platform,
        external_dentists=osm,
        issue=state["issue"],
        limit=15,
    )
    return {"merged": merged}


async def adaptive_discovery_node(state: DentistRecState) -> dict[str, Any]:
    """Execute adaptive locality search across [3, 5, 8, 10] km with minimum target."""
    lat = state["lat"]
    lng = state["lng"]
    issue = state["issue"]
    radii = SEARCH_RADII_KM
    target = MIN_RESULT_TARGET

    t0 = time.time()
    last_platform: list[dict[str, Any]] = []
    last_external: list[dict[str, Any]] = []
    last_merged: list[dict[str, Any]] = []
    final_radius = radii[-1]

    for radius in radii:
        try:
            platform_res = await search_platform_dentists(lat, lng, issue, radius_km=radius)
        except Exception as exc:
            logger.warning("[DENTIST-ADAPTIVE] Platform query error at %.1fkm: %s", radius, exc)
            platform_res = []

        try:
            external_res = await _discover_external(lat, lng, radius=radius)
        except Exception as exc:
            logger.warning("[DENTIST-ADAPTIVE] External query error at %.1fkm: %s", radius, exc)
            external_res = []

        last_platform = platform_res
        last_external = external_res
        final_radius = radius

        temp_merged = rank_dentists(
            platform_dentists=platform_res,
            external_dentists=external_res,
            issue=issue,
            limit=15,
        )
        last_merged = temp_merged

        elapsed = time.time() - t0
        logger.info(
            "[DENTIST_DISCOVERY] center=(%.4f,%.4f) radius=%.0fkm platform=%d overpass=%d merged=%d target=%d final_radius=%.0fkm (%.2fs)",
            lat,
            lng,
            radius,
            len(platform_res),
            len(external_res),
            len(temp_merged),
            target,
            final_radius,
            elapsed,
        )

        if len(temp_merged) >= target:
            logger.info(
                "[DENTIST_DISCOVERY] target reached at %.0fkm: final=%d clinics found",
                radius,
                len(temp_merged),
            )
            break

    return {
        "platform_results": last_platform,
        "osm_results": last_external,
        "merged": last_merged,
        "final_radius_km": final_radius,
    }


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
workflow.add_node("adaptive_discovery", adaptive_discovery_node)
workflow.add_node("log_session", log_session_node)

workflow.add_edge(START, "adaptive_discovery")
workflow.add_edge("adaptive_discovery", "log_session")
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
        "final_radius_km": 10.0,
    }
    result = await dentist_recommendation_graph.ainvoke(initial)
    return {
        "session_id": sid,
        "patient_lat": lat,
        "patient_lng": lng,
        "issue": issue,
        "dentists": result.get("merged", []),
        "search_radius_km": result.get("final_radius_km", 10.0),
    }
