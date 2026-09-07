# DaantShaant Oral Disease YOLO v2 — Final Large Healthy-Negative Mining Audit

> Phase 11B-4 Final Report — September 2026.
> Evaluated against current production perception model `services/teeth_analyzer/models/oral_disease/best.pt`.

---

## 1. Executive Summary

Phase 11B-4 conducted large-scale healthy-negative mining against the external Roboflow dataset `Penyakit Gigi Skripsi.yolov11` (2,468 total images). The objective is to refine the YOLO oral pathology perception model (`best.pt`) by teaching v2 to output **no supported pathology** when observing healthy enamel, natural tooth shade variations, and normal anatomical features.

### Key Audit Metrics

| Metric | Count | Percentage / Note |
|---|---|---|
| **Total Source Images** | **2,468** | Train: 1,974 \| Valid: 247 \| Test: 247 |
| **Healthy-Only Annotated Images** | **338** | 13.70% of dataset (all boxes exclusively Class 2 `healthy`) |
| **Unique Healthy Images (SHA-256)** | **338** | 100% unique cryptographic hashes (0 exact duplicates) |
| **Excluded Mixed-Class Images** | **1,342** | Contained both `healthy` and disease boxes (`calculus`/`caries`) |
| **Excluded Disease-Only Images** | **788** | Exclusively disease boxes (`calculus`/`caries`) |
| **Empty Label Files** | **0** | All images have non-empty annotations |
| **Model False Positives ($\ge 0.30$)** | **129** | `candidate_type = MODEL_FALSE_POSITIVE` |
| **Clean Normal Controls ($0$ detections $\ge 0.30$)** | **209** | `candidate_type = CLEAN_CONTROL` |
| **Auto-Eligible Clean Controls** | **55** | Passed physical quality filters + non-duplicate primary variants |
| **Quality Rejections** | **49** | Severe blur ($\text{var} < 2.5$) or extreme overexposure ($> 35\%$) |
| **Near Duplicates (Perceptual dHash)** | **233** | Grouped into clusters to prevent single-mouth over-representation |
| **Manual Review FP Candidates** | **129** | Top 120 rendered onto 8 visual contact sheets |
| **Deterministic Control Audit Sample** | **50** | Rendered onto 4 visual contact sheets (`seed=42`) |
| **Existing Trusted Negatives** | **14** | 8 (empty-label mining) + 6 (Dental Data Set mining) |
| **Potential Final Negative Pool** | **198** | 14 existing + 129 false positives + 55 auto-eligible controls |

---

## 2. Source Dataset Verification & Local Metadata

- **Source Name**: Penyakit Gigi Skripsi (YOLOv11 format)
- **Roboflow Workspace**: `nathan-asif-blm21`
- **Roboflow Project**: `penyakit-gigi-skripsi-i77mi`
- **Roboflow Version**: `dataset`
- **Roboflow URL**: `https://universe.roboflow.com/nathan-asif-blm21/penyakit-gigi-skripsi-i77mi/dataset/dataset`
- **License**: CC BY 4.0
- **Source Classes ($nc=3$)**:
  - `0`: `calculus` (4,576 total source boxes)
  - `1`: `caries` (3,956 total source boxes)
  - `2`: `healthy` (6,510 total source boxes)
- **Local Directory Structure**:
  - `train`: 1,974 images / 1,974 label files
  - `valid`: 247 images / 247 label files
  - `test`: 247 images / 247 label files
- **Clinical Validation Status**: Provided by a Roboflow user; **not clinically validated**. Annotations are used strictly for offline negative candidate mining and control isolation under human review.

---

## 3. False-Positive Analysis on Healthy Teeth

Every single healthy-only image (338 images) was processed through `best.pt` with a minimum detection confidence of $0.30$.

### False-Positive Predictions by Pathology Class

| Predicted Class | FP Images | Total Detections | Clinical Implication |
|---|---|---|---|
| **Tooth Discoloration** | **104** | **834** | **Dominant Failure Mode**: Normal off-white enamel, lighting variations, and yellow undertones trigger widespread false discoloration boxes. |
| **Gingivitis** | **21** | **87** | Normal marginal gingival pinkness/translucency misidentified as inflammation. |
| **Caries** | **4** | **13** | Dark interdental crevices and shadowing misidentified as cavities. |
| **Calculus** | **0** | **0** | No false-positive calculus detections in this subset. |
| **Oral Ulcer** | **0** | **0** | No false-positive ulcer detections in this subset. |
| **Total** | **129** | **934** | 129 images produced 934 false-positive bounding boxes. |

