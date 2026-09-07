# YOLO Small Healthy Dataset Audit (Phase 11B-3)

## 1. Dataset Overview

- **Dataset Name**: Dental Data Set (Roboflow Universe)
- **Local Location**: `dataset/Dental Data Set.yolov11/`
- **Workspace**: `nathan-asif-blm21`
- **Project**: `dental-data-set-tta0w`
- **Version**: `dataset`
- **Source URL**: `https://universe.roboflow.com/nathan-asif-blm21/dental-data-set-tta0w/dataset/dataset`
- **License**: CC BY 4.0 (documented in `data.yaml`, `README.dataset.txt`, and `README.roboflow.txt`)
- **Format**: YOLOv11 object detection
- **Pre-processing / Augmentation**: None applied

### Class Inventory (`data.yaml`)

The dataset contains 7 annotated classes:

| Class Index | Class Name | Category | DaantShaant Role |
|---|---|---|---|
| 0 | `8` | Ambiguous / Artifact | Disease / Non-healthy |
| 1 | `Calculus` | Pathology | Disease (Calculus / Tartar) |
| 2 | `CalculusCavities` | Compound Pathology | Disease |
| 3 | `CalculusHealthy Teeth` | Compound Label | Mixed / Disease |
| 4 | `Cavities` | Pathology | Disease (Caries / Cavities) |
| 5 | `Gingivitis` | Pathology | Disease (Gingivitis) |
| 6 | `Healthy Teeth` | Normal / Healthy | **Candidate Negative Class** |

### Split Counts

- **Train split**: 427 images (`train/images/`, 427 label files in `train/labels/`)
- **Valid split**: 0 images (referenced in `data.yaml` as `../valid/images`, but directory does not exist in local export)
- **Test split**: 0 images (referenced in `data.yaml` as `../test/images`, but directory does not exist in local export)
- **Total Images**: 427

---

## 2. Image Partitioning & Exclusion Logic

Per Phase 11B-3 safety requirements:
1. Only images whose bounding boxes correspond **ONLY to Class 6 (`Healthy Teeth`)** are eligible candidate negatives.
2. Any image with **disease bounding boxes** (even if healthy teeth are also annotated) is **strictly excluded** to prevent teaching disease features as clean negatives.
3. Disease-only images are excluded.

| Category | Image Count | % of Dataset | Action |
|---|---|---|---|
| **Healthy-Only** (Class 6 only) | **15** | 3.51% | **Evaluated for Hard Negatives & Controls** |
| **Mixed** (Class 6 + Disease boxes) | **144** | 33.72% | **Excluded** (Contains disease pathology) |
| **Disease-Only** (No Class 6 boxes) | **268** | 62.76% | **Excluded** (Contains disease pathology) |
| **Empty Label Files** | **0** | 0.00% | N/A |
| **Total** | **427** | 100.00% | |

### Total Box Counts in Dataset

- Class 0 (`8`): 1 box
- Class 1 (`Calculus`): 3,600 boxes
- Class 2 (`CalculusCavities`): 5 boxes
- Class 3 (`CalculusHealthy Teeth`): 4 boxes
- Class 4 (`Cavities`): 1,059 boxes
- Class 5 (`Gingivitis`): 249 boxes
- Class 6 (`Healthy Teeth`): 1,262 boxes
- **Total Bounding Boxes**: 6,180 boxes across 427 images

---

## 3. Detector Evaluation (`best.pt` at $\ge 0.30$)

The 15 healthy-only images were evaluated against DaantShaant's current YOLO detector (`services/teeth_analyzer/models/oral_disease/best.pt`).

### Summary of Findings

- **Healthy images that fooled `best.pt` ($\ge 0.30$)**: **9 images (60.0%)**
- **Healthy images producing 0 detections ($\ge 0.30$)**: **6 images (40.0%)**
- **Total False-Positive Detections**: **56 boxes** across the 9 false-positive images

### False-Positive Class Distribution

| Predicted Class | Normalized Finding | False-Positive Box Count | % of FP Boxes |
|---|---|---|---|
| `tooth discoloration` | `discoloration` | **54** | 96.43% |
| `caries` | `cavity_suspect` | **1** | 1.79% |
| `gingivitis` | `gingivitis_signs` | **1** | 1.79% |
| `calculus` | `tartar` | **0** | 0.00% |
| `ulcer` | `oral_ulcer` | **0** | 0.00% |
| **Total** | | **56** | 100.00% |

> **Key Clinical Observation**: Consistent with the Phase 11B-1 dataset audit (where tooth discoloration accounted for 42.1% of all training boxes in the original dataset), the current detector exhibits an extremely high false-positive prior on normal tooth enamel and lighting variations, falsely detecting tooth discoloration across 8 of the 9 false-positive healthy images. These 9 images are exceptionally valuable hard negatives to dampen this overprediction in YOLO v2.

---

## 4. Top-Ranked Candidates

Candidates are ranked by priority score:
$$\text{Score} = 2.0 \times \text{top\_conf} + \sum (\text{weight}_{\text{class}} \times \text{conf}_i^2)$$

Where weights reflect clinical severity: `tooth discoloration` = 1.5, `caries` = 1.4, `calculus` = 1.3, `gingivitis` = 1.1, `ulcer` = 1.0.

