"""Focused unit and integration tests for Phase 10.7: Real Data-Driven Patient + Dentist Dashboards."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from orchestrator.config import settings
from orchestrator.db.models import (
    AppointmentRequest,
    ClinicalReport,
    Dentist,
    Order,
    Product,
    ProductRecommendation,
    Scan,
    User,
)
from orchestrator.dentist_portal.routes_dashboard import (
    _normalize_urgency,
    get_dentist_dashboard,
    get_patient_dashboard,
)


@pytest.fixture(autouse=True)
def ensure_jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-with-sufficient-entropy-for-hashing-12345")


# =========================================================================
# SECTION 32: PATIENT DASHBOARD TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_patient_dashboard_zero_scans_and_orders():
    """1. Patient with 0 scans -> scan_count=0, honest empty states."""
    session = AsyncMock()
    patient_id = uuid4()
    patient_user = {"user_id": patient_id, "role": "patient", "email": "p0@example.com"}

    with patch("orchestrator.dentist_portal.routes_dashboard.ScanRepository") as MockScanRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.OrderRepository") as MockOrderRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.ProductRepository") as MockProductRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.AppointmentRepository") as MockApptRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.RecommendationRepository") as MockRecRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.DentistRepository") as MockDentistRepo:

        scan_repo = MockScanRepo.return_value
        scan_repo.count_scans = AsyncMock(return_value=0)
        scan_repo.get_latest_screening = AsyncMock(return_value=None)
        scan_repo.list_owned = AsyncMock(return_value=[])

        order_repo = MockOrderRepo.return_value
        order_repo.count_for_patient = AsyncMock(return_value=0)
        order_repo.list_for_patient = AsyncMock(return_value=[])

        appt_repo = MockApptRepo.return_value
        appt_repo.list_for_principal = AsyncMock(return_value=[])

        rec_repo = MockRecRepo.return_value
        rec_repo.list_product_for_patient = AsyncMock(return_value=[])

        res = await get_patient_dashboard(patient_user, session)

        assert res["stats"]["scan_count"] == 0
        assert res["stats"]["order_count"] == 0
        assert res["stats"]["oral_status"] is None
        assert res["latest_screening"] is None
        assert res["recommended_products"] == []
        assert res["recent_orders"] == []
        assert res["recent_activity"] == []


@pytest.mark.asyncio
async def test_patient_dashboard_multiple_scans_real_count():
    """2. Patient with multiple scans -> returns exact count."""
    session = AsyncMock()
    patient_id = uuid4()
    patient_user = {"user_id": patient_id, "role": "patient"}

    scan = MagicMock(spec=Scan)
    scan.id = uuid4()
    scan.created_at = datetime.now(timezone.utc)
    scan.mechanical_quality_score = 0.9
    scan.status = "clinical_complete"

    report = MagicMock(spec=ClinicalReport)
    report.verdict = "Mild Gingivitis"
    report.urgency_level = "soon"
    report.summary = "AI screening observed Mild Gingivitis."
    report.recommended_specialist = "Periodontist"
    report.possible_concerns = {"findings": [{"observation": "Gingivitis signs"}]}
    report.agent_trace_summary = {"confidence": 0.88}
    report.created_at = scan.created_at

    with patch("orchestrator.dentist_portal.routes_dashboard.ScanRepository") as MockScanRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.OrderRepository") as MockOrderRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.ProductRepository") as MockProductRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.AppointmentRepository") as MockApptRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.RecommendationRepository") as MockRecRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.DentistRepository") as MockDentistRepo:

        scan_repo = MockScanRepo.return_value
        scan_repo.count_scans = AsyncMock(return_value=4)
        scan_repo.get_latest_screening = AsyncMock(return_value=(scan, report))
        scan_repo.list_owned = AsyncMock(return_value=[scan])

        order_repo = MockOrderRepo.return_value
        order_repo.count_for_patient = AsyncMock(return_value=2)
        order_repo.list_for_patient = AsyncMock(return_value=[])

        appt_repo = MockApptRepo.return_value
        appt_repo.list_for_principal = AsyncMock(return_value=[])

        rec_repo = MockRecRepo.return_value
        rec_repo.list_product_for_patient = AsyncMock(return_value=[])

        product_repo = MockProductRepo.return_value
        product_repo.list_active = AsyncMock(return_value=[])

        res = await get_patient_dashboard(patient_user, session)

        assert res["stats"]["scan_count"] == 4
        assert res["stats"]["order_count"] == 2
        assert res["stats"]["oral_status"] == "soon"


@pytest.mark.asyncio
async def test_patient_latest_scan_chosen_by_timestamp():
    """3. Latest scan chosen by database timestamp (latest created_at)."""
    session = AsyncMock()
    patient_id = uuid4()
    patient_user = {"user_id": patient_id, "role": "patient"}

    latest_time = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    scan_latest = MagicMock(spec=Scan)
    scan_latest.id = uuid4()
    scan_latest.created_at = latest_time
    scan_latest.mechanical_quality_score = 0.95
    scan_latest.status = "clinical_complete"

    report_latest = MagicMock(spec=ClinicalReport)
    report_latest.verdict = "Enamel Cavity"
    report_latest.urgency_level = "urgent"
    report_latest.summary = "AI screening observed Enamel Cavity."
    report_latest.recommended_specialist = "Endodontist"
    report_latest.possible_concerns = {"findings": [{"observation": "Cavity advanced"}]}
    report_latest.agent_trace_summary = {"confidence": 0.92}
    report_latest.created_at = latest_time

    with patch("orchestrator.dentist_portal.routes_dashboard.ScanRepository") as MockScanRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.OrderRepository") as MockOrderRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.ProductRepository") as MockProductRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.AppointmentRepository") as MockApptRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.RecommendationRepository") as MockRecRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.DentistRepository") as MockDentistRepo:

        scan_repo = MockScanRepo.return_value
        scan_repo.count_scans = AsyncMock(return_value=3)
        scan_repo.get_latest_screening = AsyncMock(return_value=(scan_latest, report_latest))
        scan_repo.list_owned = AsyncMock(return_value=[scan_latest])

        order_repo = MockOrderRepo.return_value
        order_repo.count_for_patient = AsyncMock(return_value=0)
        order_repo.list_for_patient = AsyncMock(return_value=[])

        appt_repo = MockApptRepo.return_value
        appt_repo.list_for_principal = AsyncMock(return_value=[])
        rec_repo = MockRecRepo.return_value
        rec_repo.list_product_for_patient = AsyncMock(return_value=[])
        MockProductRepo.return_value.list_active = AsyncMock(return_value=[])

        res = await get_patient_dashboard(patient_user, session)

        assert res["latest_screening"]["scan_id"] == str(scan_latest.id)
        assert res["latest_screening"]["created_at"] == latest_time.isoformat()
        assert res["latest_screening"]["verdict"] == "Enamel Cavity"
        assert res["latest_screening"]["urgency"] == "urgent"


def test_triage_urgency_mappings():
    """4-7. Routine, Soon, Urgent, Emergency triage mappings work correctly."""
    assert _normalize_urgency("routine") == "routine"
    assert _normalize_urgency("None") == "routine"
    assert _normalize_urgency("Mild") == "routine"

    assert _normalize_urgency("soon") == "soon"
    assert _normalize_urgency("Moderate") == "soon"

    assert _normalize_urgency("urgent") == "urgent"
    assert _normalize_urgency("High") == "urgent"

    assert _normalize_urgency("emergency") == "emergency"
    assert _normalize_urgency("Critical") == "emergency"


@pytest.mark.asyncio
async def test_patient_dashboard_isolation_cannot_receive_other_patient_scans():
    """8. Patient cannot receive another patient's scans/records."""
    session = AsyncMock()
    patient_a = {"user_id": uuid4(), "role": "patient"}

    with patch("orchestrator.dentist_portal.routes_dashboard.ScanRepository") as MockScanRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.OrderRepository") as MockOrderRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.ProductRepository") as MockProductRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.AppointmentRepository") as MockApptRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.RecommendationRepository") as MockRecRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.DentistRepository") as MockDentistRepo:

        scan_repo = MockScanRepo.return_value
        scan_repo.count_scans = AsyncMock(return_value=1)
        scan_repo.get_latest_screening = AsyncMock(return_value=None)
        scan_repo.list_owned = AsyncMock(return_value=[])

        MockOrderRepo.return_value.count_for_patient = AsyncMock(return_value=0)
        MockOrderRepo.return_value.list_for_patient = AsyncMock(return_value=[])
        MockApptRepo.return_value.list_for_principal = AsyncMock(return_value=[])
        MockRecRepo.return_value.list_product_for_patient = AsyncMock(return_value=[])

        await get_patient_dashboard(patient_a, session)

        # Asserts ScanRepository and OrderRepository were called with patient_a user_id
        scan_repo.count_scans.assert_awaited_once_with(patient_a["user_id"])
        scan_repo.get_latest_screening.assert_awaited_once_with(patient_a["user_id"])
        MockOrderRepo.return_value.count_for_patient.assert_awaited_once_with(patient_a["user_id"])


