"""Phase 3B-lite - deterministic evidence-aware screening triage tests.

ZERO external AI calls: the triage engine is a pure rule table, and the Diagnosis
endpoint is exercised in-process with FastAPI's ``TestClient`` (no network, no
Qwen/Gemini, no image bytes).
"""

from __future__ import annotations

import inspect
import logging
import uuid

from fastapi.testclient import TestClient

from dantshaant_common.schemas import (
    ActionTrigger,
    ConditionLabel,
    DiagnoseRequest,
    DiagnoseResponse,
    Severity,
    TriageResult,
    UrgencyLevel,
    VisualFinding,
)

from diagnosis import classifier as classifier_module
from diagnosis import triage as triage_module
from diagnosis.classifier import CONDITION_THRESHOLDS, diagnose
from diagnosis.main import app
from diagnosis.triage import (
    BASE_LIMITATION,
    INCONCLUSIVE_VERDICT,
    LIMITED_VISIBILITY_LIMITATION,
    LOW_CONFIDENCE_LIMITATION,
    LOW_QUALITY_LIMITATION,
    RULES,
    URGENCY_ORDER,
    VISIT_TIMEFRAME,
    canonical_code,
    triage,
    triage_findings,
)

# Wording that would present screening output as a confirmed diagnosis.
FORBIDDEN_DEFINITIVE = (
    "you have",
    "confirmed diagnosis",
    "definitive diagnosis",
    "definitive",
    "guaranteed",
    "diagnosed with",
    "you are suffering",
)

# Tokens that would mean an AI/network call was introduced in this phase.
FORBIDDEN_CALLER_TOKENS = (
    "httpx",
    "aiohttp",
    "requests.",
    "openai",
    "qwen",
    "gemini",
    "dashscope",
    "openrouter",
    "generate_text",
    "generate_structured",
    "generate_vision",
)


def _finding(code: str, confidence: float = 0.8, visibility: str | None = None):
    return VisualFinding(label=code, confidence=confidence, visibility=visibility)


def _result(*codes: str, confidence: float = 0.8, visibility: str | None = None):
    return triage_findings(
        [_finding(code, confidence, visibility) for code in codes],
        overall_quality_score=0.9,
    )


def _text(result: TriageResult) -> str:
    """All patient-facing triage text, lowercased, for wording assertions."""
    return " | ".join(
        [result.verdict, result.condition_summary, result.visit_timeframe]
        + result.possible_concerns
        + result.recommended_actions
        + result.limitations
        + [result.recommended_specialist or "", result.disclaimer]
    ).lower()


# ---------------------------------------------------------------------------
# 1-5, 7-9. Per-finding urgency rules
# ---------------------------------------------------------------------------
def test_1_healthy_tissue_is_routine():
    result = _result("healthy_tissue", confidence=0.92)
    assert result.urgency_level == UrgencyLevel.ROUTINE
    assert result.possible_concerns == ["No obvious concerning visual finding"]
    assert any("oral hygiene" in a.lower() for a in result.recommended_actions)
    assert any("routine dental checkup" in a.lower() for a in result.recommended_actions)
    assert result.recommended_specialist == "general dentist"
    assert result.visit_timeframe == VISIT_TIMEFRAME[UrgencyLevel.ROUTINE]
    assert "no obvious concerning visual finding" in result.verdict.lower()


def test_2_plaque_detected_is_routine_or_soon():
    result = _result("plaque_detected")
    assert result.urgency_level in (UrgencyLevel.ROUTINE, UrgencyLevel.SOON)
    assert any("plaque" in c.lower() for c in result.possible_concerns)
    assert any("hygiene" in a.lower() for a in result.recommended_actions)
    assert result.recommended_specialist == "general dentist"


def test_3_tartar_is_soon():
    result = _result("tartar")
    assert result.urgency_level == UrgencyLevel.SOON
    assert any("tartar" in c.lower() or "calculus" in c.lower() for c in result.possible_concerns)
    assert any("cleaning" in a.lower() for a in result.recommended_actions)
    assert result.recommended_specialist == "general dentist"


