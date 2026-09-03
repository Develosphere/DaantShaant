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


def format_location_label(item: dict[str, Any], lang: str = "en") -> str:
    """Build a concise, language-preferred, deduplicated location label."""
    namedetails = item.get("namedetails") or {}
    address = item.get("address") or {}

    is_urdu = lang.lower().startswith("ur")

    # 1. Place name preference
    if is_urdu:
        place_name = (
            namedetails.get("name:ur")
            or namedetails.get("official_name:ur")
            or namedetails.get("short_name:ur")
            or item.get("name")
            or ""
        )
    else:
        place_name = (
            namedetails.get("name:en")
            or namedetails.get("official_name:en")
            or namedetails.get("short_name:en")
            or item.get("name")
            or ""
        )

    # 2. Extract address components concisely: [Place/Suburb, City/Town, Region/State, Country]
    suburb = (
        address.get("suburb")
        or address.get("neighbourhood")
        or address.get("quarter")
        or address.get("residential")
        or address.get("city_district")
        or ""
    )
    city = (
        address.get("city")
        or address.get("town")
        or address.get("municipality")
        or address.get("village")
        or address.get("county")
        or ""
    )
    state = (
        address.get("state")
        or address.get("province")
        or address.get("state_district")
        or address.get("region")
        or ""
    )
    country = address.get("country") or ""

    # Check names associated with the primary place to avoid Latin/Urdu duplicate suburb
    place_aliases = {
        (item.get("name") or "").lower(),
        (namedetails.get("name") or "").lower(),
        (namedetails.get("name:en") or "").lower(),
        (namedetails.get("name:ur") or "").lower(),
        place_name.lower(),
    }
    place_aliases.discard("")

    components: list[str] = []

    if place_name:
        components.append(place_name)

    if suburb and suburb.lower() not in place_aliases and suburb.lower() not in [c.lower() for c in components]:
        components.append(suburb)

    if city and city.lower() not in place_aliases and city.lower() not in [c.lower() for c in components]:
        components.append(city)

    if state and state.lower() not in place_aliases and state.lower() not in [c.lower() for c in components]:
        components.append(state)

    if country and country.lower() not in [c.lower() for c in components]:
        components.append(country)

    if components:
        return ", ".join(components)

    # Fallback to raw display_name with concise parts
    raw_display = item.get("display_name") or ""
    if raw_display:
        parts = [p.strip() for p in raw_display.split(",") if p.strip()]
        if len(parts) > 4:
            return ", ".join([parts[0], parts[1], parts[-2], parts[-1]])
        return raw_display

    return place_name or ""


async def _autocomplete_nominatim(query: str, limit: int, lang: str = "en") -> list[dict[str, Any]]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "addressdetails": "1",
        "namedetails": "1",
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
        label = format_location_label(item, lang=lang) or item.get("display_name") or ""
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
    params = {
        "osm_ids": f"N{osm_id},W{osm_id},R{osm_id}",
        "format": "json",
        "addressdetails": "1",
        "namedetails": "1",
        "accept-language": lang,
    }
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
    label = format_location_label(item, lang=lang) or item.get("display_name") or ""
    try:
        return {
            "lat": float(item["lat"]),
            "lng": float(item["lon"]),
            "label": label,
        }
    except (KeyError, TypeError, ValueError):
        return None