This observation confirms the project's core perception challenge: **tooth discoloration represents 89.3% (834/934) of all false-positive boxes on healthy teeth**.

---

## 4. Deduplication & Perceptual Clustering

1. **Exact Cryptographic Duplicates**:
   - SHA-256 calculation across all 338 images identified **0 exact duplicate image pairs** (all 338 are distinct files).
2. **Perceptual Near-Duplicates**:
   - 64-bit difference hashing (`dHash`) with a Hamming distance threshold $\le 5$ identified **233 near-duplicate image variants** representing multiple captures, angle variations, or burst frames of the same oral cavity.
   - For every cluster, the first instance is retained as `PRIMARY` (`duplicate_status = PRIMARY`). Subsequent captures are labeled `duplicate_status = NEAR_DUPLICATE` and assigned the identical `duplicate_group` ID.
   - In the clean control pool, near duplicates are excluded from automatic inclusion (`review_status = REJECT_NEAR_DUPLICATE`) to prevent any single subject from dominating the background prior.

---

## 5. Physical Image Quality Filtering

Per Section 9 rules, basic quality metrics were evaluated:
- **Corrupt / Unreadable**: 0 images
- **Tiny Resolution ($< 128\times 128$)**: 0 images (dataset resolutions range from $540\times 746$ to $2,186\times 1,734$)
- **Severe Blur**: 41 images flagged with Laplacian variance $< 2.5$
- **Extreme Overexposure**: 8 images flagged with $> 35\%$ pixels exceeding 250 in luminance
- **Total Quality Rejections**: **49 images** marked `quality_status != 'PASS'` and excluded from automatic negative eligibility.

---

## 6. Strict Benchmark Isolation & Leakage Verification

All 338 candidate images were hashed with SHA-256 and compared against the benchmark `oral-disease.yolov11` splits:
- **Validation Split (1,070 images)**: **0 matches** ($\checkmark$ ZERO leakage)
- **Test Split (1,070 images)**: **0 matches** ($\checkmark$ ZERO leakage)
- **Train Split (8,558 images)**: 0 matches with Penyakit Gigi Skripsi (external dataset completely disjoint from original oral-disease benchmark).

---

## 7. Artifacts Generated for Review

All candidate files are stored in `dataset/final-healthy-negative-candidates/`:
1. **`review.csv`** (345 KB): 338 rows with complete priority scores, candidate types, bounding box coordinates, quality statuses, duplicate groups, and review statuses.
2. **`candidates.json`** (1.05 MB): Machine-readable metadata and detection list.
3. **`audit.json`** (1.23 KB): Statistical summary.
4. **False-Positive Contact Sheets** (`contact_sheet_fp_01.jpg` to `contact_sheet_fp_08.jpg`):
   - 8 sheets displaying the top 120 false-positive candidates in 4x4 grids (16 tiles per sheet).
   - Sorted by priority: tooth discoloration $\rightarrow$ caries $\rightarrow$ calculus $\rightarrow$ gingivitis $\rightarrow$ ulcer, then by confidence and coverage.
5. **Control Audit Contact Sheets** (`contact_sheet_control_audit_01.jpg` to `contact_sheet_control_audit_04.jpg`):
   - 4 sheets displaying a deterministic 50-image random audit sample of `AUTO_ELIGIBLE_CONTROL` images (`seed=42`).

---

## 8. Final Training Pool & Class Balance

- **Current Trusted Negatives**:
  - 8 approved from empty-label mining (`dataset/review_ai_recommended.csv`)
  - 6 approved from Dental Data Set mining (`dataset/review_healthy_ai_recommended.csv`)
  - Subtotal: **14 unique approved negatives**
- **Potential New Additions**:
  - 129 false-positive candidates pending Nathan manual review in `review.csv`
  - 55 auto-eligible controls eligible pending 50-image sample audit
- **Final Potential Unique Negatives**: **198 images**
- **V2 Training Balance**:
  - Original train count: 8,558 images
  - With repeat factor $N=2$: $198 \times 2 = 396$ instances $\rightarrow$ **4.42%** of v2 train ($396 / 8,954$)
  - With repeat factor $N=1$: $198 \times 1 = 198$ instances $\rightarrow$ **2.26%** of v2 train ($198 / 8,756$)
  - Well within the target safety bound of $\le 15-18\%$.
