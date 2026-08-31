"""Google Geocoding API helper."""

from __future__ import annotations

import logging

import httpx

from orchestrator.config import settings

logger = logging.getLogger(__name__)


def _maps_key() -> str:
    return settings.google_maps_api_key.strip()


async def geocode_address(address: str) -> tuple[float, float] | None:
    """Return (lat, lng) for an address string, or None if geocoding fails."""
    api_key = _maps_key()
    if not api_key or not address.strip():
        return None

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address.strip(), "key": api_key}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, params=params)
            res.raise_for_status()
            data = res.json()
    except Exception as exc:
        logger.warning("[GEOCODE] Failed for '%s': %s", address[:60], exc)
        return None

    if data.get("status") != "OK" or not data.get("results"):
        logger.warning("[GEOCODE] No results for '%s' status=%s", address[:60], data.get("status"))
        return None

    loc = data["results"][0]["geometry"]["location"]
    return float(loc["lat"]), float(loc["lng"])
