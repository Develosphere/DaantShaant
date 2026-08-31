"""Google Places API — nearby general dentists (Tier 2)."""

from __future__ import annotations

import logging
import math
from typing import Any

import httpx

from orchestrator.config import settings
from orchestrator.dentist_recommendation.condition_mapping import places_keyword_for_issue

logger = logging.getLogger(__name__)


def _maps_key() -> str:
    return settings.google_maps_api_key.strip()


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def search_nearby_dentists(
    lat: float,
    lng: float,
    issue: str,
    radius_m: int = 10000,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search Google Places for general dentists near a coordinate."""
    api_key = _maps_key()
    if not api_key:
        logger.warning("[PLACES] GOOGLE_MAPS_API_KEY not set")
        return []

    keyword = places_keyword_for_issue(issue)
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": radius_m,
        "type": "dentist",
        "keyword": keyword,
        "key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(url, params=params)
            res.raise_for_status()
            data = res.json()
    except Exception as exc:
        logger.warning("[PLACES] Nearby search failed: %s", exc)
        return []

    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        logger.warning("[PLACES] API status=%s", data.get("status"))
        return []

    results: list[dict[str, Any]] = []
    for i, place in enumerate(data.get("results", [])[:limit]):
        place_lat = place["geometry"]["location"]["lat"]
        place_lng = place["geometry"]["location"]["lng"]
        dist = haversine_km(lat, lng, place_lat, place_lng)
        results.append({
            "tier": "general",
            "dentist_id": None,
            "place_id": place.get("place_id"),
            "name": place.get("name", "Dental Clinic"),
            "lat": place_lat,
            "lng": place_lng,
            "address": place.get("vicinity") or place.get("formatted_address", ""),
            "phone": None,
            "rating": place.get("rating"),
            "distance_km": round(dist, 2),
            "specialties": [],
            "is_partner": False,
            "clinic_name": place.get("name", "Dental Clinic"),
            "recommendation_reason": f"Highly rated nearby clinic for {issue.replace('_', ' ')}",
            "rank_score": max(0, 100 - dist * 5) + (place.get("rating") or 0) * 5,
        })

    # Fetch phone numbers for top results (best-effort)
    for item in results[:5]:
        if item.get("place_id"):
            phone = await _fetch_place_phone(item["place_id"])
            if phone:
                item["phone"] = phone

    return results


async def _fetch_place_phone(place_id: str) -> str | None:
    api_key = _maps_key()
    if not api_key:
        return None

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "formatted_phone_number,international_phone_number",
        "key": api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(url, params=params)
            data = res.json()
        if data.get("status") != "OK":
            return None
        result = data.get("result", {})
        return result.get("international_phone_number") or result.get("formatted_phone_number")
    except Exception:
        return None
