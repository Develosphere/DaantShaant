"""Tests for Phase 8-lite: Evaluation Harness & Demo Metrics.

16 required tests covering:
- Relevance accuracy & confusion matrix
- Finding precision, recall, F1, exact match
- Triage urgency accuracy
- Safety phrasing detection
- Latency statistics (mean, median, p95)
- Fallback metric normalization
- Dentist ranking benchmark evaluation
- Manifest parser & missing field safety
- No patient image/base64 leakage in results

ZERO real external network calls.
"""

import asyncio
from pathlib import Path
import pytest

from orchestrator.evaluation.schemas import (
    CaseResult,
    DatasetCase,
    Manifest,
)
from orchestrator.evaluation.metrics import (
    check_safety_wording,
    compute_finding_metrics,
    compute_latency_stats,
    compute_relevance_metrics,
    compute_structured_metrics,
    compute_triage_metrics,
    evaluate_dentist_ranking_benchmark,
)
from orchestrator.evaluation.runner import load_manifest, run_evaluation


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Test 1: Relevance accuracy computation
# ---------------------------------------------------------------------------
def test_relevance_accuracy_computation():
    cases = [
        DatasetCase(id="c1", expected_relevance="relevant"),
        DatasetCase(id="c2", expected_relevance="retake"),
        DatasetCase(id="c3", expected_relevance="unrelated"),
        DatasetCase(id="c4", expected_relevance="relevant"),
    ]
    results = [
        CaseResult(case_id="c1", predicted_relevance="relevant"),
        CaseResult(case_id="c2", predicted_relevance="retake"),
        CaseResult(case_id="c3", predicted_relevance="relevant"),  # mismatch
        CaseResult(case_id="c4", predicted_relevance="relevant"),
    ]
    metrics = compute_relevance_metrics(cases, results)
    assert metrics.total_cases == 4
    assert metrics.correct_count == 3
    assert metrics.accuracy == 0.75


# ---------------------------------------------------------------------------
# Test 2: Confusion counts
# ---------------------------------------------------------------------------
def test_relevance_confusion_counts():
    cases = [
        DatasetCase(id="c1", expected_relevance="relevant"),
        DatasetCase(id="c2", expected_relevance="relevant"),
        DatasetCase(id="c3", expected_relevance="retake"),
    ]
    results = [
        CaseResult(case_id="c1", predicted_relevance="relevant"),
        CaseResult(case_id="c2", predicted_relevance="retake"),
        CaseResult(case_id="c3", predicted_relevance="retake"),
    ]
    metrics = compute_relevance_metrics(cases, results)
    assert metrics.per_class_counts["relevant"] == 2
    assert metrics.per_class_counts["retake"] == 1
    assert metrics.confusion_matrix["relevant"]["relevant"] == 1
    assert metrics.confusion_matrix["relevant"]["retake"] == 1
    assert metrics.confusion_matrix["retake"]["retake"] == 1


# ---------------------------------------------------------------------------
# Test 3: Multi-label precision
# ---------------------------------------------------------------------------
def test_finding_precision():
    cases = [
        DatasetCase(id="c1", expected_findings=["tartar"]),
    ]
    results = [
        CaseResult(case_id="c1", predicted_findings=["tartar", "cavity_suspect"]),
    ]
    metrics = compute_finding_metrics(cases, results)
    # TP = 1, FP = 1 -> Precision = 1 / (1 + 1) = 0.5
    assert metrics.precision == 0.5


# ---------------------------------------------------------------------------
# Test 4: Multi-label recall
# ---------------------------------------------------------------------------
def test_finding_recall():
    cases = [
        DatasetCase(id="c1", expected_findings=["tartar", "gingivitis_signs"]),
    ]
    results = [
        CaseResult(case_id="c1", predicted_findings=["tartar"]),
    ]
    metrics = compute_finding_metrics(cases, results)
    # TP = 1, FN = 1 -> Recall = 1 / (1 + 1) = 0.5
    assert metrics.recall == 0.5


# ---------------------------------------------------------------------------
# Test 5: Multi-label F1
# ---------------------------------------------------------------------------
def test_finding_f1():
    cases = [
        DatasetCase(id="c1", expected_findings=["tartar", "gingivitis_signs"]),
    ]
    results = [
        CaseResult(case_id="c1", predicted_findings=["tartar", "cavity_suspect"]),
    ]
    # TP = 1, FP = 1 (prec = 0.5), FN = 1 (rec = 0.5) -> F1 = 0.5
    metrics = compute_finding_metrics(cases, results)
    assert metrics.f1 == 0.5


# ---------------------------------------------------------------------------
# Test 6: Exact match rate
# ---------------------------------------------------------------------------
def test_finding_exact_match():
    cases = [
        DatasetCase(id="c1", expected_findings=["tartar"]),
        DatasetCase(id="c2", expected_findings=["cavity_suspect", "tartar"]),
    ]
    results = [
        CaseResult(case_id="c1", predicted_findings=["tartar"]),
        CaseResult(case_id="c2", predicted_findings=["tartar"]),  # partial, not exact
    ]
    metrics = compute_finding_metrics(cases, results)
    assert metrics.total_evaluated == 2
    assert metrics.exact_match_rate == 0.5


