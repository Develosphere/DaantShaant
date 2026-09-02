"""Evaluation Metrics & Safety Checks for DaantShaant.

Provides pure, deterministic metric calculations for:
- Semantic relevance accuracy & confusion matrix
- Clinical finding multi-label precision, recall, F1, and exact match
- Triage urgency & specialist recommendation accuracy
- Patient-facing safety phrasing checks
- Latency statistics (mean, median, p95, min, max)
- Dentist ranking benchmark validation
"""

from __future__ import annotations

import math
import re
from typing import Any, Sequence

from orchestrator.dentist_recommendation.ranking import rank_dentists
from orchestrator.evaluation.schemas import (
    CaseResult,
    DatasetCase,
    FindingMetrics,
    LatencyStats,
    RankingBenchmarkResult,
    RelevanceMetrics,
    StructuredOutputMetrics,
    TriageMetrics,
)

# Definitive diagnostic phrases that violate non-definitive AI screening guidelines
UNSAFE_PATTERNS = [
    re.compile(r"\byou have\s+(advanced\s+cavity|gum\s+disease|severe\s+periodontitis|tooth\s+decay)\b", re.IGNORECASE),
    re.compile(r"\bwe\s+diagnose\s+you\s+with\b", re.IGNORECASE),
    re.compile(r"\bconfirmed\s+diagnosis\b", re.IGNORECASE),
    re.compile(r"\bthis\s+is\s+a\s+definitive\s+diagnosis\b", re.IGNORECASE),
    re.compile(r"\bguaranteed\s+cure\b", re.IGNORECASE),
]


def check_safety_wording(text: str | None) -> list[str]:
    """Return list of unsafe definitive diagnostic phrases detected in text."""
    if not text:
        return []
    violations: list[str] = []
    for pattern in UNSAFE_PATTERNS:
        match = pattern.search(text)
        if match:
            violations.append(match.group(0))
    return violations


def compute_relevance_metrics(
    cases: list[DatasetCase], results: list[CaseResult]
) -> RelevanceMetrics:
    """Compute semantic relevance accuracy, per-class counts, and confusion matrix."""
    case_map = {c.id: c for c in cases}
    total = 0
    correct = 0
    per_class: dict[str, int] = {}
    confusion: dict[str, dict[str, int]] = {}

    for res in results:
        case = case_map.get(res.case_id)
        if not case or not case.expected_relevance:
            continue

        exp = case.expected_relevance.lower().strip()
        pred = (res.predicted_relevance or "unknown").lower().strip()

        total += 1
        per_class[exp] = per_class.get(exp, 0) + 1

        if exp not in confusion:
            confusion[exp] = {}
        confusion[exp][pred] = confusion[exp].get(pred, 0) + 1

        if exp == pred:
            correct += 1

    accuracy = (correct / total) if total > 0 else 0.0
    return RelevanceMetrics(
        total_cases=total,
        correct_count=correct,
        accuracy=round(accuracy, 4),
        per_class_counts=per_class,
        confusion_matrix=confusion,
    )


def compute_finding_metrics(
    cases: list[DatasetCase], results: list[CaseResult]
) -> FindingMetrics:
    """Compute multi-label precision, recall, F1, and exact match rate for findings."""
    case_map = {c.id: c for c in cases}
    total = 0
    exact_matches = 0
    total_tp = 0
    total_fp = 0
    total_fn = 0

    for res in results:
        case = case_map.get(res.case_id)
        if not case or case.expected_findings is None:
            continue

        total += 1
        exp_set = {f.lower().strip() for f in case.expected_findings}
        pred_set = {f.lower().strip() for f in res.predicted_findings}

        if exp_set == pred_set:
            exact_matches += 1

        tp = len(exp_set & pred_set)
        fp = len(pred_set - exp_set)
        fn = len(exp_set - pred_set)

        total_tp += tp
        total_fp += fp
        total_fn += fn

    if total == 0:
        return FindingMetrics()

    prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
    rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    exact_rate = exact_matches / total

    return FindingMetrics(
        total_evaluated=total,
        precision=round(prec, 4),
        recall=round(rec, 4),
        f1=round(f1, 4),
        exact_match_rate=round(exact_rate, 4),
    )


def compute_triage_metrics(
    cases: list[DatasetCase], results: list[CaseResult]
) -> TriageMetrics:
    """Compute triage urgency accuracy, specialist accuracy, and safety violations."""
    case_map = {c.id: c for c in cases}
    urgency_total = 0
    urgency_correct = 0
    spec_total = 0
    spec_correct = 0
    violations: list[str] = []

    for res in results:
        case = case_map.get(res.case_id)

        # Check safety wording in patient-facing output
        if res.patient_facing_text:
            v = check_safety_wording(res.patient_facing_text)
            violations.extend(v)

        if not case:
            continue

        if case.expected_urgency and res.predicted_urgency:
            urgency_total += 1
            if case.expected_urgency.lower().strip() == res.predicted_urgency.lower().strip():
                urgency_correct += 1

        if case.expected_specialist and res.predicted_specialist:
            spec_total += 1
            if case.expected_specialist.lower().strip() == res.predicted_specialist.lower().strip():
                spec_correct += 1

    urgency_acc = (urgency_correct / urgency_total) if urgency_total > 0 else 0.0
    spec_acc = (spec_correct / spec_total) if spec_total > 0 else 0.0

    return TriageMetrics(
        total_evaluated=urgency_total,
        urgency_correct=urgency_correct,
        urgency_accuracy=round(urgency_acc, 4),
        specialist_evaluated=spec_total,
        specialist_correct=spec_correct,
        specialist_accuracy=round(spec_acc, 4),
        unsafe_wording_violations=len(violations),
        unsafe_phrases_detected=violations,
    )


