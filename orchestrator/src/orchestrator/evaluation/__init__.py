"""DaantShaant Evaluation Harness & Demo Metrics Package (Phase 8-lite)."""

from orchestrator.evaluation.metrics import (
    check_safety_wording,
    compute_finding_metrics,
    compute_latency_stats,
    compute_relevance_metrics,
    compute_structured_metrics,
    compute_triage_metrics,
    evaluate_dentist_ranking_benchmark,
)
from orchestrator.evaluation.runner import (
    format_evaluation_summary,
    load_manifest,
    run_evaluation,
)
from orchestrator.evaluation.schemas import (
    CaseResult,
    DatasetCase,
    EvaluationReport,
    FindingMetrics,
    LatencyStats,
    Manifest,
    RankingBenchmarkResult,
    RelevanceMetrics,
    StructuredOutputMetrics,
    TriageMetrics,
)

__all__ = [
    "DatasetCase",
    "Manifest",
    "CaseResult",
    "LatencyStats",
    "RelevanceMetrics",
    "FindingMetrics",
    "TriageMetrics",
    "StructuredOutputMetrics",
    "RankingBenchmarkResult",
    "EvaluationReport",
    "check_safety_wording",
    "compute_relevance_metrics",
    "compute_finding_metrics",
    "compute_triage_metrics",
    "compute_structured_metrics",
    "compute_latency_stats",
    "evaluate_dentist_ranking_benchmark",
    "load_manifest",
    "run_evaluation",
    "format_evaluation_summary",
]