def test_4_cavity_suspect_is_soon():
    result = _result("cavity_suspect")
    assert result.urgency_level == UrgencyLevel.SOON
    assert any("possibly consistent with" in c.lower() for c in result.possible_concerns)
    assert any("licensed dental examination" in a.lower() for a in result.recommended_actions)
    assert result.recommended_specialist == "general dentist"


def test_5_cavity_advanced_is_urgent():
    result = _result("cavity_advanced", confidence=0.9)
    assert result.urgency_level == UrgencyLevel.URGENT
    assert result.visit_timeframe == VISIT_TIMEFRAME[UrgencyLevel.URGENT]
    assert any("prompt" in a.lower() for a in result.recommended_actions)
    assert "restorative dentist" in (result.recommended_specialist or "")
    # Finding-code compatibility is preserved for downstream consumers.
    assert "cavity_advanced" in result.supporting_findings


def test_7_gingivitis_signs_is_soon():
    result = _result("gingivitis_signs")
    assert result.urgency_level == UrgencyLevel.SOON
    assert any("gum inflammation" in c.lower() for c in result.possible_concerns)
    assert result.recommended_specialist == "general dentist"


def test_8_gum_disease_severe_is_urgent_and_routes_to_periodontist():
    result = _result("gum_disease_severe", confidence=0.85)
    assert result.urgency_level == UrgencyLevel.URGENT
    assert result.recommended_specialist == "periodontist"
    assert any("periodontal" in c.lower() for c in result.possible_concerns)
    assert any("periodontal evaluation" in a.lower() for a in result.recommended_actions)


def test_9_discoloration_safe_routing():
    result = _result("discoloration")
    assert result.urgency_level in (UrgencyLevel.ROUTINE, UrgencyLevel.SOON)
    assert result.recommended_specialist == "general dentist"
    assert any("discoloration" in c.lower() for c in result.possible_concerns)
    # Only conditional follow-up, never a treatment prescription.
    assert any("if it persists" in a.lower() or "if persistent" in a.lower() for a in result.recommended_actions)


# ---------------------------------------------------------------------------
# 6, 20. Safety wording
# ---------------------------------------------------------------------------
def test_6_cavity_advanced_is_not_phrased_as_a_confirmed_diagnosis():
    result = _result("cavity_advanced", confidence=0.95)
    summary = result.condition_summary.lower()
    assert summary.startswith("possible")
    assert "advanced cavity" not in summary
    assert summary == "possible significant tooth decay / structural damage"
    assert "may be present" in " ".join(result.possible_concerns).lower()
    assert "licensed dentist" in result.disclaimer.lower()
    assert not any(phrase in _text(result) for phrase in FORBIDDEN_DEFINITIVE)


def test_20_no_definitive_wording_in_any_rule_output():
    for code in RULES:
        result = _result(code)
        text = _text(result)
        assert not any(phrase in text for phrase in FORBIDDEN_DEFINITIVE), code
        assert "licensed dentist" in result.disclaimer.lower()
        assert BASE_LIMITATION in result.limitations
    # Every rule table entry is itself worded as a possible/screening concern.
    for rule in RULES.values():
        assert "possible" in rule.condition_summary.lower() or "no obvious" in (
            rule.condition_summary.lower()
        )


# ---------------------------------------------------------------------------
# 10-11. missing_or_damaged_teeth safety fix
# ---------------------------------------------------------------------------
def test_10_missing_or_damaged_teeth_does_not_become_advanced_cavity():
    result = _result("missing_or_damaged_teeth", confidence=0.9)
    decision = triage([_finding("missing_or_damaged_teeth", 0.9)], overall_quality_score=0.9)
    assert decision.condition_label != ConditionLabel.ADVANCED_CAVITY
    assert decision.condition_label == ConditionLabel.MISSING_OR_DAMAGED_TOOTH
    combined = _text(result).lower()
    assert "cavity" not in combined
    assert "advanced cavity" not in result.condition_summary.lower()
    # The legacy unsafe alias is corrected too.
    assert canonical_code("broken_teeth") == "missing_or_damaged_teeth"
    alias_decision = triage([_finding("broken_teeth", 0.9)], overall_quality_score=0.9)
    assert alias_decision.condition_label == ConditionLabel.MISSING_OR_DAMAGED_TOOTH