# ---------------------------------------------------------------------------
# Test 7: Triage urgency accuracy
# ---------------------------------------------------------------------------
def test_triage_urgency_accuracy():
    cases = [
        DatasetCase(id="c1", expected_urgency="routine"),
        DatasetCase(id="c2", expected_urgency="urgent"),
        DatasetCase(id="c3", expected_urgency="emergency"),
    ]
    results = [
        CaseResult(case_id="c1", predicted_urgency="routine"),
        CaseResult(case_id="c2", predicted_urgency="urgent"),
        CaseResult(case_id="c3", predicted_urgency="soon"),  # mismatch
    ]
    metrics = compute_triage_metrics(cases, results)
    assert metrics.total_evaluated == 3
    assert metrics.urgency_correct == 2
    assert metrics.urgency_accuracy == round(2 / 3, 4)


# ---------------------------------------------------------------------------
# Test 8: Unsafe wording detection
# ---------------------------------------------------------------------------
def test_unsafe_wording_detection():
    safe_text = "AI screening suggests possible tooth decay. Follow up with a dentist."
    unsafe_text = "We confirm that you have advanced cavity and definitive diagnosis is complete."

    assert check_safety_wording(safe_text) == []
    violations = check_safety_wording(unsafe_text)
    assert len(violations) > 0
    assert any("advanced cavity" in v.lower() or "definitive diagnosis" in v.lower() for v in violations)


# ---------------------------------------------------------------------------
# Test 9: Latency mean
# ---------------------------------------------------------------------------
def test_latency_mean():
    latencies = [100.0, 200.0, 300.0, 400.0]
    stats = compute_latency_stats(latencies)
    assert stats.count == 4
    assert stats.mean_ms == 250.0


# ---------------------------------------------------------------------------
# Test 10: Latency median
# ---------------------------------------------------------------------------
def test_latency_median():
    # Odd count
    assert compute_latency_stats([100.0, 200.0, 500.0]).median_ms == 200.0
    # Even count
    assert compute_latency_stats([100.0, 200.0, 300.0, 400.0]).median_ms == 250.0


# ---------------------------------------------------------------------------
# Test 11: Latency p95
# ---------------------------------------------------------------------------
def test_latency_p95():
    latencies = list(range(1, 101))  # 1 to 100
    stats = compute_latency_stats(latencies)
    assert stats.p95_ms == 95.0


# ---------------------------------------------------------------------------
# Test 12: Fallback metric normalization
# ---------------------------------------------------------------------------
def test_fallback_metric_normalization():
    results = [
        CaseResult(case_id="c1", provider="qwen", fallback_used=False),
        CaseResult(case_id="c2", provider="gemini", fallback_used=True),
    ]
    manifest = Manifest(cases=[DatasetCase(id="c1"), DatasetCase(id="c2")])
    report = _run(run_evaluation(manifest, real=False))
    # In mock simulation, default fallback is tracked
    assert "fallback_rate" in report.demo_summary
    assert 0.0 <= report.demo_summary["fallback_rate"] <= 1.0


# ---------------------------------------------------------------------------
# Test 13: Specialist ranking evaluation
# ---------------------------------------------------------------------------
def test_dentist_ranking_benchmark():
    res = evaluate_dentist_ranking_benchmark()
    assert res.total_scenarios >= 3
    assert res.passed_scenarios == res.total_scenarios
    assert res.accuracy == 1.0


# ---------------------------------------------------------------------------
# Test 14: Manifest parser
# ---------------------------------------------------------------------------
def test_manifest_parser():
    fixture_path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "orchestrator"
        / "evaluation"
        / "fixtures"
        / "manifest.example.json"
    )
    manifest = load_manifest(fixture_path)
    assert len(manifest.cases) >= 4
    assert manifest.cases[0].id == "case-rel-001"
    assert manifest.cases[0].expected_relevance == "relevant"


# ---------------------------------------------------------------------------
# Test 15: Missing optional fields safe
# ---------------------------------------------------------------------------
def test_missing_optional_fields_safe():
    minimal_case = DatasetCase(id="min-01")
    assert minimal_case.id == "min-01"
    assert minimal_case.image_path is None
    assert minimal_case.expected_relevance is None
    assert minimal_case.expected_findings == []
    assert minimal_case.source is None

    # Runner handles minimal cases safely
    manifest = Manifest(cases=[minimal_case])
    report = _run(run_evaluation(manifest, real=False))
    assert report.total_cases == 1
    assert report.relevance.total_cases == 0


# ---------------------------------------------------------------------------
# Test 16: No patient image / base64 leaked into results
# ---------------------------------------------------------------------------
def test_no_patient_image_or_base64_in_results():
    case = DatasetCase(
        id="case-sec",
        image_path="/path/to/private/intraoral_image.jpg",
        expected_relevance="relevant",
    )
    manifest = Manifest(cases=[case])
    report = _run(run_evaluation(manifest, real=False))
    dumped = report.model_dump_json()

    # Assert no image file path, raw bytes, or base64 keys exist in serialized report
    assert "data:image" not in dumped
    assert "private/intraoral_image.jpg" not in dumped
