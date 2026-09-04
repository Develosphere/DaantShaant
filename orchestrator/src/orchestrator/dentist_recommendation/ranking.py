"""Deterministic Dentist Ranking Engine for DaantShaant.

Priority rules:
1. Specialist match (recommended specialist from triage / scan issue)
2. Verified registered dentist (registered on platform with is_verified=True)
3. Distance (closer clinics rank higher)
4. Bayesian weighted rating & review confidence (where reviews exist)
5. Multi-source consensus & profile completeness
6. Partner status (small tiebreaker ONLY — never overrides specialist mismatch)
"""

from __future__ import annotations

import logging
import re
from typing import Any

from orchestrator.dentist_recommendation.condition_mapping import specialist_tags_for_issue
from orchestrator.dentist_recommendation.osm_dentists import haversine_km

logger = logging.getLogger(__name__)

BEST_MATCH_COUNT = 3

# Bayesian rating parameters
BAYESIAN_MIN_REVIEWS = 10.0
DEFAULT_PRIOR_RATING = 4.0


def calculate_bayesian_rating(
    rating: float | None,
    review_count: int | None,
    mean_rating: float = DEFAULT_PRIOR_RATING,
    min_reviews: float = BAYESIAN_MIN_REVIEWS,
) -> float | None:
    """Calculate Bayesian / weighted rating:

    weighted_rating = (v / (v + m)) * R + (m / (v + m)) * C
    where:
    - R = raw rating
    - v = review count
    - C = mean/prior rating
    - m = confidence threshold
    """
    if rating is None or rating <= 0:
        return None
    v = float(review_count) if review_count is not None and review_count > 0 else 1.0
    m = min_reviews
    return (v / (v + m)) * float(rating) + (m / (v + m)) * mean_rating


def calculate_dentist_score(
    dentist: dict[str, Any],
    specialist_tags: list[str],
    mean_rating: float = DEFAULT_PRIOR_RATING,
) -> float:
    """Calculate deterministic ranking score for a dentist candidate."""
    score = 0.0

    # 1. Specialist Match (Priority 1: Highest Weight)
    dentist_specialties = [str(s).lower() for s in dentist.get("specialties") or []]
    degree_text = str(dentist.get("degree") or "").lower()
    training_text = str(dentist.get("specialized_training") or "").lower()
    clinic_text = str(dentist.get("clinic_name") or dentist.get("name") or "").lower()

    haystack = " ".join(dentist_specialties + [degree_text, training_text, clinic_text])

    target_specialists = [
        t.lower()
        for t in specialist_tags
        if t.lower() not in ("general", "general dentist", "dentist")
    ]

    if target_specialists:
        for tag in target_specialists:
            if tag in haystack:
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
    dist_km = float(dentist.get("distance_km", 0.0))
    proximity_score = max(0.0, 100.0 - dist_km * 2.5)
    score += proximity_score

    # 4. Bayesian Weighted Rating & Review Quality
    raw_rating = dentist.get("rating")
    rev_count = dentist.get("review_count")
    if raw_rating is not None and raw_rating > 0:
        weighted = calculate_bayesian_rating(raw_rating, rev_count, mean_rating)
        if weighted is not None:
            score += weighted * 4.0

    # 5. Multi-Source Consensus & Profile Completeness
    source_count = dentist.get("source_count") or (len(dentist.get("sources", [])) if dentist.get("sources") else 1)
    if source_count > 1:
        score += min((source_count - 1) * 8.0, 24.0)

    # Profile completeness bonus (phone, address, website)
    if dentist.get("phone"):
        score += 5.0
    if dentist.get("website"):
        score += 5.0
    if dentist.get("address"):
        score += 5.0

    # 6. Partner Status (Tiebreaker only: +15 points)
    if is_partner:
        score += 15.0

    return score


def _normalize_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\s]", "", str(name or "").lower())
    words = [
        w
        for w in cleaned.split()
        if w not in ("dr", "doctor", "clinic", "dental", "hospital", "care", "center", "centre", "the", "and")
    ]
    return " ".join(words) if words else cleaned.strip()


def _normalize_phone_str(phone: str | None) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    if digits.startswith("92") and len(digits) > 9:
        digits = "0" + digits[2:]
    return digits


