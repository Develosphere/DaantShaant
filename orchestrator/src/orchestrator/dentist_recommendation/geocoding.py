# Third-party: OpenStreetMap / Nominatim
# Purpose: geocode address strings to geographic coordinates.
# No patient clinical data is transmitted; only address text.

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_HEADERS = {
    "User-Agent": "DaantShaant/1.0 (oral health screening platform; contact@daantshaant.app)",
    "Accept": "application/json",
}

_COORDINATE_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


async def geocode_address(address: str, lang: str = "en") -> tuple[float, float] | None:
    """Return (lat, lng) for an address string or coordinate string, or None if geocoding fails."""
    clean = address.strip()
    if not clean:
        return None

    # Check if input is already "lat, lng" coordinates
    coord_match = _COORDINATE_RE.match(clean)
    if coord_match:
        try:
            return float(coord_match.group(1)), float(coord_match.group(2))
        except ValueError:
            pass

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": clean,
        "format": "json",
        "limit": "1",
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
        logger.warning("[GEOCODE] Nominatim geocoding failed for '%s': %s", clean[:60], exc)
        return None

    if not data or not isinstance(data, list):
        return None

    item = data[0]
    try:
        return float(item["lat"]), float(item["lon"])
    except (KeyError, ValueError, TypeError):
        return None

