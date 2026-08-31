"""Address autocomplete — Nominatim (reliable) with optional Google Places fallback."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from orchestrator.dentist_recommendation.geocoding import _maps_key, geocode_address

logger = logging.getLogger(__name__)

NOMINATIM_HEADERS = {
    "User-Agent": "DantShaant/1.0 (university dental project; contact@localhost)",
    "Accept": "application/json",
}


async def search_address_suggestions(query: str, limit: int = 6) -> list[dict[str, Any]]:
    """Return suggestions: [{ place_id, label, lat?, lng? }, ...]."""
    q = query.strip()
    if len(q) < 2:
        return []

    # Nominatim works without Google server-side key restrictions (PK/UAE focus).
    results = await _autocomplete_nominatim(q, limit)
    if results:
        return results

    api_key = _maps_key()
    if not api_key:
        return []

    results = await _autocomplete_places_new(q, limit, api_key)
    if results:
        return results

    return await _autocomplete_places_legacy(q, limit, api_key)


async def resolve_suggestion(
    place_id: str | None,
    label: str,
    lat: float | None = None,
    lng: float | None = None,
) -> dict[str, Any] | None:
    """Resolve a suggestion to lat/lng/label."""
    if lat is not None and lng is not None and label.strip():
        return {"lat": lat, "lng": lng, "label": label.strip()}

    if place_id and place_id.startswith("osm:"):
        resolved = await _resolve_nominatim_place(place_id.removeprefix("osm:"))
        if resolved:
            return resolved

    api_key = _maps_key()
    if api_key and place_id and not place_id.startswith("osm:"):
        resolved = await _place_details_new(place_id, api_key)
        if resolved:
            return resolved

    if label.strip():
        resolved = await _geocode_nominatim(label)
        if resolved:
            return resolved

        coords = await geocode_address(label)
        if coords:
            return {"lat": coords[0], "lng": coords[1], "label": label.strip()}

    return None


async def _autocomplete_nominatim(query: str, limit: int) -> list[dict[str, Any]]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "addressdetails": "0",
        "limit": str(limit),
        "countrycodes": "pk,ae",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(url, params=params, headers=NOMINATIM_HEADERS)
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


async def _resolve_nominatim_place(osm_id: str) -> dict[str, Any] | None:
    url = f"https://nominatim.openstreetmap.org/lookup"
    params = {"osm_ids": f"N{osm_id},W{osm_id},R{osm_id}", "format": "json"}

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(url, params=params, headers=NOMINATIM_HEADERS)
            res.raise_for_status()
            data = res.json()
    except Exception:
        return None

    if not data:
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


async def _geocode_nominatim(label: str) -> dict[str, Any] | None:
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": label.strip(), "format": "json", "limit": "1", "countrycodes": "pk,ae"}

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(url, params=params, headers=NOMINATIM_HEADERS)
            res.raise_for_status()
            data = res.json()
    except Exception:
        return None

    if not data:
        return None

    item = data[0]
    try:
        return {
            "lat": float(item["lat"]),
            "lng": float(item["lon"]),
            "label": item.get("display_name") or label.strip(),
        }
    except (KeyError, TypeError, ValueError):
        return None


async def _autocomplete_places_new(query: str, limit: int, api_key: str) -> list[dict[str, Any]]:
    url = "https://places.googleapis.com/v1/places:autocomplete"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
    }
    body = {
        "input": query,
        "includedRegionCodes": ["pk", "ae"],
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.post(url, headers=headers, json=body)
            if res.status_code != 200:
                return []
            data = res.json()
    except Exception:
        return []

    results: list[dict[str, Any]] = []
    for item in data.get("suggestions", [])[:limit]:
        pred = item.get("placePrediction")
        if not pred:
            continue
        label = (pred.get("text") or {}).get("text") or ""
        place_id = pred.get("placeId") or ""
        if label:
            results.append({"place_id": place_id, "label": label})

    return results


async def _autocomplete_places_legacy(query: str, limit: int, api_key: str) -> list[dict[str, Any]]:
    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": query,
        "types": "geocode",
        "key": api_key,
        "components": "country:pk|country:ae",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(url, params=params)
            res.raise_for_status()
            data = res.json()
    except Exception:
        return []

    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        return []

    results: list[dict[str, Any]] = []
    for pred in data.get("predictions", [])[:limit]:
        label = pred.get("description") or ""
        place_id = pred.get("place_id") or ""
        if label:
            results.append({"place_id": place_id, "label": label})

    return results


async def _place_details_new(place_id: str, api_key: str) -> dict[str, Any] | None:
    pid = place_id.removeprefix("places/")
    url = f"https://places.googleapis.com/v1/places/{quote(pid, safe='')}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "location,formattedAddress",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code != 200:
                return None
            data = res.json()
    except Exception:
        return None

    loc = data.get("location") or {}
    lat, lng = loc.get("latitude"), loc.get("longitude")
    label = data.get("formattedAddress") or ""
    if lat is None or lng is None:
        return None

    return {"lat": float(lat), "lng": float(lng), "label": label or f"{lat:.4f}, {lng:.4f}"}
