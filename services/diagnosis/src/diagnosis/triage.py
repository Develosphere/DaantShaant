"""Deterministic rule-based clinical screening triage (Phase 3B-lite).

Converts Teeth Analyzer VISUAL SCREENING findings (``VisualFinding`` codes) into
an AI screening verdict, possible concerns, urgency, recommended actions,
specialist routing, visit timeframe and limitations.

Design constraints honoured here:

* NO LLM/provider call and NO RAG lookup - the mapping is one explicit, testable
  rule table, so the same input always produces the same output.
* Rules keep only lightweight internal metadata (``rule_id`` / ``finding_code`` /
  ``rationale``). Deep evidence grounding (Phase 3A RAG) is deferred, so no
  citations, guideline names or source URLs are fabricated.
* Safety wording: findings stay *screening observations* about a *possible*
  concern that "may be consistent with" what is visible and that "should be
  confirmed by a licensed dentist". Nothing claims a confirmed disease, says
  "you have ...", prescribes treatment, or guarantees an outcome.
* Low confidence / limited visibility only ever ADD a limitation. They never
  increase disease certainty and never escalate urgency.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from dantshaant_common.schemas import (
    ActionTrigger,
    ConditionLabel,
    Severity,
    TriageResult,
    UrgencyLevel,
    VisualFinding,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Urgency ordering, visit timeframes and verdict wording
# ---------------------------------------------------------------------------

# routine < soon < urgent < emergency. Highest applicable urgency wins.
URGENCY_ORDER: dict[UrgencyLevel, int] = {
    UrgencyLevel.ROUTINE: 0,
    UrgencyLevel.SOON: 1,
    UrgencyLevel.URGENT: 2,
    UrgencyLevel.EMERGENCY: 3,
}

VISIT_TIMEFRAME: dict[UrgencyLevel, str] = {
    UrgencyLevel.ROUTINE: "Routine dental checkup",
    UrgencyLevel.SOON: "Arrange a dental evaluation soon",
    UrgencyLevel.URGENT: (
        "Seek a licensed dental evaluation promptly, ideally within about 1 week"
    ),
    UrgencyLevel.EMERGENCY: "Seek urgent/emergency professional care now",
}

VERDICT_BY_URGENCY: dict[UrgencyLevel, str] = {
    UrgencyLevel.ROUTINE: "AI screening suggests routine monitoring",
    UrgencyLevel.SOON: "AI screening suggests arranging a dental evaluation soon",
    UrgencyLevel.URGENT: (
        "AI screening suggests seeking a licensed dental evaluation promptly"
    ),
    UrgencyLevel.EMERGENCY: (
        "AI screening suggests seeking urgent or emergency professional care now"
    ),
}

HEALTHY_VERDICT = (
    "AI screening found no obvious concerning visual finding - routine monitoring"
)
INCONCLUSIVE_VERDICT = (
    "AI screening could not identify a clear visual finding in this image"
)

# ---------------------------------------------------------------------------
# Limitations and the conservative thresholds that produce them
# ---------------------------------------------------------------------------

BASE_LIMITATION = (
    "Screening uses only what is visible in a single photo; it cannot detect pain, "
    "swelling, or conditions that need an examination or x-rays."
)
LOW_QUALITY_LIMITATION = "Image quality limits confidence in this screening result."
LIMITED_VISIBILITY_LIMITATION = (
    "Image visibility limits confidence in this screening result."
)
LOW_CONFIDENCE_LIMITATION = (
    "Some visual findings had low confidence, so this screening result is uncertain."
)

# Documented, deliberately simple: below these values we only state a limitation.
LOW_QUALITY_FLOOR = 0.60
LOW_CONFIDENCE_FLOOR = 0.45
LIMITED_VISIBILITY_VALUES = frozenset({"limited"})


# ---------------------------------------------------------------------------
# Rule table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TriageRule:
    """One explicit finding-code -> screening-guidance rule."""

    rule_id: str
    finding_code: str
    rationale: str
    urgency: UrgencyLevel
    condition_summary: str
    possible_concerns: tuple[str, ...]
    recommended_actions: tuple[str, ...]
    specialist: str | None
    # Legacy DiagnoseResponse compatibility values, so the existing API contract,
    # frontend, live session and persistence keep working unchanged.
    condition_label: ConditionLabel
    severity: Severity
    action_trigger: ActionTrigger


RULES: dict[str, TriageRule] = {
    rule.finding_code: rule
    for rule in (
        TriageRule(
            rule_id="TRIAGE-HEALTHY-001",
            finding_code="healthy_tissue",
            rationale=(
                "Teeth and gums look healthy on visual screening, which supports "
                "routine monitoring rather than any concern."
            ),
            urgency=UrgencyLevel.ROUTINE,
            condition_summary="No obvious concerning visual finding",
            possible_concerns=("No obvious concerning visual finding",),
            recommended_actions=(
                "Maintain good oral hygiene (brush twice daily, clean between teeth)",
                "Continue routine dental checkups",
            ),
            specialist="general dentist",
            condition_label=ConditionLabel.HEALTHY,
            severity=Severity.NONE,
            action_trigger=ActionTrigger.MAINTENANCE_REMINDER,
        ),
        TriageRule(
            rule_id="TRIAGE-PLAQUE-001",
            finding_code="plaque_detected",
            rationale=(
                "Visible plaque film is a hygiene observation that is usually "
                "reversible, so it is screened as routine with a hygiene review."
            ),
            urgency=UrgencyLevel.ROUTINE,
            condition_summary="Possible plaque accumulation",
            possible_concerns=("Visible plaque accumulation",),
            recommended_actions=(
                "Review daily oral hygiene routine",
                "Consider a professional cleaning if plaque persists or is significant",
            ),
            specialist="general dentist",
            condition_label=ConditionLabel.PLAQUE_TARTAR,
            severity=Severity.MILD,
            action_trigger=ActionTrigger.PRODUCT_SUGGEST_BRUSHING,
        ),
        TriageRule(
            rule_id="TRIAGE-TARTAR-001",
            finding_code="tartar",
            rationale=(
                "Calculus/tartar cannot be removed by brushing alone, so a "
                "professional cleaning evaluation is screened as 'soon'."
            ),
            urgency=UrgencyLevel.SOON,
            condition_summary="Possible calculus / tartar buildup",
            possible_concerns=("Visible calculus / tartar buildup",),
            recommended_actions=(
                "Arrange a professional dental cleaning and evaluation",
            ),
            specialist="general dentist",
            condition_label=ConditionLabel.PLAQUE_TARTAR,
            severity=Severity.MILD,
            action_trigger=ActionTrigger.PRODUCT_SUGGEST_BRUSHING,
        ),
        TriageRule(
            rule_id="TRIAGE-CAVITY-SUSPECT-001",
            finding_code="cavity_suspect",
            rationale=(
                "A visible feature may warrant a licensed dental examination; "
                "screening cannot confirm or rule out early decay."
            ),
            urgency=UrgencyLevel.SOON,
            condition_summary="Possible early tooth decay concern",
            possible_concerns=(
                "Visual feature possibly consistent with early tooth decay",
            ),
            recommended_actions=(
                "Arrange a licensed dental examination to confirm or rule out decay",
            ),
            specialist="general dentist",
            condition_label=ConditionLabel.EARLY_CAVITY,
            severity=Severity.MODERATE,
            action_trigger=ActionTrigger.PRODUCT_DENTIST_2_WEEKS,
        ),
        TriageRule(
            rule_id="TRIAGE-CAVITY-ADVANCED-001",
            finding_code="cavity_advanced",
            rationale=(
                "Extensive visible decay/structural change needs prompt licensed "
                "evaluation; the finding code is kept for compatibility but is "
                "never reported as a confirmed advanced cavity."
            ),
            urgency=UrgencyLevel.URGENT,
            condition_summary="Possible significant tooth decay / structural damage",
            possible_concerns=(
                "Significant visible tooth decay or structural tooth damage may be present",
            ),
            recommended_actions=("Seek a prompt licensed dental evaluation",),
            specialist="general dentist / restorative dentist",
            condition_label=ConditionLabel.ADVANCED_CAVITY,
            severity=Severity.HIGH,
            action_trigger=ActionTrigger.DENTIST_URGENT_1_WEEK,
        ),
        TriageRule(
            rule_id="TRIAGE-GINGIVITIS-001",
            finding_code="gingivitis_signs",
            rationale=(
                "Redness/swelling of the gums is a screening observation that "
                "warrants a gum evaluation and professional cleaning."
            ),
            urgency=UrgencyLevel.SOON,
            condition_summary="Possible gum inflammation signs",
            possible_concerns=("Visible gum inflammation signs",),
            recommended_actions=(
                "Arrange a gum evaluation and professional cleaning",
            ),
            specialist="general dentist",
            condition_label=ConditionLabel.GINGIVITIS,
            severity=Severity.MODERATE,
            action_trigger=ActionTrigger.ANTIBACTERIAL_DENTIST,
        ),
        TriageRule(
            rule_id="TRIAGE-GUM-SEVERE-001",
            finding_code="gum_disease_severe",
            rationale=(
                "Visual features possibly consistent with advanced gum disease "
                "need prompt periodontal evaluation by a licensed specialist."
            ),
            urgency=UrgencyLevel.URGENT,
            condition_summary="Possible significant gum (periodontal) abnormality",
            possible_concerns=(
                "Significant periodontal / gum abnormality may be present",
            ),
            recommended_actions=("Seek a prompt periodontal evaluation",),
            specialist="periodontist",
            condition_label=ConditionLabel.SEVERE_GUM_DISEASE,
            severity=Severity.CRITICAL,
            action_trigger=ActionTrigger.IMMEDIATE_DENTIST,
        ),
        TriageRule(
            rule_id="TRIAGE-DISCOLORATION-001",
            finding_code="discoloration",
            rationale=(
                "Discoloration is often cosmetic, so it is screened as routine and "
                "only needs evaluation when persistent, worsening or symptomatic."
            ),
            urgency=UrgencyLevel.ROUTINE,
            condition_summary="Possible tooth discoloration",
            possible_concerns=("Tooth discoloration",),
            recommended_actions=(
                "Maintain oral hygiene and monitor the discoloration",
                "Arrange a dental evaluation if it persists, worsens, or becomes symptomatic",
            ),
            specialist="general dentist",
            condition_label=ConditionLabel.DISCOLORATION,
            severity=Severity.NONE,
            action_trigger=ActionTrigger.WHITENING_PRODUCT,
        ),
        # SAFETY FIX (Phase 3B-lite): this code previously mapped to
        # "Advanced Cavity". A missing/broken tooth is structural damage, not
        # confirmed advanced caries, so it now routes to its own concern.
        TriageRule(
            rule_id="TRIAGE-MISSING-DAMAGED-001",
            finding_code="missing_or_damaged_teeth",
            rationale=(
                "A missing, broken or chipped tooth is structural damage; it is "
                "screened as 'soon' for restorative evaluation and is deliberately "
                "NOT reported as an advanced cavity. Urgency is not escalated "
                "because the current visual contract carries no damage-extent, "
                "bleeding or trauma signal."
            ),
            urgency=UrgencyLevel.SOON,
            condition_summary="Possible missing or damaged tooth",
            possible_concerns=("Missing tooth or structural tooth damage",),
            recommended_actions=("Arrange a restorative dental evaluation",),
            specialist="general dentist / restorative dentist",
            condition_label=ConditionLabel.MISSING_OR_DAMAGED_TOOTH,
            severity=Severity.MODERATE,
            action_trigger=ActionTrigger.PRODUCT_DENTIST_2_WEEKS,
        ),
    )
}

# Inconclusive screening (unrecognised / 'unknown' finding code).
UNKNOWN_RULE = TriageRule(
    rule_id="TRIAGE-UNKNOWN-001",
    finding_code="unknown",
    rationale=(
        "An unclear or unrecognised visual finding is reported as inconclusive "
        "screening rather than guessed into a condition."
    ),
    urgency=UrgencyLevel.ROUTINE,
    condition_summary="Screening inconclusive from this image",
    possible_concerns=("No clear oral finding could be screened from this image",),
    recommended_actions=(
        "Retake the photo in good light with the teeth clearly visible and repeat the screening",
    ),
    specialist=None,
    condition_label=ConditionLabel.UNKNOWN,
    severity=Severity.MILD,
    action_trigger=ActionTrigger.REQUEST_CLEARER_PHOTO,
)

# Variant / legacy vision labels -> canonical rule codes.
FINDING_ALIASES: dict[str, str] = {
    "healthy": "healthy_tissue",
    "plaque": "plaque_detected",
    "calculus": "tartar",
    "cavity": "cavity_suspect",
    "decay": "cavity_suspect",
    "early_cavity": "cavity_suspect",
    "advanced_cavity": "cavity_advanced",
    "severe_decay": "cavity_advanced",
    "gingivitis": "gingivitis_signs",
    "gum_disease": "gum_disease_severe",
    "staining": "discoloration",
    "yellow_teeth": "discoloration",
    # Safety fix: broken/missing teeth are structural damage, NOT advanced caries.
    "broken_teeth": "missing_or_damaged_teeth",
    "missing_teeth": "missing_or_damaged_teeth",
    "damaged_teeth": "missing_or_damaged_teeth",
}

HEALTHY_CODE = "healthy_tissue"

# NOTE: no rule emits ``UrgencyLevel.EMERGENCY``. High-risk signals (severe
# facial/jaw swelling, airway/breathing concern, uncontrolled bleeding, major
# dental/facial trauma) are NOT representable in the current ``VisualFinding``
# contract and are deliberately not invented here. The enum and ordering already
# support emergency for the later unified clinical graph.


@dataclass(frozen=True)
class TriageDecision:
    """Engine output: public screening triage + legacy compatibility values."""

    result: TriageResult
    condition_label: ConditionLabel
    severity: Severity
    action_trigger: ActionTrigger
    driving_confidence: float


def canonical_code(label: str | None) -> str:
    """Normalize a vision label to a canonical rule finding code."""
    code = (label or "").strip().lower().replace(" ", "_").replace("-", "_")
    return FINDING_ALIASES.get(code, code)


def _dedup(values: Sequence[str]) -> list[str]:
    """Order-preserving deduplication (keeps output deterministic)."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _limitations(
    findings: Sequence[VisualFinding],
    overall_quality_score: float | None,
) -> list[str]:
    limitations = [BASE_LIMITATION]
    if overall_quality_score is not None and overall_quality_score < LOW_QUALITY_FLOOR:
        limitations.append(LOW_QUALITY_LIMITATION)
    if any(
        (finding.visibility or "").strip().lower() in LIMITED_VISIBILITY_VALUES
        for finding in findings
    ):
        limitations.append(LIMITED_VISIBILITY_LIMITATION)
    if any(finding.confidence < LOW_CONFIDENCE_FLOOR for finding in findings):
        limitations.append(LOW_CONFIDENCE_LIMITATION)
    return _dedup(limitations)