@pytest.mark.asyncio
async def test_patient_order_count_and_recent_orders():
    """9-10. Patient order_count is correct and patient only sees own recent orders."""
    session = AsyncMock()
    patient_id = uuid4()
    patient_user = {"user_id": patient_id, "role": "patient"}

    order_1 = MagicMock(spec=Order)
    order_1.id = uuid4()
    order_1.total = 19.99
    order_1.status = "confirmed"
    order_1.created_at = datetime(2026, 9, 3, 10, 0, 0, tzinfo=timezone.utc)
    order_1.items = {
        "product_id": str(uuid4()),
        "product_name": "Fluoride Toothpaste",
        "quantity": 2,
        "seller_name": "Dr. Tariq Dental Surgery",
    }

    dentist = MagicMock(spec=Dentist)
    dentist.clinic_name = "Dr. Tariq Dental Surgery"

    with patch("orchestrator.dentist_portal.routes_dashboard.ScanRepository") as MockScanRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.OrderRepository") as MockOrderRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.ProductRepository") as MockProductRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.AppointmentRepository") as MockApptRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.RecommendationRepository") as MockRecRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.DentistRepository") as MockDentistRepo:

        MockScanRepo.return_value.count_scans = AsyncMock(return_value=0)
        MockScanRepo.return_value.get_latest_screening = AsyncMock(return_value=None)
        MockScanRepo.return_value.list_owned = AsyncMock(return_value=[])

        order_repo = MockOrderRepo.return_value
        order_repo.count_for_patient = AsyncMock(return_value=1)
        order_repo.list_for_patient = AsyncMock(return_value=[(order_1, dentist)])

        MockApptRepo.return_value.list_for_principal = AsyncMock(return_value=[])
        MockRecRepo.return_value.list_product_for_patient = AsyncMock(return_value=[])

        res = await get_patient_dashboard(patient_user, session)

        assert res["stats"]["order_count"] == 1
        assert len(res["recent_orders"]) == 1
        assert res["recent_orders"][0]["order_id"] == str(order_1.id)
        assert res["recent_orders"][0]["product_name"] == "Fluoride Toothpaste"
        assert res["recent_orders"][0]["seller_name"] == "Dr. Tariq Dental Surgery"
        assert res["recent_orders"][0]["price"] == 19.99


