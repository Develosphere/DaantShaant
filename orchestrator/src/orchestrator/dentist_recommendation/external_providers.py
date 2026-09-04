# Third-party: External Dentist Discovery Providers
# Purpose: discover nearby dental clinics from public/free-tier geodata APIs.
# Overpass is the primary open source. Foursquare and Geoapify are optional.
# No patient clinical data is transmitted; only geographic search coordinates.

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from orchestrator.dentist_recommendation.osm_dentists import (
    haversine_km,
    search_osm_dentists,
)

logger = logging.getLogger(__name__)

# Cache TTL for external providers (30 mins)
_CACHE_TTL_SECONDS = 1800.0
_provider_cache: dict[tuple[str, float, float, float], tuple[float, list[dict[str, Any]]]] = {}


def _clean_str(val: Any) -> str:
    return str(val or "").strip()


async def search_foursquare_dentists(
    lat: float,
    lng: float,
    radius_km: float = 25.0,
    limit: int = 20,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Query Foursquare Places API for dentists if FOURSQUARE_API_KEY is configured.

    Returns empty list safely if unconfigured or on any technical failure.
    """
    api_key = os.getenv("FOURSQUARE_API_KEY", "").strip()
    if not api_key:
        return []

    cache_key = ("foursquare", round(lat, 3), round(lng, 3), round(radius_km, 1))
    now = time.time()
    if cache_key in _provider_cache:
        cached_time, cached_data = _provider_cache[cache_key]
        if now - cached_time < _CACHE_TTL_SECONDS:
            return cached_data[:limit]

    radius_m = min(int(radius_km * 1000), 100000)
    url = "https://api.foursquare.com/v3/places/search"
    headers = {
        "Authorization": api_key,
        "Accept": "application/json",
    }
    params = {
        "ll": f"{lat},{lng}",
        "radius": str(radius_m),
        "categories": "15007,15008",  # Dentist, Dental Clinic
        "limit": str(min(limit, 50)),
    }

    try:
        if client is not None:
            res = await client.get(url, headers=headers, params=params, timeout=8.0)
            res.raise_for_status()
            data = res.json()
        else:
            async with httpx.AsyncClient(timeout=8.0) as local_client:
                res = await local_client.get(url, headers=headers, params=params)
                res.raise_for_status()
                data = res.json()
    except Exception as exc:
        logger.warning("[FOURSQUARE] Query failed: %s", exc)
        return []

    results: list[dict[str, Any]] = []
    items = data.get("results", []) if isinstance(data, dict) else []
    for item in items:
        fsq_id = item.get("fsq_id", "")
        name = item.get("name") or "Dental Clinic"
        geocodes = item.get("geocodes", {}).get("main", {})
        c_lat = geocodes.get("latitude")
        c_lng = geocodes.get("longitude")
        if c_lat is None or c_lng is None:
            continue

        c_lat, c_lng = float(c_lat), float(c_lng)
        dist = haversine_km(lat, lng, c_lat, c_lng)
        loc = item.get("location", {})
        addr_parts = [loc.get("address", ""), loc.get("locality", ""), loc.get("region", "")]
        address = ", ".join(p.strip() for p in addr_parts if p.strip())
        phone = item.get("tel") or item.get("phone")
        email = item.get("email")
        website = item.get("website")
        rating = item.get("rating")
        norm_rating = round(float(rating) / 2.0, 1) if rating is not None else None

        results.append(
            {
                "tier": "general",
                "source": "foursquare",
                "dentist_id": None,
                "place_id": f"fsq:{fsq_id}",
                "name": name,
                "lat": c_lat,
                "lng": c_lng,
                "address": address,
                "phone": phone,
                "email": email,
                "website": website,
                "whatsapp": None,
                "linkedin": None,
                "rating": norm_rating,
                "distance_km": round(dist, 2),
                "specialties": ["general"],
                "is_partner": False,
                "is_verified": False,
                "is_registered": False,
                "is_best": False,
                "rank": 0,
                "clinic_name": name,
                "degree": None,
                "profile_image": None,
                "recommendation_reason": f"Nearby dental clinic ({round(dist, 1)} km)",
                "rank_score": 0.0,
            }
        )

    if results:
        _provider_cache[cache_key] = (now, results)
    return results[:limit]


async def search_geoapify_dentists(
    lat: float,
    lng: float,
    radius_km: float = 25.0,
    limit: int = 20,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Query Geoapify Places API for dentists if GEOAPIFY_API_KEY is configured.

    Returns empty list safely if unconfigured or on any technical failure.
    """
    api_key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if not api_key:
        return []

    cache_key = ("geoapify", round(lat, 3), round(lng, 3), round(radius_km, 1))
    now = time.time()
    if cache_key in _provider_cache:
        cached_time, cached_data = _provider_cache[cache_key]
        if now - cached_time < _CACHE_TTL_SECONDS:
            return cached_data[:limit]

    radius_m = min(int(radius_km * 1000), 100000)
    url = "https://api.geoapify.com/v2/places"
    params = {
        "categories": "healthcare.dentist",
        "filter": f"circle:{lng},{lat},{radius_m}",
        "bias": f"proximity:{lng},{lat}",
        "limit": str(min(limit, 50)),
        "apiKey": api_key,
    }

    try:
        if client is not None:
            res = await client.get(url, params=params, timeout=8.0)
            res.raise_for_status()
            data = res.json()
        else:
            async with httpx.AsyncClient(timeout=8.0) as local_client:
                res = await local_client.get(url, params=params)
                res.raise_for_status()
                data = res.json()
    except Exception as exc:
        logger.warning("[GEOAPIFY] Query failed: %s", exc)
        return []

    results: list[dict[str, Any]] = []
    features = data.get("features", []) if isinstance(data, dict) else []
    for feat in features:
        props = feat.get("properties", {})
        c_lat = props.get("lat")
        c_lng = props.get("lon")
        if c_lat is None or c_lng is None:
            continue

        c_lat, c_lng = float(c_lat), float(c_lng)
        dist = haversine_km(lat, lng, c_lat, c_lng)
        name = props.get("name") or "Dental Clinic"
        address = props.get("formatted") or props.get("address_line2") or ""
        phone = props.get("contact", {}).get("phone") if isinstance(props.get("contact"), dict) else None
        email = props.get("contact", {}).get("email") if isinstance(props.get("contact"), dict) else props.get("email")
        website = props.get("website") or (props.get("contact", {}).get("website") if isinstance(props.get("contact"), dict) else None)
        place_id = props.get("place_id") or f"geo:{c_lat}_{c_lng}"

        results.append(
            {
                "tier": "general",
                "source": "geoapify",
                "dentist_id": None,
                "place_id": str(place_id),
                "name": name,
                "lat": c_lat,
                "lng": c_lng,
                "address": address,
                "phone": phone,
                "email": email,
                "website": website,
                "whatsapp": None,
                "linkedin": None,
                "rating": None,
                "distance_km": round(dist, 2),
                "specialties": ["general"],
                "is_partner": False,
                "is_verified": False,
                "is_registered": False,
                "is_best": False,
                "rank": 0,
                "clinic_name": name,
                "degree": None,
                "profile_image": None,
                "recommendation_reason": f"Nearby dental clinic ({round(dist, 1)} km)",
                "rank_score": 0.0,
            }
        )

    if results:
        _provider_cache[cache_key] = (now, results)
    return results[:limit]


async def discover_external_dentists(
    lat: float,
    lng: float,
    radius_km: float = 25.0,
    limit: int = 30,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Discover nearby external dentist clinics using available sources.

    Always queries OpenStreetMap / Overpass as primary.
    If optional API keys exist (FOURSQUARE_API_KEY, GEOAPIFY_API_KEY),
    queries them and merges results.
    Failures in any provider are isolated and never crash the discovery.
    """
    candidates: list[dict[str, Any]] = []

    # 1. Primary: OSM / Overpass
    try:
        osm_results = await search_osm_dentists(lat, lng, radius_km=radius_km, limit=limit, client=client)
        candidates.extend(osm_results)
    except Exception as exc:
        logger.warning("[EXTERNAL-DISCOVERY] OSM query failed: %s", exc)

    # 2. Optional: Foursquare
    if os.getenv("FOURSQUARE_API_KEY", "").strip():
        try:
            fsq_results = await search_foursquare_dentists(lat, lng, radius_km=radius_km, limit=limit, client=client)
            candidates.extend(fsq_results)
        except Exception as exc:
            logger.warning("[EXTERNAL-DISCOVERY] Foursquare query failed: %s", exc)

    # 3. Optional: Geoapify
    if os.getenv("GEOAPIFY_API_KEY", "").strip():
        try:
            geo_results = await search_geoapify_dentists(lat, lng, radius_km=radius_km, limit=limit, client=client)
            candidates.extend(geo_results)
        except Exception as exc:
            logger.warning("[EXTERNAL-DISCOVERY] Geoapify query failed: %s", exc)

    return candidates
