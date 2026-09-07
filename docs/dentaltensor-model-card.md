# DentalTensor Vision v1.0

Developed by **Nathan Asif**

---

## Overview

**DentalTensor** is a custom computer-vision model for screening visible oral pathology patterns from standard RGB mouth photographs.

DentalTensor was conceived while Nathan Asif was leading and building **DaantShaant** for the Alibaba Cloud Bano Qabil Hackathon 2026, after identifying the fundamental need for a dedicated, local intraoral vision engine rather than relying exclusively on cloud multimodal LLMs for low-level visual perception.

**DaantShaant** is the first production-style application integration consuming the DentalTensor vision model.

DentalTensor is an independent, reusable perception asset:
- **DentalTensor**: The core computer-vision model and perception engine.
- **DaantShaant**: The end-to-end oral-health screening and care-navigation platform consuming DentalTensor outputs.

---

## Architecture

- **Base Architecture**: Ultralytics YOLO11n (nano object detection network)
- **Task**: Multi-class bounding-box object detection & spatial aggregation
- **Inference Mode**: Local edge/server inference (CPU-capable, zero mandatory GPU/cloud requirement at runtime)
- **Weights**: Custom fine-tuned oral pathology weights (`dentaltensor_nathan_asif_v1.pt`)

### Model Size & Complexity
Verified architectural metadata:
- **Layers**: 101 layers
- **Parameters**: 2,583,127 parameters
- **GFLOPs**: 6.4 GFLOPs (at 640×640 input resolution)

---

## Supported Visual Classes

DentalTensor Vision detects 5 visual oral condition categories:

| Model Class Name | Normalized Clinical Code | Clinical Description |
|---|---|---|
| `calculus` | `tartar` | Visible supragingival / subgingival dental calculus & tartar deposits |
| `caries` | `cavity_suspect` | Visible enamel cavitation / decay lesions |
| `gingivitis` | `gingivitis_signs` | Visible marginal gingival erythema, swelling, or inflammation |
| `tooth discoloration` | `discoloration` | Visible extrinsic or intrinsic tooth staining / chromatic variation |
| `ulcer` | `oral_ulcer` | Visible mucosal aphthous / ulcerative lesion or sore |

### Clinical Safety & Separation Rules
- **Discoloration Isolation**: Tooth discoloration is **never** mapped or aggregated into calculus/tartar or cavity.
- **Dual Presentation**: Concurrent calculus and discoloration detections on the same dentition are strictly preserved as separate findings.
- **Spatial Aggregation**: Detections across bounding boxes are deterministically aggregated into `localized`, `multiple`, or `generalized` distributions with horizontal third coverage tracking.

---

## Development Datasets

The development and refinement of DentalTensor utilized three audited visual datasets:

1. **`oral-disease.yolov11`** (Main Pathology Dataset)
   - **Total Images**: 10,698 images (train: 8,558, valid: 1,070, test: 1,070)
   - **Annotations**: 62,720 labeled pathology bounding boxes
   - **True Negatives**: 570 empty-label control images (5.33% of dataset)
   - **License**: CC BY 4.0 (Roboflow Universe: `di-qidb9/oral-disease-tabrb`)

2. **`Dental Data Set.yolov11`** (Auxiliary Healthy-Control / Hard-Negative Source)
   - **Total Images**: 427 images in train split
   - **License**: CC BY 4.0 (Roboflow Universe: `nathan-asif-blm21/dental-data-set-tta0w`)
   - **Role**: Source for mining healthy-only images that trigger false positives in v1 baseline.

3. **`Penyakit Gigi Skripsi.yolov11`** (Auxiliary Healthy-Control / Hard-Negative Source)
   - **Total Images**: 2,468 images across train (1,974), valid (247), test (247)
   - **License**: CC BY 4.0 (Roboflow Universe: `nathan-asif-blm21/penyakit-gigi-skripsi-i77mi`)
   - **Role**: Source for large healthy-negative pool mining.

### Curation & Leakage Protection Strategy
> [!IMPORTANT]
> **No Blind Insertion**: Auxiliary datasets were **not** blindly added to the training set. Mixed annotations (disease + healthy) and poor quality images were systematically excluded. Only manually reviewed, approved hard negatives were incorporated.
>
> **Strict Benchmark Isolation**: Benchmark `valid` (1,070 images) and `test` (1,070 images) splits from `oral-disease.yolov11` remained 100% UNTOUCHED throughout all training iterations. Cryptographic SHA-256 assertions strictly prevented any evaluation data leakage.