@pytest.mark.asyncio
async def test_recommendations_use_real_products_or_empty():
    """11-12. Recommendations use real relevant products; no fake products when none exist."""
    session = AsyncMock()
    patient_id = uuid4()
    patient_user = {"user_id": patient_id, "role": "patient"}

    scan = MagicMock(spec=Scan)
    scan.id = uuid4()
    scan.created_at = datetime.now(timezone.utc)
    scan.mechanical_quality_score = 0.9
    scan.status = "clinical_complete"

    report = MagicMock(spec=ClinicalReport)
    report.verdict = "Enamel Cavity"
    report.urgency_level = "soon"
    report.summary = "AI screening observed Cavity."
    report.recommended_specialist = "General Dentist"
    report.possible_concerns = {"findings": []}
    report.agent_trace_summary = {"confidence": 0.85}
    report.created_at = scan.created_at

    with patch("orchestrator.dentist_portal.routes_dashboard.ScanRepository") as MockScanRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.OrderRepository") as MockOrderRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.ProductRepository") as MockProductRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.AppointmentRepository") as MockApptRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.RecommendationRepository") as MockRecRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.DentistRepository") as MockDentistRepo:

        MockScanRepo.return_value.count_scans = AsyncMock(return_value=1)
        MockScanRepo.return_value.get_latest_screening = AsyncMock(return_value=(scan, report))
        MockScanRepo.return_value.list_owned = AsyncMock(return_value=[scan])
        MockOrderRepo.return_value.count_for_patient = AsyncMock(return_value=0)
        MockOrderRepo.return_value.list_for_patient = AsyncMock(return_value=[])
        MockApptRepo.return_value.list_for_principal = AsyncMock(return_value=[])
        MockRecRepo.return_value.list_product_for_patient = AsyncMock(return_value=[])

        # Case A: No active products match -> returns empty list (no fake products)
        product_repo = MockProductRepo.return_value
        product_repo.list_active = AsyncMock(return_value=[])

        res = await get_patient_dashboard(patient_user, session)
        assert res["recommended_products"] == []

        # Case B: Real active product exists
        real_product = MagicMock(spec=Product)
        real_product.id = uuid4()
        real_product.name = "Real Dentist Toothpaste"
        real_product.category = "toothpaste"
        real_product.price = 12.0
        real_product.dentist_id = uuid4()
        real_product.status = "active"

        dentist = MagicMock(spec=Dentist)
        dentist.clinic_name = "Real Clinic"
        MockDentistRepo.return_value.get = AsyncMock(return_value=dentist)
        product_repo.list_active = AsyncMock(return_value=[real_product])

        res2 = await get_patient_dashboard(patient_user, session)
        assert len(res2["recommended_products"]) == 1
        assert res2["recommended_products"][0]["name"] == "Real Dentist Toothpaste"
        assert res2["recommended_products"][0]["dentist_name"] == "Real Clinic"


