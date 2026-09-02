"""Deterministic Dentist Ranking Engine for DaantShaant.

Priority rules:
1. Specialist match (recommended specialist from triage / scan issue)
2. Verified registered dentist (registered on platform with is_verified=True)
3. Distance (closer clinics rank higher)
4. Partner status (small tiebreaker ONLY — never overrides specialist mismatch)
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.dentist_recommendation.condition_mapping import specialist_tags_for_issue

logger = logging.getLogger(__name__)

BEST_MATCH_COUNT = 3


def calculate_dentist_score(
    dentist: dict[str, Any],
    specialist_tags: list[str],
) -> float:
    """Calculate deterministic ranking score for a dentist candidate."""
    score = 0.0

    # 1. Specialist Match (Priority 1: Highest Weight)
    # Check if dentist specialties/training/degree match the required specialist tags
    dentist_specialties = [str(s).lower() for s in dentist.get("specialties") or []]
    degree_text = str(dentist.get("degree") or "").lower()
    training_text = str(dentist.get("specialized_training") or "").lower()
    clinic_text = str(dentist.get("clinic_name") or dentist.get("name") or "").lower()

    haystack = " ".join(dentist_specialties + [degree_text, training_text, clinic_text])

    target_specialists = [t.lower() for t in specialist_tags if t.lower() != "general"]
    
    specialist_matched = False
    if target_specialists:
        for tag in target_specialists:
            if tag in haystack:
                specialist_matched = True
                score += 1000.0  # Massive priority for specialist match
                break
    else:
        # For routine general checkups, any general dentist or clinic is a match
        score += 200.0

    # 2. Platform / Verification Status (Priority 2)
    is_platform = dentist.get("tier") == "platform" or dentist.get("source") == "platform"
    is_verified = bool(dentist.get("is_verified"))
    is_partner = bool(dentist.get("is_partner"))

    if is_platform:
        score += 100.0
        if is_verified:
            score += 150.0

    # 3. Distance (Priority 3)
    # Proximity adds up to 100 points (100 - 2 * distance_km)
    dist_km = float(dentist.get("distance_km", 0.0))
    proximity_score = max(0.0, 100.0 - dist_km * 2.5)
    score += proximity_score

    # 4. Partner Status (Tiebreaker only: +15 points)
    # Never enough to beat specialist match (+1000) or massive distance delta
    if is_partner:
        score += 15.0

    # 5. Rating bonus if verified/available
    rating = dentist.get("rating")
    if rating is not None and rating > 0:
        score += float(rating) * 2.0

    return score


def rank_dentists(
    platform_dentists: list[dict[str, Any]],
    osm_dentists: list[dict[str, Any]],
    issue: str,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """Merge and rank platform and OSM dentists deterministically."""
    specialist_tags = specialist_tags_for_issue(issue)
    clean_issue = issue.replace("_", " ").strip()

    seen_keys: set[str] = set()
    merged: list[dict[str, Any]] = []

    # 1. Add platform dentists
    for item in platform_dentists:
        key = (
            item.get("dentist_id")
            or f"{round(item.get('lat', 0), 4)}_{round(item.get('lng', 0), 4)}"
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        item_copy = dict(item)
        item_copy["rank_score"] = calculate_dentist_score(item_copy, specialist_tags)
        merged.append(item_copy)

    # 2. Add OSM dentists (skip duplicates with matching coordinates)
    for item in osm_dentists:
        coord_key = f"{round(item.get('lat', 0), 4)}_{round(item.get('lng', 0), 4)}"
        place_key = item.get("place_id") or coord_key
        if coord_key in seen_keys or place_key in seen_keys:
            continue
        seen_keys.add(coord_key)
        seen_keys.add(place_key)
        item_copy = dict(item)
        item_copy["rank_score"] = calculate_dentist_score(item_copy, specialist_tags)
        merged.append(item_copy)

    # Sort primarily by rank_score (descending), then distance (ascending)
    merged.sort(key=lambda d: (-d.get("rank_score", 0.0), d.get("distance_km", 0.0)))

    # Assign ranks and recommendation reasons
    for i, item in enumerate(merged):
        item["rank"] = i + 1
        item["is_best"] = i < BEST_MATCH_COUNT

        is_plat = item.get("tier") == "platform" or item.get("source") == "platform"
        dist_str = f"{item.get('distance_km', 0.0):.1f} km away"

        if item["is_best"]:
            if is_plat:
                item["recommendation_reason"] = (
                    f"Verified partner match for your {clean_issue} scan ({dist_str})"
                )
            else:
                item["recommendation_reason"] = (
                    f"Top nearby clinic for {clean_issue} ({dist_str})"
                )
        else:
            if is_plat:
                item["recommendation_reason"] = (
                    f"Platform dentist near you ({dist_str})"
                )
            else:
                item["recommendation_reason"] = (
                    f"Nearby dental clinic ({dist_str})"
                )

    return merged[:limit]