def test_11_missing_or_damaged_teeth_routes_to_structural_concern():
    result = _result("missing_or_damaged_teeth", confidence=0.9)
    assert result.urgency_level == UrgencyLevel.SOON
    assert any(
        "missing tooth" in c.lower() or "structural tooth damage" in c.lower()
        for c in result.possible_concerns
    )
    assert any("restorative dental evaluation" in a.lower() for a in result.recommended_actions)
    specialist = (result.recommended_specialist or "").lower()
    assert "general dentist" in specialist
    assert "restorative dentist" in specialist


# ---------------------------------------------------------------------------
# 12-13. Multiple findings
# ---------------------------------------------------------------------------
def test_12_multiple_findings_use_highest_urgency():
    result = _result("tartar", "cavity_advanced", confidence=0.8)
    assert result.urgency_level == UrgencyLevel.URGENT  # not "soon"
    assert result.visit_timeframe == VISIT_TIMEFRAME[UrgencyLevel.URGENT]
    # Both concerns survive, most urgent first.
    assert len(result.possible_concerns) == 2
    assert "decay" in result.possible_concerns[0].lower()
    assert result.supporting_findings == ["cavity_advanced", "tartar"]
    # Urgency ordering is total and matches routine < soon < urgent < emergency.
    assert (
        URGENCY_ORDER[UrgencyLevel.ROUTINE]
        < URGENCY_ORDER[UrgencyLevel.SOON]
        < URGENCY_ORDER[UrgencyLevel.URGENT]
        < URGENCY_ORDER[UrgencyLevel.EMERGENCY]
    )


def test_13_duplicate_concerns_actions_and_findings_removed():
    result = _result("tartar", "tartar", "cavity", "cavity_suspect")
    assert result.possible_concerns == list(dict.fromkeys(result.possible_concerns))
    assert result.recommended_actions == list(dict.fromkeys(result.recommended_actions))
    assert result.limitations == list(dict.fromkeys(result.limitations))
    assert result.supporting_findings == ["tartar", "cavity_suspect"]
    assert result.rule_ids == ["TRIAGE-TARTAR-001", "TRIAGE-CAVITY-SUSPECT-001"]


def test_24_healthy_finding_does_not_cancel_a_concurrent_concern():
    result = _result("healthy_tissue", "gingivitis_signs", confidence=0.8)
    assert result.urgency_level == UrgencyLevel.SOON
    assert result.possible_concerns == ["Visible gum inflammation signs"]
    assert "healthy_tissue" not in result.supporting_findings


# ---------------------------------------------------------------------------
# 14-15. Confidence / visibility stay conservative
# ---------------------------------------------------------------------------
def test_14_limited_visibility_adds_limitation():
    clear = _result("cavity_suspect", confidence=0.8, visibility="clear")
    limited = _result("cavity_suspect", confidence=0.8, visibility="limited")
    assert LIMITED_VISIBILITY_LIMITATION in limited.limitations
    assert LIMITED_VISIBILITY_LIMITATION not in clear.limitations
    # Visibility never changes the urgency or the concern wording.
    assert limited.urgency_level == clear.urgency_level == UrgencyLevel.SOON
    assert limited.possible_concerns == clear.possible_concerns
    # A low mechanical quality score states its own limitation.
    low_quality = triage_findings([_finding("tartar", 0.8)], overall_quality_score=0.55)
    assert LOW_QUALITY_LIMITATION in low_quality.limitations


def test_15_low_confidence_never_increases_diagnostic_certainty():
    confident = _result("cavity_advanced", confidence=0.9)
    uncertain = _result("cavity_advanced", confidence=0.3)
    assert uncertain.urgency_level == confident.urgency_level == UrgencyLevel.URGENT
    assert uncertain.confidence == 0.3  # never inflated by aggregation
    assert uncertain.condition_summary == confident.condition_summary
    assert LOW_CONFIDENCE_LIMITATION in uncertain.limitations
    assert LOW_CONFIDENCE_LIMITATION not in confident.limitations
    # The driving finding's confidence is reported, not a boosted aggregate.
    mixed = triage_findings(
        [_finding("tartar", 0.95), _finding("cavity_advanced", 0.6)],
        overall_quality_score=0.9,
    )
    assert mixed.confidence == 0.6


