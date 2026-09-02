# Third-party: OpenStreetMap / Nominatim
# Purpose: address autocomplete and location resolution for PK / UAE search.
# No patient clinical data is transmitted; only search query strings.

from __future__ import annotations

import logging
from typing import Any

import httpx

from orchestrator.dentist_recommendation.geocoding import NOMINATIM_HEADERS, geocode_address

logger = logging.getLogger(__name__)


async def search_address_suggestions(query: str, limit: int = 6, lang: str = "en") -> list[dict[str, Any]]:
    """Return suggestions: [{ place_id, label, lat?, lng? }, ...]."""
    q = query.strip()
    if len(q) < 2:
        return []

    return await _autocomplete_nominatim(q, limit, lang=lang)


async def resolve_suggestion(
    place_id: str | None,
    label: str,
    lat: float | None = None,
    lng: float | None = None,
    lang: str = "en",
) -> dict[str, Any] | None:
    """Resolve a suggestion to lat/lng/label."""
    if lat is not None and lng is not None and label.strip():
        return {"lat": lat, "lng": lng, "label": label.strip()}

    if place_id and place_id.startswith("osm:"):
        resolved = await _resolve_nominatim_place(place_id.removeprefix("osm:"), lang=lang)
        if resolved:
            return resolved

    if label.strip():
        coords = await geocode_address(label, lang=lang)
        if coords:
            return {"lat": coords[0], "lng": coords[1], "label": label.strip()}

    return None


async def _autocomplete_nominatim(query: str, limit: int, lang: str = "en") -> list[dict[str, Any]]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "addressdetails": "0",
        "limit": str(limit),
        "countrycodes": "pk,ae",
        "accept-language": lang,
    }
    headers = {**NOMINATIM_HEADERS, "Accept-Language": lang}

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(url, params=params, headers=headers)
            res.raise_for_status()
            data = res.json()
    except Exception as exc:
        logger.warning("[AUTOCOMPLETE] Nominatim failed: %s", exc)
        return []

    results: list[dict[str, Any]] = []
    for item in data[:limit]:
        label = item.get("display_name") or ""
        osm_id = str(item.get("osm_id") or item.get("place_id") or "")
        try:
            lat = float(item["lat"])
            lng = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if label and osm_id:
            results.append({
                "place_id": f"osm:{osm_id}",
                "label": label,
                "lat": lat,
                "lng": lng,
            })

    return results


async def _resolve_nominatim_place(osm_id: str, lang: str = "en") -> dict[str, Any] | None:
    url = "https://nominatim.openstreetmap.org/lookup"
    params = {"osm_ids": f"N{osm_id},W{osm_id},R{osm_id}", "format": "json", "accept-language": lang}
    headers = {**NOMINATIM_HEADERS, "Accept-Language": lang}

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(url, params=params, headers=headers)
            res.raise_for_status()
            data = res.json()
    except Exception:
        return None

    if not data or not isinstance(data, list):
        return None

    item = data[0]
    try:
        return {
            "lat": float(item["lat"]),
            "lng": float(item["lon"]),
            "label": item.get("display_name") or "",
        }
    except (KeyError, TypeError, ValueError):
        return None