- **Manually Approved Unique Hard Negatives**: 27 verified healthy control images
- **Effective Hard-Negative Instances**: 108 (with 4× balanced repetition)
- **Final v2 Training Set**: 8,666 images
- **Untouched Validation Set**: 1,070 images
- **Untouched Test Set**: 1,070 images

---

## Training Configuration

DentalTensor Vision v1.0 was trained via transfer learning from the initial oral-disease checkpoint using cloud infrastructure:

- **Hardware**: NVIDIA A10G GPU (24GB VRAM) via Modal serverless infrastructure
- **Base Checkpoint**: Initial oral pathology checkpoint (`best_v1.pt`)
- **Image Resolution**: 640×640 (`imgsz=640`)
- **Batch Size**: 16
- **Epochs**: 12 epochs
- **Optimizer**: AdamW (`lr0=0.0005`)
- **Close Mosaic**: 3 epochs
- **Random Seed**: 42 (fully reproducible)
- **Output Artifact**: `dentaltensor_nathan_asif_v1.pt` (byte-for-byte identical to `best_v2.pt`)

---

## Final Engineering Thresholds

Calibrated confidence cutoffs balance sensitivity against false-positive suppression on consumer intraoral photographs:

| Condition Class | Normalized Code | Calibrated Threshold | Operational Rationale |
|---|---|---|---|
| `calculus` | `tartar` | **`0.35`** | High sensitivity for detecting visible supragingival calculus deposits |
| `caries` | `cavity_suspect` | **`0.55`** | Conservative threshold to reduce false alerts on deep occlusal fissures |
| `gingivitis` | `gingivitis_signs` | **`0.50`** | Balanced threshold for visible gingival erythema |
| `tooth discoloration` | `discoloration` | **`0.65`** | High threshold to prevent natural tooth shade variation from triggering alerts |
| `ulcer` | `oral_ulcer` | **`0.65`** | Specific threshold for distinct mucosal ulcerations |
| **Global Fallback** | *Any / Unknown* | **`0.50`** | Standard baseline threshold |

---

## V2 Calibration Results

Calibration evaluations against untouched validation benchmarks confirmed key performance improvements:

1. **Suppression of Discoloration False Positives**:
   - V1 baseline suffered from a high false-positive prior on normal teeth (tooth discoloration accounted for 42.1% of all bounding boxes in the training distribution).
   - V2 fine-tuning with audited healthy hard negatives and the elevated 0.65 threshold significantly reduced false-positive discoloration predictions on clean dentition while preserving sensitivity on true staining.
2. **Benchmark Preservation**:
   - Validated on 1,070 untouched validation and 1,070 test images with zero data leakage.
   - Preserved caries, calculus, gingivitis, and ulcer detection precision across standard intraoral viewing angles.
3. **Engineering Benchmark Status**:
   - These results represent engineering benchmark metrics on intraoral photograph datasets and do **not** constitute clinical trials or medical device certification.

---

## Known Limitations

- **Screening Support Only**: DentalTensor Vision is an awareness and preliminary screening tool. It does not replace a physical clinical examination, dental probing, or dental radiographs (bitewing/periapical X-rays).
- **Subgingival & Interproximal Pathology**: Visible-spectrum RGB imaging cannot detect subgingival calculus, interproximal caries between tight contact points, or internal root pathologies.
- **Lighting and Framing Sensitivity**: Variable smartphone flash lighting, motion blur, saliva reflections, and severe underexposure can influence detection confidence.
- **Visual Similarity**: Natural anatomical variations (such as developmental grooves, amiloradicular grooves, or benign racial pigmentation) may visually resemble pathology under certain illumination conditions.

---

## Production Integration: DaantShaant Pipeline

In DaantShaant, DentalTensor Vision serves as the foundational perception engine:

```text
DaantShaant Oral Scan (Snapshot / Upload / Live WebSocket)
        ↓
Semantic Dental Relevance Gate (Relevance / Retake / Reject)
        ↓
Mechanical Quality Gate (OpenCV Preprocessing)
        ↓
DentalTensor Vision v1.0 (dentaltensor_nathan_asif_v1.pt)
        ↓
Spatial Aggregation & Normalized Evidence
        ↓
Deterministic Clinical Triage (Rules & Urgency Classification)
        ↓
Patient-Friendly Clinical Report (Structured LLM Generation)
```

---

## Ownership & Attribution

- **Product / Model Family**: DentalTensor
- **Full Model Name**: DentalTensor Vision v1.0
- **Developer & Author**: **Nathan Asif**
- **Inception & Provenance**: Conceived, engineered, fine-tuned, calibrated, and productized by Nathan Asif while leading and building DaantShaant for the Alibaba Cloud Bano Qabil Hackathon 2026.
- **Primary Product Integration**: DaantShaant