# ---------------------------------------------------------------------------
# 16-17. Specialist routing and visit timeframe
# ---------------------------------------------------------------------------
def test_16_specialist_routing():
    expected = {
        "healthy_tissue": "general dentist",
        "plaque_detected": "general dentist",
        "tartar": "general dentist",
        "cavity_suspect": "general dentist",
        "discoloration": "general dentist",
        "gingivitis_signs": "general dentist",
        "gum_disease_severe": "periodontist",
    }
    for code, specialist in expected.items():
        assert _result(code).recommended_specialist == specialist, code
    assert "restorative dentist" in (_result("cavity_advanced").recommended_specialist or "")
    # Highest-urgency specialists merge deterministically.
    merged = _result("gum_disease_severe", "cavity_advanced", confidence=0.8)
    assert merged.urgency_level == UrgencyLevel.URGENT
    specialist = merged.recommended_specialist or ""
    assert "periodontist" in specialist
    assert "restorative dentist" in specialist


def test_17_visit_timeframe_mapping():
    assert VISIT_TIMEFRAME[UrgencyLevel.ROUTINE] == "Routine dental checkup"
    assert VISIT_TIMEFRAME[UrgencyLevel.SOON] == "Arrange a dental evaluation soon"
    assert VISIT_TIMEFRAME[UrgencyLevel.URGENT] == (
        "Seek a licensed dental evaluation promptly, ideally within about 1 week"
    )
    assert VISIT_TIMEFRAME[UrgencyLevel.EMERGENCY] == (
        "Seek urgent/emergency professional care now"
    )
    assert _result("tartar").visit_timeframe == VISIT_TIMEFRAME[UrgencyLevel.SOON]
    assert _result("cavity_advanced").visit_timeframe == VISIT_TIMEFRAME[UrgencyLevel.URGENT]


def test_25_emergency_is_supported_but_not_invented():
    # The current VisualFinding contract carries no swelling / airway / bleeding /
    # trauma signal, so no rule may claim one.
    assert all(rule.urgency != UrgencyLevel.EMERGENCY for rule in RULES.values())
    assert UrgencyLevel.EMERGENCY in URGENCY_ORDER
    assert UrgencyLevel.EMERGENCY in VISIT_TIMEFRAME


# ---------------------------------------------------------------------------
# 18. Diagnosis API compatibility
# ---------------------------------------------------------------------------
def test_18_diagnosis_endpoint_contract_stays_compatible():
    client = TestClient(app)
    payload = {
        "user_id": str(uuid.uuid4()),
        "analysis_id": str(uuid.uuid4()),
        "findings": [
            {"label": "cavity_advanced", "confidence": 0.9, "region": "upper_left"},
            {"label": "tartar", "confidence": 0.7},
        ],
        "overall_quality_score": 0.9,
    }
    response = client.post("/v1/diagnose", json=payload)
    assert response.status_code == 200
    body = response.json()

    legacy_keys = (
        "diagnosis_id",
        "user_id",
        "analysis_id",
        "condition_label",
        "severity",
        "confidence",
        "confidence_threshold",
        "meets_threshold",
        "action_trigger",
        "disclaimer",
        "diagnosed_at",
    )
    for key in legacy_keys:
        assert key in body, key

    # Legacy enum values are unchanged for existing consumers.
    assert body["condition_label"] == "Advanced Cavity"
    assert body["severity"] == "High"
    assert body["action_trigger"] == "dentist_urgent_1_week"
    assert body["meets_threshold"] is True
    assert body["confidence_threshold"] == CONDITION_THRESHOLDS[ConditionLabel.ADVANCED_CAVITY]

    # Additive screening block.
    assert body["triage"]["urgency_level"] == "urgent"
    assert body["triage"]["condition_summary"] == (
        "Possible significant tooth decay / structural damage"
    )
    assert body["triage"]["recommended_specialist"]

    # A legacy client that never sees `triage` still validates.
    assert DiagnoseResponse.model_validate({k: v for k, v in body.items() if k != "triage"}).triage is None

    assert client.get("/health").status_code == 200