def _specialist(rules: Sequence[TriageRule]) -> str | None:
    """Merge the specialists of the highest-urgency rules into one string."""
    parts = _dedup(
        part
        for rule in rules
        for part in (rule.specialist or "").split(" / ")
        if part
    )
    return " / ".join(parts) or None


def _inconclusive(overall_quality_score: float | None) -> TriageDecision:
    result = TriageResult(
        verdict=INCONCLUSIVE_VERDICT,
        condition_summary=UNKNOWN_RULE.condition_summary,
        possible_concerns=list(UNKNOWN_RULE.possible_concerns),
        urgency_level=UNKNOWN_RULE.urgency,
        recommended_actions=list(UNKNOWN_RULE.recommended_actions),
        recommended_specialist=UNKNOWN_RULE.specialist,
        visit_timeframe=VISIT_TIMEFRAME[UNKNOWN_RULE.urgency],
        limitations=_limitations([], overall_quality_score),
        supporting_findings=[],
        rule_ids=[UNKNOWN_RULE.rule_id],
        confidence=None,
    )
    return TriageDecision(
        result=result,
        condition_label=UNKNOWN_RULE.condition_label,
        severity=UNKNOWN_RULE.severity,
        action_trigger=UNKNOWN_RULE.action_trigger,
        driving_confidence=0.0,
    )


