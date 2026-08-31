"""
Clinical mapping from visual findings → condition schema (Technical Doc Table 8).

Phase 1: rule-based mapper (testable, spec-aligned).
Phase 2+: optional small classifier or LLM assist — same DiagnoseResponse contract.
"""

from uuid import uuid4

from dantshaant_common.schemas import (
    ActionTrigger,
    ConditionLabel,
    DiagnoseRequest,
    DiagnoseResponse,
    Severity,
    VisualFinding,
)

# Table 8 — confidence thresholds per condition
CONDITION_THRESHOLDS: dict[ConditionLabel, float] = {
    ConditionLabel.HEALTHY: 0.85,
    ConditionLabel.PLAQUE_TARTAR: 0.80,
    ConditionLabel.EARLY_CAVITY: 0.78,
    ConditionLabel.ADVANCED_CAVITY: 0.75,
    ConditionLabel.GINGIVITIS: 0.78,
    ConditionLabel.SEVERE_GUM_DISEASE: 0.72,
    ConditionLabel.DISCOLORATION: 0.82,
    ConditionLabel.UNKNOWN: 0.0,
}

# Raw vision label → clinical condition candidate
LABEL_MAP: dict[str, ConditionLabel] = {
    "healthy_tissue": ConditionLabel.HEALTHY,
    "healthy": ConditionLabel.HEALTHY,
    "plaque_detected": ConditionLabel.PLAQUE_TARTAR,
    "plaque": ConditionLabel.PLAQUE_TARTAR,
    "tartar": ConditionLabel.PLAQUE_TARTAR,
    "cavity_suspect": ConditionLabel.EARLY_CAVITY,
    "cavity": ConditionLabel.EARLY_CAVITY,
    "decay": ConditionLabel.EARLY_CAVITY,
    "early_cavity": ConditionLabel.EARLY_CAVITY,
    "cavity_advanced": ConditionLabel.ADVANCED_CAVITY,
    "advanced_cavity": ConditionLabel.ADVANCED_CAVITY,
    "severe_decay": ConditionLabel.ADVANCED_CAVITY,
    "gingivitis_signs": ConditionLabel.GINGIVITIS,
    "gingivitis": ConditionLabel.GINGIVITIS,
    "gum_disease_severe": ConditionLabel.SEVERE_GUM_DISEASE,
    "gum_disease": ConditionLabel.SEVERE_GUM_DISEASE,
    "discoloration": ConditionLabel.DISCOLORATION,
    "staining": ConditionLabel.DISCOLORATION,
    "yellow_teeth": ConditionLabel.DISCOLORATION,
    "missing_or_damaged_teeth": ConditionLabel.ADVANCED_CAVITY,
    "broken_teeth": ConditionLabel.ADVANCED_CAVITY,
}

HEALTHY_LABELS = frozenset({"healthy_tissue", "healthy"})

CONDITION_META: dict[ConditionLabel, tuple[Severity, ActionTrigger]] = {
    ConditionLabel.HEALTHY: (Severity.NONE, ActionTrigger.MAINTENANCE_REMINDER),
    ConditionLabel.PLAQUE_TARTAR: (
        Severity.MILD,
        ActionTrigger.PRODUCT_SUGGEST_BRUSHING,
    ),
    ConditionLabel.EARLY_CAVITY: (
        Severity.MODERATE,
        ActionTrigger.PRODUCT_DENTIST_2_WEEKS,
    ),
    ConditionLabel.ADVANCED_CAVITY: (
        Severity.HIGH,
        ActionTrigger.DENTIST_URGENT_1_WEEK,
    ),
    ConditionLabel.GINGIVITIS: (
        Severity.MODERATE,
        ActionTrigger.ANTIBACTERIAL_DENTIST,
    ),
    ConditionLabel.SEVERE_GUM_DISEASE: (
        Severity.CRITICAL,
        ActionTrigger.IMMEDIATE_DENTIST,
    ),
    ConditionLabel.DISCOLORATION: (
        Severity.NONE,
        ActionTrigger.WHITENING_PRODUCT,
    ),
    ConditionLabel.UNKNOWN: (
        Severity.MILD,
        ActionTrigger.REQUEST_CLEARER_PHOTO,
    ),
}


# Higher = more urgent when comparing conditions
CONDITION_PRIORITY: dict[ConditionLabel, int] = {
    ConditionLabel.SEVERE_GUM_DISEASE: 7,
    ConditionLabel.ADVANCED_CAVITY: 6,
    ConditionLabel.EARLY_CAVITY: 5,
    ConditionLabel.GINGIVITIS: 4,
    ConditionLabel.PLAQUE_TARTAR: 3,
    ConditionLabel.DISCOLORATION: 2,
    ConditionLabel.UNKNOWN: 1,
    ConditionLabel.HEALTHY: 0,
}


def _pick_primary_finding(findings: list[VisualFinding]) -> VisualFinding | None:
    if not findings:
        return None

    pathology = [
        f
        for f in findings
        if f.label not in HEALTHY_LABELS and f.label in LABEL_MAP
    ]
    if pathology:
        return max(
            pathology,
            key=lambda f: (CONDITION_PRIORITY.get(LABEL_MAP[f.label], 0), f.confidence),
        )

    return max(findings, key=lambda f: f.confidence)


def diagnose(request: DiagnoseRequest) -> DiagnoseResponse:
    """Contract: specs/diagnosis.openapi.yaml"""
    if request.overall_quality_score < 0.5:
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
        )

    primary = _pick_primary_finding(request.findings)
    if primary is None:
        condition = ConditionLabel.UNKNOWN
        confidence = 0.0
    else:
        condition = LABEL_MAP.get(primary.label, ConditionLabel.UNKNOWN)
        confidence = primary.confidence

    threshold = CONDITION_THRESHOLDS.get(condition, 0.75)
    meets = confidence >= threshold

    if not meets:
        condition = ConditionLabel.UNKNOWN
        severity, action = Severity.MILD, ActionTrigger.REQUEST_CLEARER_PHOTO
        threshold = 0.0
    else:
        severity, action = CONDITION_META[condition]

    return DiagnoseResponse(
        diagnosis_id=uuid4(),
        user_id=request.user_id,
        analysis_id=request.analysis_id,
        condition_label=condition,
        severity=severity,
        confidence=confidence,
        confidence_threshold=threshold,
        meets_threshold=meets,
        action_trigger=action,
    )
