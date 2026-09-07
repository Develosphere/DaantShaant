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

---

## 5. YOLO Dental Pathology Perception Evaluation (Phase 11B-1 & 11B-2)

Phase 11B added dedicated offline tools for calibrating the YOLO oral disease detector, mining hard negatives, and preparing v2 refinement:

| Tool / Document | Purpose | CLI Example |
|---|---|---|
| **Dataset Audit** (`scripts/audit_yolo_dataset.py`) | Evaluates class distribution, box sizes, and counts empty label (true negative) images. | `python scripts/audit_yolo_dataset.py --dataset dataset/oral-disease.yolov11` |
| **Calibration Analysis** (`scripts/evaluate_yolo_calibration.py`) | Sweeps confidence thresholds (0.30–0.80) to produce per-class Precision/Recall/F1 and confusion curves. | `python scripts/evaluate_yolo_calibration.py --model path/to/best.pt --split valid` |
| **Hard-Negative Miner** (`scripts/mine_yolo_hard_negatives.py`) | Mines false positives on empty-label training images; outputs `review.csv` and visual contact sheets. | `python scripts/mine_yolo_hard_negatives.py --split train --min-confidence 0.30` |
| **v2 Dataset Preparation** (`scripts/prepare_yolo_v2_dataset.py`) | Merges Nathan-approved hard negatives into TRAIN only; leaves VALID/TEST 100% untouched; supports `--negative-repeat 2`. | `python scripts/prepare_yolo_v2_dataset.py --review-csv dataset/hard-negative-candidates/review.csv` |
| **Modal v2 Fine-Tuning** (`scripts/modal_train_yolo_v2.py`) | Remote fine-tuning starting from uploaded `/root/best_v1.pt` on A10G with AdamW lr0=0.0005. | `modal run scripts/modal_train_yolo_v2.py` |
| **v1 vs v2 Comparison** (`scripts/compare_yolo_models.py`) | Side-by-side comparative evaluation of baseline vs fine-tuned weights on untouched valid/test sets. | `python scripts/compare_yolo_models.py --model-a best.pt --model-b best_v2.pt` |
| **Manual Acceptance Matrix** (`docs/evaluation/yolo_manual_acceptance.md`) | Protocol for human acceptance testing across 10 distinct clinical categories (A–J). | *Manual testing by Nathan* |
| **Hard Negatives Guide** (`docs/evaluation/yolo_hard_negatives_guide.md`) | Step-by-step instructions for candidate review, v2 dataset creation, Modal training, and acceptance. | *Reference document* |

---

## 6. DentalTensor Vision v1.0 — Model Identity & Freeze (Phase 11B Final)

The custom oral pathology perception model developed by **Nathan Asif** has been officially frozen and branded as **DentalTensor Vision v1.0**:

- **Model Identity:** DentalTensor Vision v1.0
- **Developer / Author:** Nathan Asif
- **Primary Integration:** DaantShaant
- **Production Checkpoint:** `services/teeth_analyzer/models/oral_disease/dentaltensor_nathan_asif_v1.pt` (byte-for-byte identical to `best_v2.pt`, SHA-256 verified)
- **Rollback Checkpoints Retained:** `services/teeth_analyzer/models/oral_disease/best_v2.pt` and `best.pt`
- **Config Key:** `YOLO_DENTAL_MODEL_PATH`
- **Model Card:** [`docs/dentaltensor-model-card.md`](dentaltensor-model-card.md)
- **Final Engineering Screening Thresholds:**
  - `calculus` (`tartar`): **`0.35`**
  - `caries` (`cavity_suspect`): **`0.55`**
  - `gingivitis` (`gingivitis_signs`): **`0.50`**
  - `tooth discoloration` (`discoloration`): **`0.65`**
  - `ulcer` (`oral_ulcer`): **`0.65`**
  - Global Fallback: **`0.50`**

> [!IMPORTANT]
> **Engineering Screening Thresholds Only:** These calibrated cutoff values represent engineering screening thresholds chosen to balance sensitivity and false-positive suppression on intraoral photographs. They do **not** constitute medical validation claims or diagnostic guarantees.