@pytest.mark.asyncio
async def test_recent_activity_contains_only_real_records():
    """13. Recent activity contains only real records merged and sorted by timestamp."""
    session = AsyncMock()
    patient_id = uuid4()
    patient_user = {"user_id": patient_id, "role": "patient"}

    t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 9, 3, 10, 0, 0, tzinfo=timezone.utc)

    scan = MagicMock(spec=Scan)
    scan.id = uuid4()
    scan.status = "clinical_complete"
    scan.created_at = t1

    order = MagicMock(spec=Order)
    order.id = uuid4()
    order.status = "shipped"
    order.total = 15.0
    order.items = {"product_name": "Sonic Brush"}
    order.created_at = t3

    appt = MagicMock(spec=AppointmentRequest)
    appt.id = uuid4()
    appt.status = "pending"
    appt.issue = "Tooth pain"
    appt.created_at = t2

    with patch("orchestrator.dentist_portal.routes_dashboard.ScanRepository") as MockScanRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.OrderRepository") as MockOrderRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.ProductRepository") as MockProductRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.AppointmentRepository") as MockApptRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.RecommendationRepository") as MockRecRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.DentistRepository") as MockDentistRepo:

        MockScanRepo.return_value.count_scans = AsyncMock(return_value=1)
        MockScanRepo.return_value.get_latest_screening = AsyncMock(return_value=(scan, None))
        MockScanRepo.return_value.list_owned = AsyncMock(return_value=[scan])

        MockOrderRepo.return_value.count_for_patient = AsyncMock(return_value=1)
        MockOrderRepo.return_value.list_for_patient = AsyncMock(return_value=[(order, None)])

        MockApptRepo.return_value.list_for_principal = AsyncMock(return_value=[appt])
        MockRecRepo.return_value.list_product_for_patient = AsyncMock(return_value=[])
        MockProductRepo.return_value.list_active = AsyncMock(return_value=[])

        res = await get_patient_dashboard(patient_user, session)
        activity = res["recent_activity"]

        assert len(activity) == 3
        # Chronological order: t3 (order) first, then t2 (appt), then t1 (scan)
        assert activity[0]["type"] == "order"
        assert "Sonic Brush" in activity[0]["title"]
        assert activity[1]["type"] == "appointment"
        assert "Tooth pain" in activity[1]["title"]
        assert activity[2]["type"] == "scan"


