"""Clinical mapping from visual findings → condition schema (Technical Doc Table 8).

Phase 3B-lite: the finding → concern/severity/action mapping now lives in ONE
place - ``diagnosis.triage``, a deterministic rule engine that produces safer
AI-screening wording instead of hard-coded disease assumptions. This module keeps
the legacy ``DiagnoseResponse`` contract (condition label, severity, Table 8
confidence threshold, action trigger) and adapts the triage decision into it,
attaching the screening ``TriageResult`` as an additive field.

No LLM/provider call happens here or in ``diagnosis.triage``.
"""

from uuid import uuid4

from dantshaant_common.schemas import (
    ActionTrigger,
    ConditionLabel,
    DiagnoseRequest,
    DiagnoseResponse,
    Severity,
)
from diagnosis.triage import triage, triage_findings

# Table 8 — confidence thresholds per condition (internal review thresholds).
CONDITION_THRESHOLDS: dict[ConditionLabel, float] = {
    ConditionLabel.HEALTHY: 0.85,
    ConditionLabel.PLAQUE_TARTAR: 0.80,
    ConditionLabel.EARLY_CAVITY: 0.78,
    ConditionLabel.ADVANCED_CAVITY: 0.75,
    ConditionLabel.GINGIVITIS: 0.78,
    ConditionLabel.SEVERE_GUM_DISEASE: 0.72,
    ConditionLabel.DISCOLORATION: 0.82,
    ConditionLabel.MISSING_OR_DAMAGED_TOOTH: 0.75,
    ConditionLabel.UNKNOWN: 0.0,
}

# Mechanical quality floor: below this an image cannot support screening at all.
MIN_QUALITY_SCORE = 0.5

BELOW_THRESHOLD_LIMITATION = (
    "Model confidence for the driving visual finding was below the internal review "
    "threshold; a clearer, well-lit photo may improve this screening."
)


def diagnose(request: DiagnoseRequest) -> DiagnoseResponse:
    """Contract: specs/diagnosis.openapi.yaml"""
    if request.overall_quality_score < MIN_QUALITY_SCORE:
        # Preserved legacy behaviour. Findings from an image that cannot support
        # screening are reported as inconclusive rather than acted upon.
        return DiagnoseResponse(
            diagnosis_id=uuid4(),
            user_id=request.user_id,
            analysis_id=request.analysis_id,
            condition_label=ConditionLabel.UNKNOWN,
            severity=Severity.MILD,
            confidence=request.overall_quality_score,
            confidence_threshold=0.0,
            meets_threshold=False,
            action_trigger=ActionTrigger.REQUEST_CLEARER_PHOTO,
            triage=triage_findings(
                [], overall_quality_score=request.overall_quality_score
            ),
        )

    decision = triage(
        request.findings,
        overall_quality_score=request.overall_quality_score,
    )
    result = decision.result
    condition = decision.condition_label
    confidence = decision.driving_confidence
    threshold = CONDITION_THRESHOLDS.get(condition, 0.75)
    meets = confidence >= threshold

    if not meets:
        # The possible concern is still reported (safer than silently collapsing
        # it to "Unknown"); the confidence flag and this limitation carry the
        # uncertainty instead.
        result = result.model_copy(
            update={"limitations": [*result.limitations, BELOW_THRESHOLD_LIMITATION]}
        )

    return DiagnoseResponse(
        diagnosis_id=uuid4(),
        user_id=request.user_id,
        analysis_id=request.analysis_id,
        condition_label=condition,
        severity=decision.severity,
        confidence=confidence,
        confidence_threshold=threshold,
        meets_threshold=meets,
        action_trigger=decision.action_trigger,
        triage=result,
    )
