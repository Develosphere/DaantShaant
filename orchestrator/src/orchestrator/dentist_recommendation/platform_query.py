"""Query registered platform dentists from PostgreSQL."""

from __future__ import annotations

from typing import Any

from orchestrator.db.session import async_session_factory
from orchestrator.dentist_recommendation.condition_mapping import specialist_tags_for_issue
from orchestrator.dentist_recommendation.geocoding import geocode_address
from orchestrator.dentist_recommendation.places_service import haversine_km
from orchestrator.repositories import DentistRepository


def _specialty_match_score(dentist, tags: list[str]) -> float:
    specialties = dentist.specialties or []
    if isinstance(specialties, dict):
        specialties = list(specialties.values())
    haystack = " ".join(
        [
            dentist.specialized_training or "",
            dentist.degree or "",
            dentist.institution or "",
            dentist.clinic_name or "",
            " ".join(str(item) for item in specialties),
        ]
    ).lower()
    return sum(25.0 for tag in tags if tag.lower() in haystack) if tags else 10.0


async def search_platform_dentists(
    lat: float,
    lng: float,
    issue: str,
    radius_km: float = 25.0,
    limit: int = 10,
) -> list[dict[str, Any]]:
    tags = specialist_tags_for_issue(issue)
    async with async_session_factory() as session:
        async with session.begin():
            rows = await DentistRepository(session).list_platform()
            results: list[dict[str, Any]] = []
            for dentist, owner in rows:
                if dentist.latitude is None or dentist.longitude is None:
                    coords = await geocode_address(dentist.address or "")
                    if not coords:
                        continue
                    dentist.latitude, dentist.longitude = coords
                distance = haversine_km(
                    lat, lng, float(dentist.latitude), float(dentist.longitude)
                )
                if distance > radius_km:
                    continue
                rank_score = (
                    _specialty_match_score(dentist, tags)
                    + (30.0 if dentist.is_partner else 0.0)
                    + (20.0 if dentist.is_verified else 5.0)
                    + max(0, 50 - distance * 2)
                )
                dentist_specs = dentist.specialties or []
                if isinstance(dentist_specs, dict):
                    dentist_specs = list(dentist_specs.values())
                elif isinstance(dentist_specs, str):
                    dentist_specs = [dentist_specs]
                if not dentist_specs:
                    dentist_specs = ["general"]

                results.append(
                    {
                        "tier": "platform",
                        "dentist_id": str(dentist.id),
                        "place_id": None,
                        "name": dentist.name,
                        "lat": float(dentist.latitude),
                        "lng": float(dentist.longitude),
                        "address": dentist.address or "",
                        "phone": dentist.phone,
                        "rating": dentist.rating,
                        "distance_km": round(distance, 2),
                        "specialties": [str(s) for s in dentist_specs],
                        "is_partner": dentist.is_partner,
                        "is_verified": dentist.is_verified,
                        "clinic_name": dentist.clinic_name or f"{dentist.name} Dental Clinic",
                        "degree": dentist.degree,
                        "profile_image": owner.profile_image_url if owner else None,
                        "recommendation_reason": (
                            f"Platform dentist matched for {issue.replace('_', ' ')}"
                        ),
                        "rank_score": rank_score,
                    }
                )
    results.sort(key=lambda item: item["rank_score"], reverse=True)
    return results[:limit]
