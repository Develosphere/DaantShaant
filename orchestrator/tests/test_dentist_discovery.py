"""Tests for Phase 6 Fast Track: OSM Dentist Discovery + Deterministic Ranking.

These tests use mocked responses only and make ZERO real external network calls.
"""

import asyncio
import math
from unittest.mock import AsyncMock, patch
import pytest
import httpx

from orchestrator.dentist_recommendation.osm_dentists import (
    haversine_km,
    normalize_osm_element,
    search_osm_dentists,
)
from orchestrator.dentist_recommendation.ranking import (
    calculate_dentist_score,
    rank_dentists,
)
from orchestrator.dentist_recommendation.dentist_agent import run_dentist_recommendation
from orchestrator.dentist_portal.models import DentistPin, DentistRecommendResponse


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Test 1: OSM dentist normalized correctly
# ---------------------------------------------------------------------------
def test_osm_dentist_normalized_correctly():
    raw_node = {
        "type": "node",
        "id": 123456,
        "lat": 24.8607,
        "lon": 67.0011,
        "tags": {
            "name": "Al-Shifa Dental Care",
            "addr:street": "Main Boulevard",
            "addr:housenumber": "42-B",
            "addr:city": "Karachi",
            "phone": "+92 21 34567890",
            "website": "https://alshifadental.example.com",
            "healthcare:speciality": "orthodontics;periodontics",
        },
    }

    patient_lat = 24.8600
    patient_lng = 67.0000

    candidate = normalize_osm_element(raw_node, patient_lat, patient_lng)
    assert candidate is not None
    assert candidate["name"] == "Al-Shifa Dental Care"
    assert candidate["place_id"] == "osm:node:123456"
    assert candidate["lat"] == 24.8607
    assert candidate["lng"] == 67.0011
    assert "42-B Main Boulevard" in candidate["address"]
    assert "Karachi" in candidate["address"]
    assert candidate["phone"] == "+92 21 34567890"
    assert candidate["website"] == "https://alshifadental.example.com"
    assert "orthodontics" in candidate["specialties"]
    assert "periodontics" in candidate["specialties"]
    assert candidate["distance_km"] > 0.0


# ---------------------------------------------------------------------------
# Test 2: Missing OSM fields handled safely
# ---------------------------------------------------------------------------
def test_missing_osm_fields_handled_safely():
    # Way with center coordinates and minimal tags
    raw_way = {
        "type": "way",
        "id": 9999,
        "center": {"lat": 25.2048, "lon": 55.2708},
        "tags": {},
    }

    candidate = normalize_osm_element(raw_way, 25.2000, 55.2700)
    assert candidate is not None
    assert candidate["name"] == "Dental Clinic"
    assert candidate["place_id"] == "osm:way:9999"
    assert candidate["address"] == ""
    assert candidate["phone"] is None
    assert candidate["website"] is None
    assert candidate["specialties"] == ["general"]

    # Invalid element without coordinates returns None safely
    raw_invalid = {"type": "node", "id": 111, "tags": {"name": "No coords"}}
    assert normalize_osm_element(raw_invalid, 25.0, 55.0) is None


# ---------------------------------------------------------------------------
# Test 3: OSM dentist defaults registered/verified/partner=false & rating=None
# ---------------------------------------------------------------------------
def test_osm_dentist_defaults_false_and_no_fabricated_rating():
    raw_node = {
        "type": "node",
        "id": 888,
        "lat": 24.86,
        "lon": 67.00,
        "tags": {"name": "Community Clinic"},
    }
    candidate = normalize_osm_element(raw_node, 24.86, 67.00)
    assert candidate is not None
    assert candidate["source"] == "osm"
    assert candidate["is_registered"] is False
    assert candidate["is_verified"] is False
    assert candidate["is_partner"] is False
    assert candidate["rating"] is None  # Do NOT fabricate rating


# ---------------------------------------------------------------------------
# Test 4: Haversine distance correct
# ---------------------------------------------------------------------------
def test_haversine_distance_correct():
    # Karachi (24.8607, 67.0011) to Lahore (31.5204, 74.3587) ~ 1020-1040 km
    dist = haversine_km(24.8607, 67.0011, 31.5204, 74.3587)
    assert 1000.0 < dist < 1050.0

    # Same coordinates should be 0.0
    assert haversine_km(24.86, 67.00, 24.86, 67.00) == 0.0