| Tile # | Filename | Candidate Type | Top Class | Top Conf | Box Count | Priority Score | Review Status |
|---|---|---|---|---|---|---|---|
| 1 | `(1608)_jpg.rf.dBFIgTOMBQtfsLiPC6K0.jpg` | `MODEL_FALSE_POSITIVE` | `tooth discoloration` | 0.7439 | 8 | 6.637 | UNREVIEWED |
| 2 | `(1644)_jpg.rf.O84JHugxsVx1cXiMwy3k.jpg` | `MODEL_FALSE_POSITIVE` | `tooth discoloration` | 0.7594 | 9 | 6.547 | UNREVIEWED |
| 3 | `05_jpg.rf.shelwwTHJvJhGnitn4NK.jpg` | `MODEL_FALSE_POSITIVE` | `tooth discoloration` | 0.7257 | 13 | 6.441 | UNREVIEWED |
| 4 | `03_jpg.rf.YMhZQDr9QNLKq98E5sOX.jpg` | `MODEL_FALSE_POSITIVE` | `tooth discoloration` | 0.7264 | 10 | 5.687 | UNREVIEWED |
| 5 | `(657)_jpg.rf.4pK6pFtINBqbSpOfSNUT.jpg` | `MODEL_FALSE_POSITIVE` | `tooth discoloration` | 0.7129 | 5 | 3.536 | UNREVIEWED |
| 6 | `(1648)_jpg.rf.Ftfi80X8Vpr7OdiBUZ81.jpg` | `MODEL_FALSE_POSITIVE` | `tooth discoloration` | 0.6466 | 6 | 3.163 | UNREVIEWED |
| 7 | `(656)_jpg.rf.AGuHCaWSUsa3zy8v2i5y.jpg` | `MODEL_FALSE_POSITIVE` | `tooth discoloration` | 0.4893 | 2 | 1.507 | UNREVIEWED |
| 8 | `(1609)_jpg.rf.ZKHjiSMLRlkb1k8YCNCH.jpg` | `MODEL_FALSE_POSITIVE` | `caries` | 0.4221 | 2 | 1.224 | UNREVIEWED |
| 9 | `(1621)_jpg.rf.t30c0PQSjHG7F0dsk1nF.jpg` | `MODEL_FALSE_POSITIVE` | `tooth discoloration` | 0.4147 | 1 | 1.087 | UNREVIEWED |
| 10 | `(64)_jpg.rf.Y6j2tFHQz5NxccZDU6mg.jpg` | `CLEAN_CONTROL` | `none` | 0.0000 | 0 | 0.000 | UNREVIEWED |
| 11 | `(655)_jpg.rf.xtXx8ThSdJK2l6Rmysj7.jpg` | `CLEAN_CONTROL` | `none` | 0.0000 | 0 | 0.000 | UNREVIEWED |
| 12 | `01_webp.rf.6MlJTFarFjIYgqC61kvV.webp` | `CLEAN_CONTROL` | `none` | 0.0000 | 0 | 0.000 | UNREVIEWED |
| 13 | `02_webp.rf.nXJUfRimNAiFQXI7XU6m.webp` | `CLEAN_CONTROL` | `none` | 0.0000 | 0 | 0.000 | UNREVIEWED |
| 14 | `04_jpg.rf.0dwx42DnajsFskD0e4TX.jpg` | `CLEAN_CONTROL` | `none` | 0.0000 | 0 | 0.000 | UNREVIEWED |
| 15 | `06_jpg.rf.YMzhZf8VMPAuLBAPol5u.jpg` | `CLEAN_CONTROL` | `none` | 0.0000 | 0 | 0.000 | UNREVIEWED |

---

## 5. Deduplication & Benchmark Isolation

1. **Internal Deduplication**:
   - All 15 candidate images have unique SHA-256 hashes (0 duplicates).
2. **Benchmark Split Isolation**:
   - SHA-256 hashes of all 15 images were checked against the entire benchmark dataset (`dataset/oral-disease.yolov11/valid/` and `dataset/oral-disease.yolov11/test/`).
   - **Zero overlap detected**: None of the external candidate images match any benchmark validation or test image.

---

## 6. Review Status Summary

- **Total Candidates Mined**: 15
  - `MODEL_FALSE_POSITIVE`: 9
  - `CLEAN_CONTROL`: 6
- **Current Status**:
  - `UNREVIEWED`: 15
  - `ACCEPT_NEGATIVE`: 0 (Pending Nathan review)
  - `REJECT_*`: 0

### Review Artifacts

- **Candidate CSV**: `dataset/healthy-negative-candidates/review.csv`
- **Metadata JSON**: `dataset/healthy-negative-candidates/candidates.json`
- **Visual Contact Sheet**: `dataset/healthy-negative-candidates/contact_sheet_01.jpg` (1 sheet, 15 populated tiles, 1440x1440 resolution)

---

## 7. Integration with YOLO v2 Dataset Preparation

`scripts/prepare_yolo_v2_dataset.py` has been updated to merge:
1. The 8 accepted hard negatives from `dataset/review_ai_recommended.csv` (Tiles 6, 7, 8, 15, 16, 25, 32, 36)
2. Any approved negatives from `dataset/healthy-negative-candidates/review.csv`

**Safety Rules Enforced**:
- Only rows marked `ACCEPT_NEGATIVE` enter the v2 `train` split.
- Accepted negative images receive **EMPTY (0-byte) `.txt` label files**.
- Benchmark `valid` and `test` splits remain **100% UNTOUCHED**.
- Hard-negative repetition (`--negative-repeat 2`) expands accepted negatives in `train` for balanced gradient signal.
