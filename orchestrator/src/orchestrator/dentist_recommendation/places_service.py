"""Legacy Places Service Adapter — delegates to OpenStreetMap Overpass discovery.

Google Maps / Places has been removed. This module is retained for backward-compatibility.
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.dentist_recommendation.osm_dentists import (
    haversine_km,
    search_osm_dentists,
)

logger = logging.getLogger(__name__)


async def search_nearby_dentists(
    lat: float,
    lng: float,
    issue: str,
    radius_m: int = 10000,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search for nearby general dentists using OpenStreetMap / Overpass."""
    radius_km = radius_m / 1000.0
    return await search_osm_dentists(lat, lng, radius_km=radius_km, limit=limit)
