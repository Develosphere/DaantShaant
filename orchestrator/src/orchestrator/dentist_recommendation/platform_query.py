"""Query registered platform dentists (Tier 1) from MongoDB."""

from __future__ import annotations

import logging
import math
from typing import Any

from orchestrator.dentist_portal.db import get_portal_users_col
from orchestrator.dentist_portal.models import UserRole
from orchestrator.dentist_recommendation.condition_mapping import specialist_tags_for_issue
from orchestrator.dentist_recommendation.geocoding import geocode_address
from orchestrator.dentist_recommendation.places_service import haversine_km

logger = logging.getLogger(__name__)


def _specialty_match_score(dentist: dict, tags: list[str]) -> float:
    if not tags:
        return 10.0
    haystack = " ".join([
        dentist.get("specialized_training") or "",
        dentist.get("degree") or "",
        dentist.get("institution") or "",
        dentist.get("clinic_name") or "",
    ]).lower()
    score = 0.0
    for tag in tags:
        if tag.lower() in haystack:
            score += 25.0
    return score


async def _ensure_coordinates(dentist: dict) -> tuple[float, float] | None:
    lat = dentist.get("lat")
    lng = dentist.get("lng")
    if lat is not None and lng is not None:
        return float(lat), float(lng)

    location = dentist.get("location", "")
    coords = await geocode_address(location)
    if not coords:
        return None

    lat, lng = coords
    users = get_portal_users_col()
    await users.update_one(
        {"_id": dentist["_id"]},
        {"$set": {
            "lat": lat,
            "lng": lng,
            "coordinates": {"type": "Point", "coordinates": [lng, lat]},
        }},
    )
    return lat, lng


async def search_platform_dentists(
    lat: float,
    lng: float,
    issue: str,
    radius_km: float = 25.0,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Find registered dentists within radius, ranked by specialty + distance."""
    users = get_portal_users_col()
    tags = specialist_tags_for_issue(issue)

    cursor = users.find({"role": UserRole.DENTIST.value})
    docs = await cursor.to_list(length=200)

    results: list[dict[str, Any]] = []
    for doc in docs:
        coords = await _ensure_coordinates(doc)
        if not coords:
            continue

        dlat, dlng = coords
        dist = haversine_km(lat, lng, dlat, dlng)
        if dist > radius_km:
            continue

        specialty_score = _specialty_match_score(doc, tags)
        partner_bonus = 30.0 if doc.get("is_partner", True) else 0.0
        verified_bonus = 20.0 if doc.get("is_verified") else 5.0
        rank_score = specialty_score + partner_bonus + verified_bonus + max(0, 50 - dist * 2)

        name = doc.get("name") or f"{doc.get('first_name', '')} {doc.get('last_name', '')}".strip()
        clinic = doc.get("clinic_name") or doc.get("institution") or f"{name} Dental Clinic"

        results.append({
            "tier": "platform",
            "dentist_id": str(doc["_id"]),
            "place_id": None,
            "name": name,
            "lat": dlat,
            "lng": dlng,
            "address": doc.get("location", ""),
            "phone": doc.get("phone"),
            "rating": doc.get("rating"),
            "distance_km": round(dist, 2),
            "specialties": tags,
            "is_partner": doc.get("is_partner", True),
            "is_verified": doc.get("is_verified", False),
            "clinic_name": clinic,
            "degree": doc.get("degree"),
            "profile_image": doc.get("profile_image"),
            "recommendation_reason": f"Platform partner matched for {issue.replace('_', ' ')}",
            "rank_score": rank_score,
        })

    results.sort(key=lambda x: x["rank_score"], reverse=True)
    return results[:limit]
