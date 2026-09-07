"""Query-aware retrieval tests for Central Dentist (Phase 12A Final).

Verifies that the LangGraph retrieval planner only fetches data relevant
to the detected intent, keeping database queries and LLM context minimal.
"""

from orchestrator.central_dentist.graph import nlp_understanding, plan_retrieval
from orchestrator.central_dentist.nlp import CentralDentistIntent


def test_scan_latest_query_plan():
    state = {
        "message": "what did my last scan show?",
        "user_id": "test-user-id",
    }
    nlp_out = nlp_understanding(state)
    state.update(nlp_out)
    plan_out = plan_retrieval(state)
    plan = plan_out["retrieval_plan"]

    assert plan["need_latest_scan"] is True
    assert plan["need_appointments"] is False
    assert plan["need_scan_history"] is False
    assert plan["need_dentist_info"] is False


def test_appointment_status_query_plan():
    state = {
        "message": "when is my next appointment?",
        "user_id": "test-user-id",
    }
    nlp_out = nlp_understanding(state)
    state.update(nlp_out)
    plan_out = plan_retrieval(state)
    plan = plan_out["retrieval_plan"]

    assert plan["need_appointments"] is True
    assert plan["need_latest_scan"] is False
    assert plan["need_scan_history"] is False


def test_scan_compare_query_plan():
    state = {
        "message": "compare my last two scans",
        "user_id": "test-user-id",
    }
    nlp_out = nlp_understanding(state)
    state.update(nlp_out)
    plan_out = plan_retrieval(state)
    plan = plan_out["retrieval_plan"]

    assert plan["need_scan_compare"] is True
    assert plan["need_appointments"] is False


def test_dentist_information_query_plan():
    state = {
        "message": "who is my dentist?",
        "user_id": "test-user-id",
    }
    nlp_out = nlp_understanding(state)
    state.update(nlp_out)
    plan_out = plan_retrieval(state)
    plan = plan_out["retrieval_plan"]

    assert plan["need_dentist_info"] is True
    assert plan["need_appointments"] is True
    assert plan["need_scan_history"] is False


def test_general_oral_health_query_plan():
    state = {
        "message": "how should I brush properly?",
        "user_id": "test-user-id",
    }
    nlp_out = nlp_understanding(state)
    state.update(nlp_out)
    plan_out = plan_retrieval(state)
    plan = plan_out["retrieval_plan"]

    assert plan["need_knowledge"] is True
    assert plan["need_latest_scan"] is False
    assert plan["need_appointments"] is False