# ---------------------------------------------------------------------------
# Test 5: Specialist match outranks closer specialty mismatch
# ---------------------------------------------------------------------------
def test_specialist_match_outranks_closer_mismatch():
    # Issue: orthodontics
    issue = "orthodontic alignment"

    # Clinic A: General dentist, 2 km away
    clinic_a = {
        "tier": "general",
        "name": "Nearby General Dentist",
        "lat": 24.86,
        "lng": 67.00,
        "distance_km": 2.0,
        "specialties": ["general"],
        "is_verified": False,
        "is_partner": False,
    }

    # Clinic B: Orthodontist specialist, 10 km away
    clinic_b = {
        "tier": "general",
        "name": "Far Orthodontics Specialist",
        "lat": 24.95,
        "lng": 67.10,
        "distance_km": 10.0,
        "specialties": ["orthodontist", "braces"],
        "is_verified": False,
        "is_partner": False,
    }

    ranked = rank_dentists([], [clinic_a, clinic_b], issue=issue)
    assert len(ranked) == 2
    # Clinic B must rank first due to specialist relevance
    assert ranked[0]["name"] == "Far Orthodontics Specialist"
    assert ranked[0]["rank"] == 1
    assert ranked[1]["name"] == "Nearby General Dentist"
    assert ranked[1]["rank"] == 2


# ---------------------------------------------------------------------------
# Test 6: Verified registered dentist ranking behavior
# ---------------------------------------------------------------------------
def test_verified_registered_dentist_boost():
    issue = "dental cavity"

    # Unverified OSM dentist at 5km
    osm_dentist = {
        "tier": "general",
        "source": "osm",
        "name": "Unverified OSM Clinic",
        "lat": 24.86,
        "lng": 67.00,
        "distance_km": 5.0,
        "specialties": ["general"],
        "is_verified": False,
        "is_partner": False,
    }

    # Verified Platform dentist at 5km with restorative training
    platform_dentist = {
        "tier": "platform",
        "source": "platform",
        "dentist_id": "00000000-0000-0000-0000-000000000001",
        "name": "Dr. Sarah (Verified)",
        "lat": 24.86,
        "lng": 67.00,
        "distance_km": 5.0,
        "specialties": ["restorative", "general"],
        "is_verified": True,
        "is_partner": False,
        "degree": "BDS, RDS",
    }

    ranked = rank_dentists([platform_dentist], [osm_dentist], issue=issue)
    assert ranked[0]["name"] == "Dr. Sarah (Verified)"
    assert ranked[0]["is_best"] is True


# ---------------------------------------------------------------------------
# Test 7: Partner status does not override specialist relevance
# ---------------------------------------------------------------------------
def test_partner_status_does_not_override_specialist_relevance():
    issue = "gingivitis gum disease"  # requires periodontist

    # Partner platform clinic that only does cosmetic / teeth whitening (mismatch)
    partner_mismatch = {
        "tier": "platform",
        "source": "platform",
        "dentist_id": "00000000-0000-0000-0000-000000000002",
        "name": "Glamour Whitening Studio (Partner)",
        "lat": 24.86,
        "lng": 67.00,
        "distance_km": 3.0,
        "specialties": ["cosmetic", "whitening"],
        "is_partner": True,
        "is_verified": True,
    }

    # Non-partner OSM clinic with periodontist specialist (exact clinical match)
    osm_periodontist = {
        "tier": "general",
        "source": "osm",
        "name": "Karachi Periodontics & Gum Care",
        "lat": 24.88,
        "lng": 67.02,
        "distance_km": 4.0,
        "specialties": ["periodontist", "gum treatment"],
        "is_partner": False,
        "is_verified": False,
    }

    ranked = rank_dentists([partner_mismatch], [osm_periodontist], issue=issue)
    # The specialist matching periodontist clinic must outrank the partner mismatch
    assert ranked[0]["name"] == "Karachi Periodontics & Gum Care"


# ---------------------------------------------------------------------------
# Test 8: Overpass failure falls back to DB dentists
# ---------------------------------------------------------------------------
def test_overpass_failure_falls_back_to_db_dentists():
    # Mock Overpass transport to simulate 504 Gateway Timeout
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, text="Gateway Timeout")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    osm_results = _run(search_osm_dentists(
        lat=24.86, lng=67.00, radius_km=10.0, client=mock_client
    ))
    # Should not raise; returns empty list gracefully
    assert osm_results == []

    # When merged with DB platform dentists, platform dentists are returned safely
    mock_platform = [
        {
            "tier": "platform",
            "source": "platform",
            "dentist_id": "11111111-1111-1111-1111-111111111111",
            "name": "Dr. Ahmed",
            "lat": 24.86,
            "lng": 67.00,
            "distance_km": 1.2,
            "specialties": ["general"],
            "is_verified": True,
            "is_partner": False,
        }
    ]
    ranked = rank_dentists(mock_platform, osm_results, issue="routine checkup")
    assert len(ranked) == 1
    assert ranked[0]["name"] == "Dr. Ahmed"