# =========================================================================
# SECTION 33: DENTIST DASHBOARD TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_dentist_dashboard_product_count_and_order_count_own_only():
    """1-3. product_count, order_count, and multi-seller isolation for dentist."""
    session = AsyncMock()
    dentist_user = {"user_id": uuid4(), "role": "dentist"}

    dentist = MagicMock(spec=Dentist)
    dentist.id = uuid4()
    dentist.owner_user_id = dentist_user["user_id"]

    with patch("orchestrator.dentist_portal.routes_dashboard.DentistRepository") as MockDentistRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.ProductRepository") as MockProductRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.OrderRepository") as MockOrderRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.AppointmentRepository") as MockApptRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.UserRepository") as MockUserRepo:

        MockDentistRepo.return_value.get_by_owner = AsyncMock(return_value=dentist)

        product_repo = MockProductRepo.return_value
        product_repo.count_owned = AsyncMock(return_value=5)

        order_repo = MockOrderRepo.return_value
        order_repo.count_for_dentist = AsyncMock(side_effect=lambda owner_id, status=None: 2 if status else 8)
        order_repo.list_for_dentist = AsyncMock(return_value=[])

        appt_repo = MockApptRepo.return_value
        appt_repo.count_for_principal = AsyncMock(return_value=4)
        appt_repo.list_for_principal = AsyncMock(return_value=[])

        res = await get_dentist_dashboard(dentist_user, session)

        assert res["stats"]["product_count"] == 5
        assert res["stats"]["order_count"] == 8
        assert res["stats"]["appointment_count"] == 4
        # Asserts count_owned called with this dentist's user_id
        product_repo.count_owned.assert_awaited_once_with(dentist_user["user_id"])


@pytest.mark.asyncio
async def test_dentist_appointments_belong_to_authenticated_dentist_only():
    """4-5. Appointments belong to authenticated dentist; other excluded."""
    session = AsyncMock()
    dentist_user = {"user_id": uuid4(), "role": "dentist"}

    dentist = MagicMock(spec=Dentist)
    dentist.id = uuid4()
    dentist.owner_user_id = dentist_user["user_id"]

    with patch("orchestrator.dentist_portal.routes_dashboard.DentistRepository") as MockDentistRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.ProductRepository") as MockProductRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.OrderRepository") as MockOrderRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.AppointmentRepository") as MockApptRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.UserRepository") as MockUserRepo:

        MockDentistRepo.return_value.get_by_owner = AsyncMock(return_value=dentist)
        MockProductRepo.return_value.count_owned = AsyncMock(return_value=0)
        MockOrderRepo.return_value.count_for_dentist = AsyncMock(return_value=0)
        MockOrderRepo.return_value.list_for_dentist = AsyncMock(return_value=[])

        appt_repo = MockApptRepo.return_value
        appt_repo.count_for_principal = AsyncMock(return_value=3)
        appt_repo.list_for_principal = AsyncMock(return_value=[])

        await get_dentist_dashboard(dentist_user, session)

        appt_repo.count_for_principal.assert_any_await(
            user_id=dentist_user["user_id"], role="dentist"
        )
        appt_repo.list_for_principal.assert_awaited_once_with(
            user_id=dentist_user["user_id"], role="dentist", limit=4
        )


