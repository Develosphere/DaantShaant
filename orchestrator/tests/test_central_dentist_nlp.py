"""Unit tests for Central Dentist lightweight deterministic NLP (Phase 12A Final)."""

import pytest

from orchestrator.central_dentist.nlp import (
    CentralDentistIntent,
    analyze_message,
    classify_intent,
    detect_fast_path,
    extract_confidence_number,
    extract_finding_reference,
    normalize_text,
)


def test_text_normalization():
    assert normalize_text("  Hello  World!  ") == "hello world!"
    assert normalize_text("What's 76% confidence?") == "what s 76% confidence?"


def test_confidence_number_extraction():
    assert extract_confidence_number("what does 76% mean?") == 0.76
    assert extract_confidence_number("why is confidence 76 percent?") == 0.76
    assert extract_confidence_number("confidence was 0.85") == 0.85
    assert extract_confidence_number("no confidence number here") is None


def test_finding_reference_extraction():
    assert extract_finding_reference("why does it say discoloration?") == "discoloration"
    assert extract_finding_reference("my teeth look yellow") == "discoloration"
    assert extract_finding_reference("is there tartar buildup?") == "tartar"
    assert extract_finding_reference("do I have a cavity?") == "cavity_suspect"
    assert extract_finding_reference("my gums are bleeding") == "gingivitis_signs"
    assert extract_finding_reference("there is an ulcer on my tongue") == "oral_ulcer"


def test_intent_scan_latest():
    res = analyze_message("what did my last scan show?")
    assert res.intent == CentralDentistIntent.SCAN_LATEST

    res2 = analyze_message("What did my latest scan say?")
    assert res2.intent == CentralDentistIntent.SCAN_LATEST


def test_intent_scan_compare():
    res = analyze_message("compare my last two scans")
    assert res.intent == CentralDentistIntent.SCAN_COMPARE

    res2 = analyze_message("is it better than my previous scan?")
    assert res2.intent == CentralDentistIntent.SCAN_COMPARE


def test_intent_explain_finding():
    res = analyze_message("why does it say discoloration?")
    assert res.intent == CentralDentistIntent.EXPLAIN_FINDING
    assert res.finding_reference == "discoloration"

    res2 = analyze_message("what does tartar mean?")
    assert res2.intent == CentralDentistIntent.EXPLAIN_FINDING
    assert res2.finding_reference == "tartar"


def test_intent_explain_confidence():
    res = analyze_message("what does 76 percent mean?")
    assert res.intent == CentralDentistIntent.EXPLAIN_CONFIDENCE
    assert res.confidence_query == 0.76

    res2 = analyze_message("what does 76% mean?")
    assert res2.intent == CentralDentistIntent.EXPLAIN_CONFIDENCE
    assert res2.confidence_query == 0.76


def test_intent_appointment_status():
    res = analyze_message("when is my appointment?")
    assert res.intent == CentralDentistIntent.APPOINTMENT_STATUS

    res2 = analyze_message("do I have an upcoming appointment?")
    assert res2.intent == CentralDentistIntent.APPOINTMENT_STATUS


def test_intent_dentist_information():
    res = analyze_message("who is my dentist?")
    assert res.intent == CentralDentistIntent.DENTIST_INFORMATION

    res2 = analyze_message("which dentist am I seeing?")
    assert res2.intent == CentralDentistIntent.DENTIST_INFORMATION


def test_intent_follow_up_reference_with_active_context():
    # Without active context, might be unknown
    res_no_ctx = analyze_message("is that serious?")
    assert res_no_ctx.intent != CentralDentistIntent.FOLLOW_UP_REFERENCE

    # With active context, resolves to FOLLOW_UP_REFERENCE
    res_with_ctx = analyze_message("is that serious?", active_finding="discoloration")
    assert res_with_ctx.intent == CentralDentistIntent.FOLLOW_UP_REFERENCE
    assert res_with_ctx.finding_reference == "discoloration"


def test_intent_general_oral_health():
    res = analyze_message("how should I brush?")
    assert res.intent == CentralDentistIntent.GENERAL_ORAL_HEALTH

    res2 = analyze_message("what is the best way to floss?")
    assert res2.intent == CentralDentistIntent.GENERAL_ORAL_HEALTH


def test_intent_symptom_question():
    res = analyze_message("my tooth hurts when I drink cold water")
    assert res.intent == CentralDentistIntent.SYMPTOM_QUESTION

    res2 = analyze_message("my gums bleed when brushing")
    assert res2.intent == CentralDentistIntent.SYMPTOM_QUESTION


def test_fast_path_detection():
    # Scan date fast path
    res = analyze_message("when was my latest scan?")
    assert res.is_fast_path_candidate is True
    assert res.fast_path_type == "scan_date"

    # Appointment date fast path
    res2 = analyze_message("when is my appointment?")
    assert res2.is_fast_path_candidate is True
    assert res2.fast_path_type == "appointment_date"

    # Confidence fast path
    res3 = analyze_message("what was the confidence?")
    assert res3.is_fast_path_candidate is True
    assert res3.fast_path_type == "confidence"

    # Urgency fast path
    res4 = analyze_message("what is my urgency?")
    assert res4.is_fast_path_candidate is True
    assert res4.fast_path_type == "urgency"

    # Greeting fast path
    res5 = analyze_message("hello")
    assert res5.is_fast_path_candidate is True
    assert res5.fast_path_type == "greeting"
