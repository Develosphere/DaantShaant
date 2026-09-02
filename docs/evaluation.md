# DaantShaant Evaluation Harness & Metrics (Phase 8-lite)

The DaantShaant evaluation harness provides a reproducible, lightweight benchmark suite for assessing:
1. **Semantic Dental Relevance**: Image gating accuracy and class-level confusion.
2. **Clinical Visual Findings**: Multi-label set-based precision, recall, F1, and exact-match rates.
3. **Deterministic Triage**: Urgency classification accuracy and specialist routing validity.
4. **Safety Phrasing Checks**: Detection of definitive diagnosis claims in patient-facing output.
5. **Dentist Recommendation Ranking**: Verification that clinical specialist relevance outranks commercial partner status.
6. **Pipeline Latency Distribution**: Statistical profiling (mean, median, p95, min, max).
7. **AI Provider Fallback**: Monitoring provider technical fallback rates.

---

## 1. Dataset Manifest Format

Manifest files define benchmark cases with expected ground truth:

```json
{
  "description": "Intraoral Caries and Hygiene Benchmark Candidate",
  "version": "1.0",
  "cases": [
    {
      "id": "case-001",
      "image_path": "external/fixtures/intraoral_cavity_01.jpg",
      "expected_relevance": "relevant",
      "expected_findings": ["cavity_suspect"],
      "expected_urgency": "soon",
      "expected_specialist": "restorative dentist",
      "source": "Roboflow Oral Disease / Synthetic Candidate",
      "license": "CC-BY-4.0",
      "attribution": "Oral Disease Dataset Contributors",
      "notes": "Clear intraoral view of occlusal surface."
    }
  ]
}
```

### Dataset Privacy & Provenance Rules
- **No private or patient medical images** are committed to version control.
- External benchmark images stay outside Git repository paths.
- Manifest entries support `source`, `license`, and `attribution` for provenance tracking without bundling raw datasets.

---

## 2. Evaluation Metrics

| Metric Area | Metric | Definition / Scope |
|---|---|---|
| **Relevance** | Accuracy | $\frac{\text{Correct Predictions}}{\text{Total Cases}}$ across `relevant`, `retake`, `unrelated` |
| | Confusion Matrix | Per-class true vs predicted distribution |
| **Findings** | Multi-label Precision | $\frac{TP}{TP + FP}$ across visual finding codes |
| | Multi-label Recall | $\frac{TP}{TP + FN}$ across visual finding codes |
| | Multi-label F1 | Harmonic mean $\frac{2 \cdot P \cdot R}{P + R}$ |
| | Exact Match Rate | % of cases where predicted findings exactly match expected set |
| **Triage** | Urgency Accuracy | % cases matching deterministic urgency level (`routine`/`soon`/`urgent`/`emergency`) |
| | Specialist Accuracy | % cases matching expected dental specialty |
| **Safety** | Unsafe Wording Count | Count of definitive diagnosis phrases (e.g. "you have advanced cavity") detected |
| **Dentist Ranking** | Scenario Accuracy | Benchmark scenarios testing specialist relevance over commercial partner status |
| **Latency** | Median & p95 | Millisecond execution time distribution across pipeline stages |
| **Fallback** | Fallback Rate | % of requests utilizing secondary provider technical fallback |

---

## 3. Execution Modes

### A. Offline / Mock Mode (Default)
- Uses synthetic fixtures and simulated responses.
- Makes **zero** real external network or AI API calls.
- Ideal for CI/CD, regression checks, and demonstration metric generation.

```bash
python scripts/run_evaluation.py
```

### B. Real / Manual Mode
- Requires the explicit `--real` flag.
- Intended for controlled developer-run benchmarking against external evaluation images.

```bash
python scripts/run_evaluation.py --real --manifest path/to/real_manifest.json
```

---

## 4. CLI Options

```bash
# Run default offline evaluation with human-readable summary
python scripts/run_evaluation.py

# Output machine-readable demo JSON summary
python scripts/run_evaluation.py --summary-only

# Save full evaluation report to JSON
python scripts/run_evaluation.py --json-out evaluation-results.json
```