def triage(
    findings: Sequence[VisualFinding] | None,
    *,
    overall_quality_score: float | None = None,
) -> TriageDecision:
    """Run the deterministic rule engine over visual screening findings.

    Highest applicable urgency wins; concerns/actions/limitations/findings are
    deduplicated; low confidence or limited visibility only add limitations.
    """
    matched: list[tuple[int, VisualFinding, TriageRule]] = []
    for index, finding in enumerate(findings or []):
        rule = RULES.get(canonical_code(finding.label))
        if rule is not None:
            matched.append((index, finding, rule))

    if not matched:
        decision = _inconclusive(overall_quality_score)
    else:
        # A healthy-looking area does not cancel out a concurrent concern.
        concerning = [m for m in matched if m[2].finding_code != HEALTHY_CODE]
        effective = concerning or matched
        # Deterministic order: highest urgency first, then original input order.
        ordered = sorted(
            effective, key=lambda m: (-URGENCY_ORDER[m[2].urgency], m[0])
        )
        driving_finding, driving_rule = ordered[0][1], ordered[0][2]
        urgency = driving_rule.urgency

        top_rules = [rule for _, _, rule in ordered if rule.urgency == urgency]

        result = TriageResult(
            # Only an exclusively-healthy screening reports the healthy verdict.
            verdict=HEALTHY_VERDICT if not concerning else VERDICT_BY_URGENCY[urgency],
            condition_summary=driving_rule.condition_summary,
            possible_concerns=_dedup(
                concern for _, _, rule in ordered for concern in rule.possible_concerns
            ),
            urgency_level=urgency,
            recommended_actions=_dedup(
                action for _, _, rule in ordered for action in rule.recommended_actions
            ),
            recommended_specialist=_specialist(top_rules),
            visit_timeframe=VISIT_TIMEFRAME[urgency],
            limitations=_limitations(
                [finding for _, finding, _ in ordered], overall_quality_score
            ),
            supporting_findings=_dedup(
                rule.finding_code for _, _, rule in ordered
            ),
            rule_ids=_dedup(rule.rule_id for _, _, rule in ordered),
            # Conservative: the confidence of the finding driving the verdict.
            # Aggregation never raises certainty above the driving observation.
            confidence=round(driving_finding.confidence, 2),
        )
        decision = TriageDecision(
            result=result,
            condition_label=driving_rule.condition_label,
            severity=driving_rule.severity,
            action_trigger=driving_rule.action_trigger,
            driving_confidence=driving_finding.confidence,
        )

    # Safe observability: rule ids / urgency / counts only. Never image bytes,
    # base64, prompts or keys.
    logger.info(
        "[TRIAGE] rule_ids=%s highest_urgency=%s finding_count=%d",
        ",".join(decision.result.rule_ids),
        decision.result.urgency_level.value,
        len(findings or []),
    )
    return decision


def triage_findings(
    findings: Sequence[VisualFinding] | None,
    *,
    overall_quality_score: float | None = None,
) -> TriageResult:
    """Convenience wrapper returning only the public screening triage result."""
    return triage(findings, overall_quality_score=overall_quality_score).result


__all__ = [
    "BASE_LIMITATION",
    "FINDING_ALIASES",
    "HEALTHY_VERDICT",
    "INCONCLUSIVE_VERDICT",
    "LIMITED_VISIBILITY_LIMITATION",
    "LOW_CONFIDENCE_LIMITATION",
    "LOW_QUALITY_LIMITATION",
    "RULES",
    "TriageDecision",
    "TriageRule",
    "UNKNOWN_RULE",
    "URGENCY_ORDER",
    "VERDICT_BY_URGENCY",
    "VISIT_TIMEFRAME",
    "canonical_code",
    "triage",
    "triage_findings",
]