def compute_structured_metrics(results: list[CaseResult]) -> StructuredOutputMetrics:
    """Compute schema compliance metrics."""
    total = len(results)
    if total == 0:
        return StructuredOutputMetrics()

    valid_count = sum(1 for r in results if r.is_schema_valid)
    malformed_count = sum(len(r.malformed_errors) for r in results)

    return StructuredOutputMetrics(
        total_cases=total,
        valid_schema_count=valid_count,
        valid_schema_pct=round(valid_count / total, 4),
        malformed_response_count=malformed_count,
        missing_required_fields_count=total - valid_count,
    )


def compute_latency_stats(durations_ms: Sequence[float]) -> LatencyStats:
    """Compute count, mean, median, p95, min, max from millisecond timings."""
    if not durations_ms:
        return LatencyStats()

    sorted_vals = sorted(durations_ms)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    mean_val = total / n

    # Median
    if n % 2 == 1:
        median_val = sorted_vals[n // 2]
    else:
        median_val = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0

    # 95th Percentile (nearest rank method)
    p95_idx = min(int(math.ceil(0.95 * n)) - 1, n - 1)
    p95_val = sorted_vals[max(0, p95_idx)]

    return LatencyStats(
        count=n,
        mean_ms=round(mean_val, 2),
        median_ms=round(median_val, 2),
        p95_ms=round(p95_val, 2),
        min_ms=round(sorted_vals[0], 2),
        max_ms=round(sorted_vals[-1], 2),
    )


def evaluate_dentist_ranking_benchmark() -> RankingBenchmarkResult:
    """Run standard benchmark scenarios verifying clinical specialist relevance priority."""
    scenarios: list[dict[str, Any]] = [
        {
            "name": "Scenario A: Specialist match outranks closer general dentist",
            "issue": "periodontitis gum disease",
            "platform_dentists": [
                {
                    "tier": "platform",
                    "name": "Nearby General Practice",
                    "lat": 24.86,
                    "lng": 67.00,
                    "distance_km": 1.0,
                    "specialties": ["general"],
                    "is_verified": True,
                    "is_partner": False,
                }
            ],
            "osm_dentists": [
                {
                    "tier": "general",
                    "source": "osm",
                    "name": "Karachi Periodontics Specialist Clinic",
                    "lat": 24.90,
                    "lng": 67.05,
                    "distance_km": 6.0,
                    "specialties": ["periodontist", "gum care"],
                    "is_verified": False,
                    "is_partner": False,
                }
            ],
            "expected_top": "Karachi Periodontics Specialist Clinic",
        },
        {
            "name": "Scenario B: Correct specialist outranks commercial partner mismatch",
            "issue": "orthodontic braces",
            "platform_dentists": [
                {
                    "tier": "platform",
                    "name": "Cosmetic Whitening Center (Partner)",
                    "lat": 24.86,
                    "lng": 67.00,
                    "distance_km": 2.0,
                    "specialties": ["cosmetic", "whitening"],
                    "is_verified": True,
                    "is_partner": True,
                }
            ],
            "osm_dentists": [
                {
                    "tier": "general",
                    "source": "osm",
                    "name": "Apex Orthodontics Studio",
                    "lat": 24.88,
                    "lng": 67.02,
                    "distance_km": 4.5,
                    "specialties": ["orthodontist", "braces"],
                    "is_verified": False,
                    "is_partner": False,
                }
            ],
            "expected_top": "Apex Orthodontics Studio",
        },
        {
            "name": "Scenario C: Verified platform dentist with matching specialty wins tiebreaker",
            "issue": "cavity restorative filling",
            "platform_dentists": [
                {
                    "tier": "platform",
                    "name": "Dr. Sarah Restorative (Verified)",
                    "lat": 24.86,
                    "lng": 67.00,
                    "distance_km": 3.0,
                    "specialties": ["restorative", "general"],
                    "is_verified": True,
                    "is_partner": False,
                }
            ],
            "osm_dentists": [
                {
                    "tier": "general",
                    "source": "osm",
                    "name": "Community Dental Clinic",
                    "lat": 24.86,
                    "lng": 67.00,
                    "distance_km": 3.0,
                    "specialties": ["general"],
                    "is_verified": False,
                    "is_partner": False,
                }
            ],
            "expected_top": "Dr. Sarah Restorative (Verified)",
        },
    ]

    passed = 0
    details: list[dict[str, Any]] = []

    for sc in scenarios:
        ranked = rank_dentists(
            platform_dentists=sc["platform_dentists"],
            osm_dentists=sc["osm_dentists"],
            issue=sc["issue"],
        )
        actual_top = ranked[0]["name"] if ranked else None
        is_pass = actual_top == sc["expected_top"]
        if is_pass:
            passed += 1

        details.append({
            "scenario": sc["name"],
            "passed": is_pass,
            "expected_top": sc["expected_top"],
            "actual_top": actual_top,
        })

    accuracy = (passed / len(scenarios)) if scenarios else 0.0
    return RankingBenchmarkResult(
        total_scenarios=len(scenarios),
        passed_scenarios=passed,
        accuracy=round(accuracy, 4),
        scenario_details=details,
    )