# ---------------------------------------------------------------------------
# Test 9: Raw Overpass response not exposed
# ---------------------------------------------------------------------------
def test_raw_overpass_response_not_exposed():
    raw_node = {
        "type": "node",
        "id": 555,
        "lat": 24.86,
        "lon": 67.00,
        "tags": {
            "name": "Safe Clinic",
            "amenity": "dentist",
            "source": "survey:2024",
            "osm:user": "secret_osm_user",
        },
    }
    candidate = normalize_osm_element(raw_node, 24.86, 67.00)
    assert candidate is not None
    # No raw OSM internal metadata leaked into Candidate schema
    assert "osm:user" not in candidate
    assert "amenity" not in candidate
    assert candidate["tier"] in ("platform", "general")


# ---------------------------------------------------------------------------
# Test 10: Google Maps active runtime caller absent
# ---------------------------------------------------------------------------
def test_google_maps_active_runtime_absent():
    # Ensure no active dependency on Google Maps runtime in dentist recommendation
    import orchestrator.dentist_recommendation.places_service as ps
    import orchestrator.dentist_recommendation.geocoding as gc
    import orchestrator.dentist_recommendation.autocomplete_service as ac

    # Check that modules do not contain maps.googleapis.com
    import inspect
    assert "maps.googleapis.com" not in inspect.getsource(ps)
    assert "maps.googleapis.com" not in inspect.getsource(gc)
    assert "maps.googleapis.com" not in inspect.getsource(ac)
    assert "places.googleapis.com" not in inspect.getsource(ac)


# ---------------------------------------------------------------------------
# Test 11: API response compatible with DentistRecommendResponse & DentistPin
# ---------------------------------------------------------------------------
def test_api_response_compatible():
    candidate_dict = {
        "tier": "general",
        "source": "osm",
        "dentist_id": None,
        "place_id": "osm:node:123",
        "name": "Civic Dental Care",
        "lat": 24.86,
        "lng": 67.00,
        "address": "Karachi",
        "phone": "+92 300 1234567",
        "website": "https://civicdental.example.com",
        "rating": None,
        "distance_km": 1.5,
        "specialties": ["general"],
        "is_partner": False,
        "is_verified": False,
        "is_registered": False,
        "is_best": True,
        "rank": 1,
        "clinic_name": "Civic Dental Care",
        "degree": None,
        "profile_image": None,
        "recommendation_reason": "Top nearby clinic",
    }

    pin = DentistPin(**candidate_dict)
    assert pin.name == "Civic Dental Care"
    assert pin.source == "osm"
    assert pin.website == "https://civicdental.example.com"
    assert pin.rating is None

    response = DentistRecommendResponse(
        session_id="00000000-0000-0000-0000-000000000000",
        issue="cavity",
        patient_lat=24.86,
        patient_lng=67.00,
        dentists=[pin],
    )
    assert len(response.dentists) == 1
    assert response.dentists[0].is_best is True


# ---------------------------------------------------------------------------
# Test 12: LangGraph end-to-end execution
# ---------------------------------------------------------------------------
def test_dentist_recommendation_graph_execution():
    with patch(
        "orchestrator.dentist_recommendation.dentist_agent.search_platform_dentists",
        new_callable=AsyncMock,
    ) as mock_platform, patch(
        "orchestrator.dentist_recommendation.dentist_agent.search_osm_dentists",
        new_callable=AsyncMock,
    ) as mock_osm, patch(
        "orchestrator.dentist_recommendation.dentist_agent.async_session_factory"
    ) as mock_session_factory:
        # Mock database session
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        mock_platform.return_value = [
            {
                "tier": "platform",
                "source": "platform",
                "dentist_id": "22222222-2222-2222-2222-222222222222",
                "name": "Dr. Fatima (Platform)",
                "lat": 24.86,
                "lng": 67.00,
                "distance_km": 0.8,
                "specialties": ["general", "restorative"],
                "is_verified": True,
                "is_partner": True,
            }
        ]

        mock_osm.return_value = [
            {
                "tier": "general",
                "source": "osm",
                "dentist_id": None,
                "place_id": "osm:node:777",
                "name": "City Dental Clinic (OSM)",
                "lat": 24.87,
                "lng": 67.01,
                "distance_km": 2.1,
                "specialties": ["general"],
                "is_verified": False,
                "is_partner": False,
                "rating": None,
            }
        ]

        result = _run(run_dentist_recommendation(
            patient_id="00000000-0000-0000-0000-000000000099",
            issue="cavity suspect",
            lat=24.86,
            lng=67.00,
        ))

        assert "session_id" in result
        assert result["issue"] == "cavity suspect"
        assert len(result["dentists"]) == 2
        assert result["dentists"][0]["name"] == "Dr. Fatima (Platform)"
        assert result["dentists"][0]["is_best"] is True
        assert result["dentists"][1]["name"] == "City Dental Clinic (OSM)"
