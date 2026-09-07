# DaantShaant Hard-Negative Mining & YOLO v2 Refinement Guide (Phase 11B-2)

> This document defines the exact workflow for Phase 11B-2:
> 1. Hard-negative mining on empty-label training images.
> 2. Nathan manual review of candidates via `review.csv` and contact sheets.
> 3. Dataset preparation preserving 100% untouched validation and test benchmark sets.
> 4. Remote Modal fine-tuning from `best_v1.pt`.
> 5. Honest side-by-side evaluation of v1 vs v2.

---

## 1. Mining Results Summary

From the 457 empty-label training images in `dataset/oral-disease.yolov11/train/`:
- **Total Empty-Label Images Evaluated**: 457
- **False-Positive Candidate Images (confidence >= 0.30)**: **36**
- **Clean Images (No detections >= 0.30)**: **421** (92.1% pass rate)
- **Total False-Positive Bounding Boxes**: **86**
- **Class Breakdown of False Positives**:
  - `tooth discoloration`: 47 detections (54.7% of all false positives)
  - `caries`: 22 detections (25.6%)
  - `calculus`: 16 detections (18.6%)
  - `ulcer`: 1 detection (1.2%)
  - `gingivitis`: 0 detections (0.0%)

Artifacts generated:
- CSV: `dataset/hard-negative-candidates/review.csv`
- JSON: `dataset/hard-negative-candidates/candidates.json`
- Visual Contact Sheets:
  - `dataset/hard-negative-candidates/contact_sheet_01.jpg` (20 tiles)
  - `dataset/hard-negative-candidates/contact_sheet_02.jpg` (16 tiles)

---

## 2. Nathan Manual Review Workflow

Before building the v2 dataset, inspect the contact sheets and edit `dataset/hard-negative-candidates/review.csv`:

### Valid Statuses for `review_status`:
- `ACCEPT_NEGATIVE`: Image is confirmed clinically clean or has only harmless normal variations (yellowish enamel, shadows, saliva reflection). Safe to use as a hard negative in v2 training.
- `REJECT_UNCERTAIN`: Image has ambiguous appearance or poor clarity.
- `REJECT_POSSIBLE_PATHOLOGY`: Image appears to contain actual clinical pathology (caries, tartar, gingivitis, or ulcer) that Roboflow annotators missed. Must NOT be trained as a negative.

Only candidates marked **`ACCEPT_NEGATIVE`** will be imported into the v2 training dataset.

---

## 3. Preparing the v2 Dataset

Run:
```bash
python scripts/prepare_yolo_v2_dataset.py \
  --original dataset/oral-disease.yolov11 \
  --output dataset/oral-disease-v2.yolov11 \
  --review-csv dataset/hard-negative-candidates/review.csv \
  --negative-repeat 2
```

### Dataset Structure & Guarantees:
- **V2 Train**: Original `train` images + Nathan-approved negatives (repeated 2x with `rep0_neg_*` and `rep1_neg_*` unique names and 0-byte `.txt` labels).
- **V2 Valid**: **100% UNTOUCHED** copy of original `valid` split. Zero leakage.
- **V2 Test**: **100% UNTOUCHED** copy of original `test` split. Zero leakage.
- **Original Dataset**: Preserved without mutation.
- **Leakage Protection**: Computes SHA-256 hashes of all valid and test images. Aborts immediately if any approved negative matches a validation or test sample.

### Zip Dataset for Modal:
```powershell
Compress-Archive -Path dataset/oral-disease-v2.yolov11/* -DestinationPath dataset/oral-disease-v2.yolov11.zip -Force
```

---

## 4. Modal v2 Fine-Tuning Execution

Run:
```bash
modal run scripts/modal_train_yolo_v2.py
```

### Modal Architecture:
- App: `daantshaant-yolo-v2-training`
- Output Volume: `daantshaant-yolo-v2-output`
- Starting Model: Uploaded `/root/best_v1.pt` (starts from current `best.pt`, NOT `yolo11n.pt`)
- Dataset: Uploaded `/root/oral-disease-v2.zip`
- Hyperparameters:
  - `epochs = 12`
  - `optimizer = "AdamW"`
  - `lr0 = 0.0005` (conservative refinement rate)
  - `imgsz = 640`
  - `batch = 16`
  - `patience = 4`
  - `close_mosaic = 3`
  - `seed = 42`
- Outputs Saved to Volume:
  - `/output/oral-disease-yolo11n-v2/weights/best.pt`
  - `/output/oral-disease-yolo11n-v2/weights/last.pt`
  - `/output/oral-disease-yolo11n-v2/results.csv`
  - `/output/oral-disease-yolo11n-v2/confusion_matrix.png`

---

## 5. Downloading & Comparing v1 vs v2

### Step 1: Download weights from Modal volume
```bash
modal volume get daantshaant-yolo-v2-output oral-disease-yolo11n-v2/weights/best.pt services/teeth_analyzer/models/oral_disease/best_v2.pt
```

### Step 2: Run Calibration on Untouched Validation Split for Both Models
```bash
# Evaluate v1 baseline on untouched validation set
python scripts/evaluate_yolo_calibration.py \
  --model services/teeth_analyzer/models/oral_disease/best.pt \
  --dataset dataset/oral-disease.yolov11 \
  --split valid \
  --output docs/evaluation/yolo_v1_validation_calibration.md

# Evaluate v2 on the SAME untouched validation set
python scripts/evaluate_yolo_calibration.py \
  --model services/teeth_analyzer/models/oral_disease/best_v2.pt \
  --dataset dataset/oral-disease.yolov11 \
  --split valid \
  --output docs/evaluation/yolo_v2_validation_calibration.md
```

### Step 3: Run Direct Side-by-Side Model Comparison
```bash
python scripts/compare_yolo_models.py \
  --model-a services/teeth_analyzer/models/oral_disease/best.pt \
  --model-b services/teeth_analyzer/models/oral_disease/best_v2.pt \
  --dataset dataset/oral-disease.yolov11 \
  --split valid \
  --output docs/evaluation/yolo_v1_vs_v2_comparison.md
```

---

## 6. Model Activation in Production

Once v2 satisfies the acceptance criteria (reduced discoloration false positives without significant recall degradation):
Set in `.env`:
```env
YOLO_DENTAL_MODEL_PATH=services/teeth_analyzer/models/oral_disease/best_v2.pt
```
No Python code changes are required.