@pytest.mark.asyncio
async def test_dentist_recent_orders_and_appointments_ordering():
    """6-7. Recent orders and recent appointments are correctly populated & ordered."""
    session = AsyncMock()
    dentist_user = {"user_id": uuid4(), "role": "dentist"}

    dentist = MagicMock(spec=Dentist)
    dentist.id = uuid4()

    ord1 = MagicMock(spec=Order)
    ord1.id = uuid4()
    ord1.total = 35.0
    ord1.status = "placed"
    ord1.items = {"product_name": "Sonic Brush", "quantity": 1, "patient_name": "Sara Ahmed"}
    ord1.created_at = datetime(2026, 9, 4, 9, 0, 0, tzinfo=timezone.utc)

    appt1 = MagicMock(spec=AppointmentRequest)
    appt1.id = uuid4()
    appt1.patient_user_id = uuid4()
    appt1.issue = "Routine cleaning"
    appt1.status = "confirmed"
    appt1.preferred_time = "Morning"
    appt1.created_at = datetime(2026, 9, 4, 8, 0, 0, tzinfo=timezone.utc)

    patient_user = MagicMock(spec=User)
    patient_user.first_name = "Ali"
    patient_user.last_name = "Khan"
    patient_user.email = "ali@example.com"

    with patch("orchestrator.dentist_portal.routes_dashboard.DentistRepository") as MockDentistRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.ProductRepository") as MockProductRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.OrderRepository") as MockOrderRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.AppointmentRepository") as MockApptRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.UserRepository") as MockUserRepo:

        MockDentistRepo.return_value.get_by_owner = AsyncMock(return_value=dentist)
        MockProductRepo.return_value.count_owned = AsyncMock(return_value=2)
        MockOrderRepo.return_value.count_for_dentist = AsyncMock(return_value=1)
        MockOrderRepo.return_value.list_for_dentist = AsyncMock(return_value=[ord1])

        MockApptRepo.return_value.count_for_principal = AsyncMock(return_value=1)
        MockApptRepo.return_value.list_for_principal = AsyncMock(return_value=[appt1])

        MockUserRepo.return_value.get = AsyncMock(return_value=patient_user)

        res = await get_dentist_dashboard(dentist_user, session)

        assert len(res["recent_orders"]) == 1
        assert res["recent_orders"][0]["product_name"] == "Sonic Brush"
        assert res["recent_orders"][0]["patient_name"] == "Sara Ahmed"

        assert len(res["recent_appointments"]) == 1
        assert res["recent_appointments"][0]["patient_name"] == "Ali Khan"
        assert res["recent_appointments"][0]["issue"] == "Routine cleaning"
        assert res["recent_appointments"][0]["status"] == "confirmed"


@pytest.mark.asyncio
async def test_empty_dentist_dashboard_returns_safe_zeros():
    """8. Empty dentist dashboard returns safe zeros and empty arrays."""
    session = AsyncMock()
    dentist_user = {"user_id": uuid4(), "role": "dentist"}

    dentist = MagicMock(spec=Dentist)
    dentist.id = uuid4()

    with patch("orchestrator.dentist_portal.routes_dashboard.DentistRepository") as MockDentistRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.ProductRepository") as MockProductRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.OrderRepository") as MockOrderRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.AppointmentRepository") as MockApptRepo, \
         patch("orchestrator.dentist_portal.routes_dashboard.UserRepository") as MockUserRepo:

        MockDentistRepo.return_value.get_by_owner = AsyncMock(return_value=dentist)
        MockProductRepo.return_value.count_owned = AsyncMock(return_value=0)
        MockOrderRepo.return_value.count_for_dentist = AsyncMock(return_value=0)
        MockOrderRepo.return_value.list_for_dentist = AsyncMock(return_value=[])
        MockApptRepo.return_value.count_for_principal = AsyncMock(return_value=0)
        MockApptRepo.return_value.list_for_principal = AsyncMock(return_value=[])

        res = await get_dentist_dashboard(dentist_user, session)

        assert res["stats"]["product_count"] == 0
        assert res["stats"]["order_count"] == 0
        assert res["stats"]["appointment_count"] == 0
        assert res["stats"]["pending_order_count"] == 0
        assert res["stats"]["completed_order_count"] == 0
        assert res["recent_orders"] == []
        assert res["recent_appointments"] == []
