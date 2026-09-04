"""Unit and mocked integration tests for Phase 10.4.1:
Stale / Missing / Unowned / Malformed scan_id Resilience in Dentist Discovery.

Requirements covered:
1. No scan_id -> dentist recommendation runs normally
2. Valid owned scan_id -> scan_id passed through to recommendation/session
3. Valid UUID but missing in DB -> discovery still runs, downstream receives scan_id=None
4. Valid UUID but belongs to another user -> discovery still runs, scan context discarded
5. Malformed scan_id (non-UUID string) -> discovery still runs, scan_id=None
6. No scan data or unowned scan context is leaked in any invalid/unowned case
7. HTTP route level verification: POST /portal/recommend/dentists/ returns 200 OK (never 404)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator.dentist_portal.models import (
    DentistPin,
    DentistRecommendRequest,
    DentistRecommendResponse,
)
from orchestrator.dentist_recommendation.routes import recommend_dentists, router as dentist_router
from orchestrator.dentist_portal.auth import get_current_patient
from orchestrator.db.session import get_db_session


def _run(coro):
    return asyncio.run(coro)


SAMPLE_DENTIST_PINS = [
    {
        "dentist_id": None,
        "place_id": "osm:node:101",
        "name": "City Dental Clinic",
        "clinic_name": "City Dental Clinic",
        "lat": 24.861,
        "lng": 67.002,
        "address": "Main Street, Karachi",
        "phone": "+92 21 11112222",
        "website": None,
        "rating": 4.5,
        "review_count": 12,
        "distance_km": 1.2,
        "specialties": ["general"],
        "is_partner": False,
        "tier": "external",
        "source": "osm",
        "is_verified": False,
        "experience_years": 0,
        "consultation_fee": None,
        "specialized_training": None,
        "degree": None,
        "profile_image": None,
        "recommendation_reason": "Nearest general dental clinic",
        "sources": ["osm"],
        "source_count": 1,
    }
]


# ---------------------------------------------------------------------------
# Test 1: No scan_id -> dentist recommendation runs normally
# ---------------------------------------------------------------------------
def test_1_no_scan_id_runs_recommendation():
    user_id = uuid4()
    patient_user = {"user_id": user_id, "role": "patient"}
    mock_session = AsyncMock()

    req = DentistRecommendRequest(
        issue="toothache",
        lat=24.86,
        lng=67.00,
        severity="moderate",
        scan_id=None,
    )

    with patch(
        "orchestrator.dentist_recommendation.routes.ScanRepository"
    ) as MockScanRepo, patch(
        "orchestrator.dentist_recommendation.routes.run_dentist_recommendation",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = {
            "session_id": str(uuid4()),
            "patient_lat": 24.86,
            "patient_lng": 67.00,
            "issue": "toothache",
            "dentists": SAMPLE_DENTIST_PINS,
            "search_radius_km": 5.0,
        }

        resp = _run(recommend_dentists(req=req, user=patient_user, session=mock_session))

        assert isinstance(resp, DentistRecommendResponse)
        assert len(resp.dentists) == 1
        assert resp.dentists[0].name == "City Dental Clinic"
        # Verify ScanRepository was not called
        MockScanRepo.assert_not_called()
        # Verify downstream recommendation received scan_id=None
        mock_run.assert_awaited_once()
        assert mock_run.call_args.kwargs["scan_id"] is None
        assert mock_run.call_args.kwargs["patient_id"] == str(user_id)


# ---------------------------------------------------------------------------
# Test 2: Valid owned scan_id -> scan_id passed through
# ---------------------------------------------------------------------------
def test_2_valid_owned_scan_id_passed_through():
    user_id = uuid4()
    owned_scan_id = uuid4()
    patient_user = {"user_id": user_id, "role": "patient"}
    mock_session = AsyncMock()

    req = DentistRecommendRequest(
        issue="cavity",
        lat=24.86,
        lng=67.00,
        severity="moderate",
        scan_id=str(owned_scan_id),
    )

    mock_scan = MagicMock()
    mock_scan.id = owned_scan_id
    mock_scan.patient_user_id = user_id

    with patch(
        "orchestrator.dentist_recommendation.routes.ScanRepository"
    ) as MockScanRepo, patch(
        "orchestrator.dentist_recommendation.routes.run_dentist_recommendation",
        new_callable=AsyncMock,
    ) as mock_run:
        repo_instance = MockScanRepo.return_value
        repo_instance.get_owned = AsyncMock(return_value=mock_scan)

        mock_run.return_value = {
            "session_id": str(uuid4()),
            "patient_lat": 24.86,
            "patient_lng": 67.00,
            "issue": "cavity",
            "dentists": SAMPLE_DENTIST_PINS,
            "search_radius_km": 5.0,
        }

        resp = _run(recommend_dentists(req=req, user=patient_user, session=mock_session))

        assert isinstance(resp, DentistRecommendResponse)
        repo_instance.get_owned.assert_awaited_once_with(owned_scan_id, user_id)
        mock_run.assert_awaited_once()
        # The valid owned scan_id MUST be passed through
        assert mock_run.call_args.kwargs["scan_id"] == str(owned_scan_id)


# ---------------------------------------------------------------------------
# Test 3: Valid but missing scan_id (not in DB) -> continues with scan_id=None
# ---------------------------------------------------------------------------
def test_3_valid_uuid_missing_in_db_continues_with_none():
    user_id = uuid4()
    missing_scan_id = uuid4()
    patient_user = {"user_id": user_id, "role": "patient"}
    mock_session = AsyncMock()

    req = DentistRecommendRequest(
        issue="bleeding gums",
        lat=24.86,
        lng=67.00,
        severity="moderate",
        scan_id=str(missing_scan_id),
    )

    with patch(
        "orchestrator.dentist_recommendation.routes.ScanRepository"
    ) as MockScanRepo, patch(
        "orchestrator.dentist_recommendation.routes.run_dentist_recommendation",
        new_callable=AsyncMock,
    ) as mock_run:
        repo_instance = MockScanRepo.return_value
        # Missing scan returns None
        repo_instance.get_owned = AsyncMock(return_value=None)

        mock_run.return_value = {
            "session_id": str(uuid4()),
            "patient_lat": 24.86,
            "patient_lng": 67.00,
            "issue": "bleeding gums",
            "dentists": SAMPLE_DENTIST_PINS,
            "search_radius_km": 8.0,
        }

        # Must NOT raise HTTPException 404
        resp = _run(recommend_dentists(req=req, user=patient_user, session=mock_session))

        assert isinstance(resp, DentistRecommendResponse)
        repo_instance.get_owned.assert_awaited_once_with(missing_scan_id, user_id)
        mock_run.assert_awaited_once()
        # Safely dropped: scan_id=None passed downstream
        assert mock_run.call_args.kwargs["scan_id"] is None


# ---------------------------------------------------------------------------
# Test 4: Valid UUID but belonging to another user -> scan context discarded
# ---------------------------------------------------------------------------
def test_4_unowned_scan_id_safely_discarded():
    user_id = uuid4()
    other_user_scan_id = uuid4()
    patient_user = {"user_id": user_id, "role": "patient"}
    mock_session = AsyncMock()

    req = DentistRecommendRequest(
        issue="orthodontics",
        lat=24.86,
        lng=67.00,
        severity="moderate",
        scan_id=str(other_user_scan_id),
    )

    with patch(
        "orchestrator.dentist_recommendation.routes.ScanRepository"
    ) as MockScanRepo, patch(
        "orchestrator.dentist_recommendation.routes.run_dentist_recommendation",
        new_callable=AsyncMock,
    ) as mock_run:
        repo_instance = MockScanRepo.return_value
        # get_owned checks Scan.patient_user_id == user["user_id"], returns None for other user
        repo_instance.get_owned = AsyncMock(return_value=None)

        mock_run.return_value = {
            "session_id": str(uuid4()),
            "patient_lat": 24.86,
            "patient_lng": 67.00,
            "issue": "orthodontics",
            "dentists": SAMPLE_DENTIST_PINS,
            "search_radius_km": 5.0,
        }

        # Must NOT fail and must NOT attach unowned scan
        resp = _run(recommend_dentists(req=req, user=patient_user, session=mock_session))

        assert isinstance(resp, DentistRecommendResponse)
        repo_instance.get_owned.assert_awaited_once_with(other_user_scan_id, user_id)
        mock_run.assert_awaited_once()
        # Downstream receives scan_id=None, protecting unowned scan record
        assert mock_run.call_args.kwargs["scan_id"] is None


# ---------------------------------------------------------------------------
# Test 5: Malformed scan_id -> continues with scan_id=None
# ---------------------------------------------------------------------------
def test_5_malformed_scan_id_continues_with_none():
    user_id = uuid4()
    patient_user = {"user_id": user_id, "role": "patient"}
    mock_session = AsyncMock()

    # Various malformed strings
    malformed_cases = [
        "not-a-valid-uuid",
        "undefined",
        "null",
        "12345",
        "xyz-abc-123",
    ]

    for bad_id in malformed_cases:
        req = DentistRecommendRequest(
            issue="routine checkup",
            lat=24.86,
            lng=67.00,
            severity="moderate",
            scan_id=bad_id,
        )

        with patch(
            "orchestrator.dentist_recommendation.routes.ScanRepository"
        ) as MockScanRepo, patch(
            "orchestrator.dentist_recommendation.routes.run_dentist_recommendation",
            new_callable=AsyncMock,
        ) as mock_run:
            repo_instance = MockScanRepo.return_value

            mock_run.return_value = {
                "session_id": str(uuid4()),
                "patient_lat": 24.86,
                "patient_lng": 67.00,
                "issue": "routine checkup",
                "dentists": SAMPLE_DENTIST_PINS,
                "search_radius_km": 3.0,
            }

            # Must NOT raise HTTPException 400
            resp = _run(recommend_dentists(req=req, user=patient_user, session=mock_session))

            assert isinstance(resp, DentistRecommendResponse)
            # ScanRepository.get_owned should NOT even be called for unparseable UUID
            repo_instance.get_owned.assert_not_called()
            mock_run.assert_awaited_once()
            assert mock_run.call_args.kwargs["scan_id"] is None


# ---------------------------------------------------------------------------
# Test 6: Security - No scan data leaked in invalid/unowned case
# ---------------------------------------------------------------------------
def test_6_no_scan_data_leaked_in_invalid_unowned_cases():
    user_id = uuid4()
    attacker_or_stale_scan_id = uuid4()
    patient_user = {"user_id": user_id, "role": "patient"}
    mock_session = AsyncMock()

    req = DentistRecommendRequest(
        issue="sensitive check",
        lat=24.86,
        lng=67.00,
        severity="moderate",
        scan_id=str(attacker_or_stale_scan_id),
    )

    with patch(
        "orchestrator.dentist_recommendation.routes.ScanRepository"
    ) as MockScanRepo, patch(
        "orchestrator.dentist_recommendation.routes.run_dentist_recommendation",
        new_callable=AsyncMock,
    ) as mock_run:
        repo_instance = MockScanRepo.return_value
        repo_instance.get_owned = AsyncMock(return_value=None)

        mock_run.return_value = {
            "session_id": str(uuid4()),
            "patient_lat": 24.86,
            "patient_lng": 67.00,
            "issue": "sensitive check",
            "dentists": SAMPLE_DENTIST_PINS,
            "search_radius_km": 5.0,
        }

        resp = _run(recommend_dentists(req=req, user=patient_user, session=mock_session))

        # Check response dictionary
        resp_dict = resp.model_dump()
        # Scan ID must NOT appear anywhere in the response
        resp_str = str(resp_dict)
        assert str(attacker_or_stale_scan_id) not in resp_str
        assert "scan_id" not in resp_dict
        # Downstream must NOT have received attacker_or_stale_scan_id
        assert mock_run.call_args.kwargs["scan_id"] is None


# ---------------------------------------------------------------------------
# Test 7: HTTP route integration via FastAPI TestClient
# ---------------------------------------------------------------------------
def test_7_http_route_never_returns_404_or_400_for_scan_id():
    user_id = uuid4()
    missing_uuid = str(uuid4())

    test_app = FastAPI()
    test_app.include_router(dentist_router)

    async def mock_get_current_patient():
        return {"user_id": user_id, "role": "patient"}

    async def mock_get_db_session():
        yield AsyncMock()

    test_app.dependency_overrides[get_current_patient] = mock_get_current_patient
    test_app.dependency_overrides[get_db_session] = mock_get_db_session

    with patch(
        "orchestrator.dentist_recommendation.routes.ScanRepository"
    ) as MockScanRepo, patch(
        "orchestrator.dentist_recommendation.routes.run_dentist_recommendation",
        new_callable=AsyncMock,
    ) as mock_run:
        repo_instance = MockScanRepo.return_value
        repo_instance.get_owned = AsyncMock(return_value=None)

        mock_run.return_value = {
            "session_id": str(uuid4()),
            "patient_lat": 24.86,
            "patient_lng": 67.00,
            "issue": "tooth decay",
            "dentists": SAMPLE_DENTIST_PINS,
            "search_radius_km": 5.0,
        }

        client = TestClient(test_app)

        # 1. Missing / unowned scan UUID
        resp1 = client.post(
            "/portal/recommend/dentists/",
            json={
                "issue": "tooth decay",
                "lat": 24.86,
                "lng": 67.00,
                "scan_id": missing_uuid,
            },
        )
        assert resp1.status_code == 200, f"Expected 200 but got {resp1.status_code}: {resp1.text}"
        data1 = resp1.json()
        assert len(data1["dentists"]) == 1

        # 2. Malformed scan_id string
        resp2 = client.post(
            "/portal/recommend/dentists/",
            json={
                "issue": "tooth decay",
                "lat": 24.86,
                "lng": 67.00,
                "scan_id": "malformed-scan-id-xyz",
            },
        )
        assert resp2.status_code == 200, f"Expected 200 but got {resp2.status_code}: {resp2.text}"
        data2 = resp2.json()
        assert len(data2["dentists"]) == 1

        # 3. None / missing scan_id
        resp3 = client.post(
            "/portal/recommend/dentists/",
            json={
                "issue": "tooth decay",
                "lat": 24.86,
                "lng": 67.00,
            },
        )
        assert resp3.status_code == 200, f"Expected 200 but got {resp3.status_code}: {resp3.text}"

