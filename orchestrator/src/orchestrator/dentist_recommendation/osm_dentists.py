# Third-party: OpenStreetMap / Overpass API
# Purpose: discover nearby dental clinics from public OSM data.
# No patient clinical data is transmitted; only geographic search coordinates.

from __future__ import annotations

import logging
import math
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OVERPASS_ENDPOINTS = [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
]
OVERPASS_ENDPOINT = OVERPASS_ENDPOINTS[0]
OVERPASS_TIMEOUT_SECONDS = 4.0

OVERPASS_HEADERS = {
    "User-Agent": "DaantShaant/1.0 (https://daantshaant.pk; contact@daantshaant.pk)",
    "Accept": "application/json",
}

# Simple short-lived in-memory cache to prevent duplicate external calls (30 min TTL)
_CACHE_TTL_SECONDS = 1800.0
_cache: dict[tuple[str, float, float, float], tuple[float, list[dict[str, Any]]]] = {}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate the great-circle distance between two points on the Earth."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _build_overpass_query(lat: float, lng: float, radius_m: int) -> str:
    return f"""[out:json][timeout:10];
(
  node["amenity"="dentist"](around:{radius_m},{lat},{lng});
  node["healthcare"="dentist"](around:{radius_m},{lat},{lng});
  way["amenity"="dentist"](around:{radius_m},{lat},{lng});
  way["healthcare"="dentist"](around:{radius_m},{lat},{lng});
);
out center tags;"""


def _extract_address(tags: dict[str, str]) -> str:
    street = tags.get("addr:street", "").strip()
    housenumber = tags.get("addr:housenumber", "").strip()
    city = tags.get("addr:city", "").strip()
    full = tags.get("addr:full", "").strip()

    if full:
        return full
    parts = []
    if housenumber and street:
        parts.append(f"{housenumber} {street}")
    elif street:
        parts.append(street)
    if city:
        parts.append(city)
    return ", ".join(parts)


def _extract_specialties(tags: dict[str, str]) -> list[str]:
    specialty_tag = tags.get("healthcare:speciality", "") or tags.get("dentist:speciality", "") or tags.get("speciality", "")
    specialties: list[str] = []
    if specialty_tag:
        for item in specialty_tag.replace(";", ",").split(","):
            cleaned = item.strip().lower()
            if cleaned:
                specialties.append(cleaned)
    if not specialties:
        specialties.append("general")
    return sorted(set(specialties))


def normalize_osm_element(
    elem: dict[str, Any], patient_lat: float, patient_lng: float
) -> dict[str, Any] | None:
    """Normalize a raw OSM node/way/relation element into internal DentistCandidate shape."""
    elem_type = elem.get("type", "node")
    elem_id = elem.get("id", "")
    tags = elem.get("tags") or {}

    lat = elem.get("lat")
    lng = elem.get("lon")
    if lat is None or lng is None:
        center = elem.get("center") or {}
        lat = center.get("lat")
        lng = center.get("lon")

    if lat is None or lng is None:
        return None

    lat = float(lat)
    lng = float(lng)
    dist = haversine_km(patient_lat, patient_lng, lat, lng)

    name = tags.get("name") or tags.get("operator") or "Dental Clinic"
    address = _extract_address(tags)
    phone = tags.get("phone") or tags.get("contact:phone")
    email = tags.get("email") or tags.get("contact:email")
    website = tags.get("website") or tags.get("contact:website")
    whatsapp = tags.get("whatsapp") or tags.get("contact:whatsapp")
    linkedin = tags.get("linkedin") or tags.get("contact:linkedin")
    specialties = _extract_specialties(tags)

    return {
        "tier": "general",
        "source": "osm",
        "dentist_id": None,
        "place_id": f"osm:{elem_type}:{elem_id}",
        "name": name,
        "lat": lat,
        "lng": lng,
        "address": address,
        "phone": phone,
        "email": email,
        "website": website,
        "whatsapp": whatsapp,
        "linkedin": linkedin,
        "rating": None,  # Explicitly None: do NOT fabricate rating for OSM
        "distance_km": round(dist, 2),
        "specialties": specialties,
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


async def search_osm_dentists(
    lat: float,
    lng: float,
    radius_km: float = 25.0,
    limit: int = 20,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Query OSM / Overpass API for dentists within radius_km.

    Returns normalized dentist candidates. Gracefully falls back to empty list on error.
    """
    cache_key = ("osm", round(lat, 3), round(lng, 3), round(radius_km, 1))
    now = time.time()
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if now - cached_time < _CACHE_TTL_SECONDS:
            return cached_data[:limit]

    radius_m = int(radius_km * 1000)
    query = _build_overpass_query(lat, lng, radius_m)

    data = None
    if client is not None:
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                res = await client.post(
                    endpoint,
                    data={"data": query},
                    headers=OVERPASS_HEADERS,
                    timeout=OVERPASS_TIMEOUT_SECONDS,
                )
                res.raise_for_status()
                data = res.json()
                break
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "[OVERPASS] Endpoint %s failed: status=%d http_code=%d exc=%s",
                    endpoint,
                    exc.response.status_code,
                    exc.response.status_code,
                    exc,
                )
                continue
            except httpx.TimeoutException as exc:
                logger.warning(
                    "[OVERPASS] Endpoint %s failed: status=timeout timeout_type=%s exc=%s",
                    endpoint,
                    type(exc).__name__,
                    exc,
                )
                continue
            except Exception as exc:
                logger.warning(
                    "[OVERPASS] Endpoint %s failed: status=error exc_type=%s exc=%s",
                    endpoint,
                    type(exc).__name__,
                    exc,
                )
                continue
    else:
        async with httpx.AsyncClient(timeout=OVERPASS_TIMEOUT_SECONDS) as local_client:
            for endpoint in OVERPASS_ENDPOINTS:
                try:
                    res = await local_client.post(
                        endpoint,
                        data={"data": query},
                        headers=OVERPASS_HEADERS,
                    )
                    res.raise_for_status()
                    data = res.json()
                    break
                except httpx.HTTPStatusError as exc:
                    logger.warning(
                        "[OVERPASS] Endpoint %s failed: status=%d http_code=%d exc=%s",
                        endpoint,
                        exc.response.status_code,
                        exc.response.status_code,
                        exc,
                    )
                    continue
                except httpx.TimeoutException as exc:
                    logger.warning(
                        "[OVERPASS] Endpoint %s failed: status=timeout timeout_type=%s exc=%s",
                        endpoint,
                        type(exc).__name__,
                        exc,
                    )
                    continue
                except Exception as exc:
                    logger.warning(
                        "[OVERPASS] Endpoint %s failed: status=error exc_type=%s exc=%s",
                        endpoint,
                        type(exc).__name__,
                        exc,
                    )
                    continue

    if not data:
        return []

    elements = data.get("elements", [])
    results: list[dict[str, Any]] = []
    for elem in elements:
        candidate = normalize_osm_element(elem, lat, lng)
        if candidate:
            results.append(candidate)

    results.sort(key=lambda d: d["distance_km"])
    _cache[cache_key] = (now, results)
    return results[:limit]
