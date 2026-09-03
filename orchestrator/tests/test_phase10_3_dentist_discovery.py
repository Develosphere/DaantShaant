"""Tests for Phase 10.3: Live Nearby Dentist Discovery Integration.

Covers:
- Exact browser coordinates reach discovery backend unchanged
- Adaptive search radius: 3km, 5km, 8km, and 10km fallback
- Minimum result target behavior
- Multi-source external provider abstraction and failure isolation
- Deduplication across platform and external providers
- Clinical specialist weighting without deleting general clinics
- Missing ratings preserved as None (no fake 0 stars)
- Route direct coordinates handling
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import httpx

from orchestrator.dentist_recommendation.dentist_agent import (
    SEARCH_RADII_KM,
    MIN_RESULT_TARGET,
    run_dentist_recommendation,
)
from orchestrator.dentist_recommendation.ranking import (
    calculate_dentist_score,
    rank_dentists,
    _is_duplicate,
    _merge_candidate,
)
from orchestrator.dentist_recommendation.external_providers import (
    search_foursquare_dentists,
    search_geoapify_dentists,
    discover_external_dentists,
)
from orchestrator.dentist_portal.models import DentistRecommendRequest, DentistRecommendResponse


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Test 1: Adaptive radius stops at 3km when target is reached
# ---------------------------------------------------------------------------
def test_adaptive_radius_stops_at_3km_when_target_reached():
    six_external = [
        {
            "tier": "general",
            "source": "osm",
            "dentist_id": None,
            "place_id": f"osm:node:{i}",
            "name": f"Clinic {i}",
            "lat": 24.86 + i * 0.002,
            "lng": 67.00 + i * 0.002,
            "distance_km": 1.0 + i * 0.2,
            "specialties": ["general"],
            "is_partner": False,
            "is_verified": False,
            "rating": None,
        }
        for i in range(6)
    ]

    mock_external = AsyncMock(return_value=six_external)
    mock_platform = AsyncMock(return_value=[])

    with patch("orchestrator.dentist_recommendation.dentist_agent._discover_external", mock_external), \
         patch("orchestrator.dentist_recommendation.dentist_agent.search_platform_dentists", mock_platform), \
         patch("orchestrator.dentist_recommendation.dentist_agent.async_session_factory") as mock_session_factory:
        
        mock_session_factory.return_value.__aenter__.return_value = AsyncMock()

        result = _run(run_dentist_recommendation(
            patient_id="00000000-0000-0000-0000-000000000001",
            issue="general checkup",
            lat=24.8600,
            lng=67.0000,
        ))

        # Stopped at 3 km because 6 clinics >= target 5
        assert result["search_radius_km"] == 3.0
        assert len(result["dentists"]) == 6
        # External discovery was called only once (for 3.0 km)
        assert mock_external.call_count == 1
        call_args = mock_external.call_args[1]
        assert call_args["radius"] == 3.0


# ---------------------------------------------------------------------------
# Test 2: Adaptive radius expands to 5km when 3km is insufficient
# ---------------------------------------------------------------------------
def test_adaptive_radius_expands_to_5km():
    two_at_3km = [
        {
            "tier": "general",
            "source": "osm",
            "dentist_id": None,
            "place_id": f"osm:node:{i}",
            "name": f"Clinic {i}",
            "lat": 24.86 + i * 0.002,
            "lng": 67.00 + i * 0.002,
            "distance_km": 1.5,
            "specialties": ["general"],
            "is_partner": False,
            "is_verified": False,
            "rating": None,
        }
        for i in range(2)
    ]

    six_at_5km = [
        {
            "tier": "general",
            "source": "osm",
            "dentist_id": None,
            "place_id": f"osm:node:{i}",
            "name": f"Clinic {i}",
            "lat": 24.86 + i * 0.005,
            "lng": 67.00 + i * 0.005,
            "distance_km": 3.8,
            "specialties": ["general"],
            "is_partner": False,
            "is_verified": False,
            "rating": None,
        }
        for i in range(6)
    ]

    async def side_effect(lat, lng, radius):
        if radius == 3.0:
            return two_at_3km
        elif radius == 5.0:
            return six_at_5km
        return []

    mock_external = AsyncMock(side_effect=side_effect)

    with patch("orchestrator.dentist_recommendation.dentist_agent._discover_external", mock_external), \
         patch("orchestrator.dentist_recommendation.dentist_agent.search_platform_dentists", AsyncMock(return_value=[])), \
         patch("orchestrator.dentist_recommendation.dentist_agent.async_session_factory") as mock_session_factory:

        mock_session_factory.return_value.__aenter__.return_value = AsyncMock()

        result = _run(run_dentist_recommendation(
            patient_id="00000000-0000-0000-0000-000000000001",
            issue="general checkup",
            lat=24.8600,
            lng=67.0000,
        ))

        assert result["search_radius_km"] == 5.0
        assert len(result["dentists"]) == 6
        assert mock_external.call_count == 2


# ---------------------------------------------------------------------------
# Test 3: Adaptive radius expands to 8km
# ---------------------------------------------------------------------------
def test_adaptive_radius_expands_to_8km():
    async def side_effect(lat, lng, radius):
        if radius in (3.0, 5.0):
            return [{"tier": "general", "source": "osm", "dentist_id": None, "place_id": "1", "name": "C1", "lat": 24.86, "lng": 67.0, "distance_km": 1.0, "specialties": ["general"], "is_partner": False, "is_verified": False, "rating": None}]
        elif radius == 8.0:
            return [
                {"tier": "general", "source": "osm", "dentist_id": None, "place_id": str(i), "name": f"C{i}", "lat": 24.86 + i*0.01, "lng": 67.0 + i*0.01, "distance_km": 6.0, "specialties": ["general"], "is_partner": False, "is_verified": False, "rating": None}
                for i in range(5)
            ]
        return []

    mock_external = AsyncMock(side_effect=side_effect)

    with patch("orchestrator.dentist_recommendation.dentist_agent._discover_external", mock_external), \
         patch("orchestrator.dentist_recommendation.dentist_agent.search_platform_dentists", AsyncMock(return_value=[])), \
         patch("orchestrator.dentist_recommendation.dentist_agent.async_session_factory") as mock_session_factory:

        mock_session_factory.return_value.__aenter__.return_value = AsyncMock()

        result = _run(run_dentist_recommendation(
            patient_id="00000000-0000-0000-0000-000000000001",
            issue="general checkup",
            lat=24.8600,
            lng=67.0000,
        ))

        assert result["search_radius_km"] == 8.0
        assert mock_external.call_count == 3


# ---------------------------------------------------------------------------
# Test 4: Adaptive radius exhausts all and returns 10km fallback
# ---------------------------------------------------------------------------
def test_adaptive_radius_falls_back_to_10km():
    sparse_clinic = [
        {"tier": "general", "source": "osm", "dentist_id": None, "place_id": "c1", "name": "Sparse Clinic", "lat": 24.86, "lng": 67.0, "distance_km": 2.0, "specialties": ["general"], "is_partner": False, "is_verified": False, "rating": None}
    ]

    mock_external = AsyncMock(return_value=sparse_clinic)

    with patch("orchestrator.dentist_recommendation.dentist_agent._discover_external", mock_external), \
         patch("orchestrator.dentist_recommendation.dentist_agent.search_platform_dentists", AsyncMock(return_value=[])), \
         patch("orchestrator.dentist_recommendation.dentist_agent.async_session_factory") as mock_session_factory:

        mock_session_factory.return_value.__aenter__.return_value = AsyncMock()

        result = _run(run_dentist_recommendation(
            patient_id="00000000-0000-0000-0000-000000000001",
            issue="general checkup",
            lat=24.8600,
            lng=67.0000,
        ))

        # Reached final fallback radius (10 km)
        assert result["search_radius_km"] == 10.0
        assert len(result["dentists"]) == 1
        assert mock_external.call_count == len(SEARCH_RADII_KM)


# ---------------------------------------------------------------------------
# Test 5: External provider failure does not crash discovery
# ---------------------------------------------------------------------------
def test_external_provider_timeout_does_not_crash():
    mock_external = AsyncMock(side_effect=httpx.TimeoutException("Overpass timeout"))
    platform_dentists = [
        {
            "tier": "platform",
            "source": "platform",
            "dentist_id": "11111111-1111-1111-1111-111111111111",
            "name": "Dr. Resilience",
            "lat": 24.86,
            "lng": 67.00,
            "distance_km": 1.2,
            "specialties": ["general"],
            "is_partner": True,
            "is_verified": True,
            "rating": 4.9,
        }
    ]

    with patch("orchestrator.dentist_recommendation.dentist_agent._discover_external", mock_external), \
         patch("orchestrator.dentist_recommendation.dentist_agent.search_platform_dentists", AsyncMock(return_value=platform_dentists)), \
         patch("orchestrator.dentist_recommendation.dentist_agent.async_session_factory") as mock_session_factory:

        mock_session_factory.return_value.__aenter__.return_value = AsyncMock()

        result = _run(run_dentist_recommendation(
            patient_id="00000000-0000-0000-0000-000000000001",
            issue="routine checkup",
            lat=24.8600,
            lng=67.0000,
        ))

        assert len(result["dentists"]) == 1
        assert result["dentists"][0]["name"] == "Dr. Resilience"
        assert result["dentists"][0]["tier"] == "platform"


# ---------------------------------------------------------------------------
# Test 6: Multi-source duplicate dentists merge correctly (platform authoritative)
# ---------------------------------------------------------------------------
def test_multi_source_duplicate_dentists_merge():
    platform_cand = {
        "tier": "platform",
        "source": "platform",
        "dentist_id": "11111111-1111-1111-1111-111111111111",
        "name": "Fatima Dental Clinic",
        "lat": 24.8601,
        "lng": 67.0002,
        "address": "Suite 101, Karachi",
        "phone": "+92 21 34567890",
        "website": None,
        "distance_km": 0.5,
        "specialties": ["general", "restorative"],
        "is_partner": True,
        "is_verified": True,
        "rating": 4.8,
    }

    osm_duplicate = {
        "tier": "general",
        "source": "osm",
        "dentist_id": None,
        "place_id": "osm:node:9999",
        "name": "Fatima Dental Clinic",
        "lat": 24.8602,
        "lng": 67.0003,
        "address": "Street 4, Karachi",
        "phone": "+92 21 34567890",
        "website": "https://fatimadental.pk",
        "distance_km": 0.52,
        "specialties": ["general"],
        "is_partner": False,
        "is_verified": False,
        "rating": None,
    }

    ranked = rank_dentists([platform_cand], [osm_duplicate], issue="restorative")
    assert len(ranked) == 1
    # Platform record is authoritative
    assert ranked[0]["tier"] == "platform"
    assert ranked[0]["dentist_id"] == "11111111-1111-1111-1111-111111111111"
    # External metadata backfilled (website)
    assert ranked[0]["website"] == "https://fatimadental.pk"
    assert ranked[0]["is_verified"] is True


# ---------------------------------------------------------------------------
# Test 7: Unknown specialty external clinic is not automatically deleted
# ---------------------------------------------------------------------------
def test_unknown_specialty_external_clinic_not_deleted():
    general_clinic = {
        "tier": "general",
        "source": "osm",
        "name": "Neighborhood Dental Care",
        "lat": 24.86,
        "lng": 67.00,
        "distance_km": 1.0,
        "specialties": ["general"],
        "is_partner": False,
        "is_verified": False,
        "rating": None,
    }

    ranked = rank_dentists([], [general_clinic], issue="orthodontics")
    # Must NOT be deleted merely because it doesn't match orthodontics
    assert len(ranked) == 1
    assert ranked[0]["name"] == "Neighborhood Dental Care"


# ---------------------------------------------------------------------------
# Test 8: Exact current coordinates remain search center
# ---------------------------------------------------------------------------
def test_exact_current_lat_lng_remains_search_center():
    exact_lat = 24.905865
    exact_lng = 67.030718

    mock_external = AsyncMock(return_value=[])
    mock_platform = AsyncMock(return_value=[])

    with patch("orchestrator.dentist_recommendation.dentist_agent._discover_external", mock_external), \
         patch("orchestrator.dentist_recommendation.dentist_agent.search_platform_dentists", mock_platform), \
         patch("orchestrator.dentist_recommendation.dentist_agent.async_session_factory") as mock_session_factory:

        mock_session_factory.return_value.__aenter__.return_value = AsyncMock()

        result = _run(run_dentist_recommendation(
            patient_id="00000000-0000-0000-0000-000000000001",
            issue="routine checkup",
            lat=exact_lat,
            lng=exact_lng,
        ))

        # Search center in output matches exact input coordinates
        assert result["patient_lat"] == exact_lat
        assert result["patient_lng"] == exact_lng

        # Platform search was called with exact coordinates
        platform_call_args = mock_platform.call_args[0]
        assert platform_call_args[0] == exact_lat
        assert platform_call_args[1] == exact_lng


# ---------------------------------------------------------------------------
# Test 9: Optional providers without API keys skip safely without error
# ---------------------------------------------------------------------------
def test_optional_providers_without_keys_skip_safely():
    with patch.dict("os.environ", {}, clear=True):
        fsq = _run(search_foursquare_dentists(24.86, 67.00))
        assert fsq == []

        geo = _run(search_geoapify_dentists(24.86, 67.00))
        assert geo == []


# ---------------------------------------------------------------------------
# Test 10: Missing rating is preserved as None, never 0 stars
# ---------------------------------------------------------------------------
def test_missing_rating_preserved_as_none():
    osm_cand = {
        "tier": "general",
        "source": "osm",
        "name": "Public Dental Health Center",
        "lat": 24.86,
        "lng": 67.00,
        "distance_km": 2.0,
        "specialties": ["general"],
        "is_partner": False,
        "is_verified": False,
        "rating": None,
    }
    ranked = rank_dentists([], [osm_cand], issue="checkup")
    assert len(ranked) == 1
    assert ranked[0]["rating"] is None


# ---------------------------------------------------------------------------
# Test 11: API response serialization preserves dentists and coordinates
# ---------------------------------------------------------------------------
def test_api_response_dentists_survive_serialization():
    from orchestrator.dentist_portal.models import DentistPin, DentistRecommendResponse
    from orchestrator.dentist_recommendation.osm_dentists import OVERPASS_ENDPOINTS

    # Verify working endpoints are prioritized
    assert "lz4.overpass-api.de" in OVERPASS_ENDPOINTS[0]

    raw_dentist = {
        "tier": "general",
        "source": "osm",
        "dentist_id": None,
        "place_id": "osm:node:123456",
        "name": "Saddar Dental Clinic",
        "lat": 24.8596,
        "lng": 67.0308,
        "address": "Saddar, Karachi",
        "phone": "+92 300 1234567",
        "website": None,
        "rating": None,
        "distance_km": 0.35,
        "specialties": ["general"],
        "is_partner": False,
        "is_verified": False,
        "is_registered": False,
        "is_best": True,
        "rank": 1,
        "clinic_name": "Saddar Dental Clinic",
        "degree": None,
        "profile_image": None,
        "recommendation_reason": "Top nearby clinic for dental checkup (0.4 km)",
    }

    pin = DentistPin(**raw_dentist)
    resp = DentistRecommendResponse(
        session_id="test-session-123",
        issue="dental checkup",
        patient_lat=24.8596,
        patient_lng=67.0308,
        dentists=[pin],
        search_radius_km=3.0,
    )

    data = resp.model_dump()
    assert len(data["dentists"]) == 1
    assert data["dentists"][0]["name"] == "Saddar Dental Clinic"
    assert data["dentists"][0]["lat"] == 24.8596
    assert data["dentists"][0]["lng"] == 67.0308
    assert data["dentists"][0]["distance_km"] == 0.35
    assert data["search_radius_km"] == 3.0