def _is_duplicate(cand: dict[str, Any], existing: dict[str, Any]) -> bool:
    # 1. Platform dentist_id match
    c_id = cand.get("dentist_id")
    e_id = existing.get("dentist_id")
    if c_id and e_id and str(c_id) == str(e_id):
        return True

    # 2. Place_id match
    c_pid = cand.get("place_id")
    e_pid = existing.get("place_id")
    if c_pid and e_pid and str(c_pid) == str(e_pid):
        return True

    # 3. Exact coordinates match (rounded to 4 decimals ~11 meters)
    c_lat, c_lng = float(cand.get("lat", 0.0)), float(cand.get("lng", 0.0))
    e_lat, e_lng = float(existing.get("lat", 0.0)), float(existing.get("lng", 0.0))
    if round(c_lat, 4) == round(e_lat, 4) and round(c_lng, 4) == round(e_lng, 4):
        return True

    # 4. Proximity within 80 meters with name overlap
    dist = haversine_km(c_lat, c_lng, e_lat, e_lng)
    if dist < 0.08:
        c_norm = _normalize_name(cand.get("name") or cand.get("clinic_name") or "")
        e_norm = _normalize_name(existing.get("name") or existing.get("clinic_name") or "")
        if not c_norm or not e_norm or c_norm in e_norm or e_norm in c_norm:
            return True
        c_words = set(c_norm.split())
        e_words = set(e_norm.split())
        if c_words and e_words and (c_words & e_words):
            return True

    # 5. Phone number match (min 7 digits)
    c_phone = _normalize_phone_str(cand.get("phone"))
    e_phone = _normalize_phone_str(existing.get("phone"))
    if c_phone and e_phone and len(c_phone) >= 7 and c_phone == e_phone:
        return True

    return False


def _merge_candidate(existing: dict[str, Any], new_cand: dict[str, Any]) -> dict[str, Any]:
    """Merge two matching candidates. Platform source always remains authoritative."""
    e_is_plat = existing.get("tier") == "platform" or existing.get("source") == "platform"
    n_is_plat = new_cand.get("tier") == "platform" or new_cand.get("source") == "platform"

    target = existing if e_is_plat or not n_is_plat else new_cand
    source = new_cand if target is existing else existing

    # Maintain multi-source list and count
    sources = list(target.get("sources") or ([target["source"]] if target.get("source") else []))
    new_source = source.get("source")
    if new_source and new_source not in sources:
        sources.append(new_source)
    target["sources"] = sources
    target["source_count"] = len(sources)

    if not target.get("phone") and source.get("phone"):
        target["phone"] = source["phone"]
    if not target.get("website") and source.get("website"):
        target["website"] = source["website"]
    if not target.get("address") and source.get("address"):
        target["address"] = source["address"]
    if target.get("rating") is None and source.get("rating") is not None:
        target["rating"] = source["rating"]
    if target.get("review_count") is None and source.get("review_count") is not None:
        target["review_count"] = source["review_count"]

    return target


def rank_dentists(
    platform_dentists: list[dict[str, Any]],
    osm_dentists: list[dict[str, Any]] | None = None,
    issue: str = "dental checkup",
    limit: int = 15,
    *,
    external_dentists: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Merge, deduplicate and rank platform and external dentists deterministically."""
    specialist_tags = specialist_tags_for_issue(issue)
    clean_issue = issue.replace("_", " ").strip()

    merged: list[dict[str, Any]] = []

    # 1. Add platform dentists (authoritative)
    for item in platform_dentists:
        item_copy = dict(item)
        if "sources" not in item_copy:
            item_copy["sources"] = [item_copy.get("source") or "platform"]
            item_copy["source_count"] = len(item_copy["sources"])

        # Check against already added platform items
        dup_idx = next((i for i, m in enumerate(merged) if _is_duplicate(item_copy, m)), None)
        if dup_idx is not None:
            merged[dup_idx] = _merge_candidate(merged[dup_idx], item_copy)
        else:
            merged.append(item_copy)

    # 2. Add external dentists (OSM, FSQ, Geoapify, etc.)
    ext_list = external_dentists if external_dentists is not None else (osm_dentists or [])
    for item in ext_list:
        item_copy = dict(item)
        if "sources" not in item_copy:
            item_copy["sources"] = [item_copy.get("source") or "osm"]
            item_copy["source_count"] = len(item_copy["sources"])

        dup_idx = next((i for i, m in enumerate(merged) if _is_duplicate(item_copy, m)), None)
        if dup_idx is not None:
            merged[dup_idx] = _merge_candidate(merged[dup_idx], item_copy)
        else:
            merged.append(item_copy)

    # Compute mean rating among candidates with ratings for local Bayesian prior
    ratings_available = [
        float(d["rating"]) for d in merged if d.get("rating") is not None and float(d["rating"]) > 0
    ]
    mean_candidate_rating = (
        sum(ratings_available) / len(ratings_available) if ratings_available else DEFAULT_PRIOR_RATING
    )

    # Calculate deterministic score for each merged candidate
    for cand in merged:
        cand["rank_score"] = calculate_dentist_score(cand, specialist_tags, mean_candidate_rating)

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