def test_23_low_quality_score_legacy_path_is_preserved():
    request = DiagnoseRequest(
        user_id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        findings=[_finding("cavity_advanced", 0.9)],
        overall_quality_score=0.3,
    )
    response = diagnose(request)
    assert response.condition_label == ConditionLabel.UNKNOWN
    assert response.severity == Severity.MILD
    assert response.action_trigger == ActionTrigger.REQUEST_CLEARER_PHOTO
    assert response.meets_threshold is False
    assert response.confidence == 0.3
    assert response.triage is not None
    assert response.triage.verdict == INCONCLUSIVE_VERDICT
    assert response.triage.rule_ids == ["TRIAGE-UNKNOWN-001"]
    assert LOW_QUALITY_LIMITATION in response.triage.limitations


def test_28_below_threshold_confidence_keeps_the_possible_concern():
    request = DiagnoseRequest(
        user_id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        findings=[_finding("cavity_advanced", 0.55)],
        overall_quality_score=0.9,
    )
    response = diagnose(request)
    assert response.meets_threshold is False
    # Safer than the legacy collapse to "Unknown": the concern is still surfaced.
    assert response.condition_label == ConditionLabel.ADVANCED_CAVITY
    assert response.triage.urgency_level == UrgencyLevel.URGENT
    assert any("internal review threshold" in item for item in response.triage.limitations)


def test_22_unrecognised_finding_is_inconclusive_not_guessed():
    result = _result("something_unmapped", confidence=0.9)
    assert result.verdict == INCONCLUSIVE_VERDICT
    assert result.urgency_level == UrgencyLevel.ROUTINE
    assert result.rule_ids == ["TRIAGE-UNKNOWN-001"]
    assert result.supporting_findings == []
    assert result.confidence is None
    decision = triage([_finding("something_unmapped", 0.9)], overall_quality_score=0.9)
    assert decision.condition_label == ConditionLabel.UNKNOWN
    assert decision.action_trigger == ActionTrigger.REQUEST_CLEARER_PHOTO


# ---------------------------------------------------------------------------
# 19, 21, 26. No AI call, determinism, safe observability
# ---------------------------------------------------------------------------
def test_19_no_provider_or_network_call_is_introduced():
    for module in (triage_module, classifier_module):
        source = inspect.getsource(module).lower()
        for token in FORBIDDEN_CALLER_TOKENS:
            assert token not in source, (module.__name__, token)
    # The engine is synchronous and pure - nothing to await, nothing to call.
    assert not inspect.iscoroutinefunction(triage)
    assert not inspect.iscoroutinefunction(triage_findings)
    assert not inspect.iscoroutinefunction(diagnose)


def test_21_output_is_deterministic():
    findings = [
        _finding("tartar", 0.7, visibility="partial"),
        _finding("cavity_suspect", 0.5),
        _finding("gingivitis_signs", 0.6),
    ]
    first = triage_findings(findings, overall_quality_score=0.8).model_dump()
    second = triage_findings(findings, overall_quality_score=0.8).model_dump()
    assert first == second
    assert first["urgency_level"] == UrgencyLevel.SOON


def test_26_triage_log_is_safe(caplog):
    secret_looking = "L0FAKEBASE64IMAGEBYTES/"
    findings = [_finding("cavity_advanced", 0.9)]
    findings[0].region = secret_looking
    with caplog.at_level(logging.INFO, logger="diagnosis.triage"):
        triage(findings, overall_quality_score=0.9)
    triage_logs = [r.getMessage() for r in caplog.records if "[TRIAGE]" in r.getMessage()]
    assert len(triage_logs) == 1
    line = triage_logs[0]
    assert "rule_ids=TRIAGE-CAVITY-ADVANCED-001" in line
    assert "highest_urgency=urgent" in line
    assert "finding_count=1" in line
    assert secret_looking not in line
