# DaantShaant YOLO Dataset Audit Report

> Generated as part of Phase 11B-1: YOLO Detector Calibration + Hard-Negative Preparation.

## Executive Summary

- **Total Dataset Images**: 10,698
- **Total Labeled Bounding Boxes**: 62,720
- **Total True Negative (Empty Label / Healthy) Images**: **570** (5.33%)

> [!NOTE]
> **570 TRUE NEGATIVE (EMPTY LABEL) IMAGES FOUND (5.33% of dataset).**
> While ~5.3% of images lack bounding boxes, the vast majority (94.7%) contain disease annotations.
> Crucially, common clinical variations (clean professionally treated teeth, mild yellow enamel,
> dark interdental shadows, and phone flash reflections) are under-represented as negatives,
> leading to false positives like tooth discoloration at ~0.60 on healthy/treated dentition.
> Hard-negative collection and v2 dataset preparation remain critically necessary.

## Split Breakdown

| Split | Total Images | Positive Images | True Negatives (Empty) | Total Boxes | Avg Boxes/Img | Multi-Class Imgs |
|---|---|---|---|---|---|---|
| `train` | 8,558 | 8,101 | **457** | 49,781 | 5.82 | 2,635 |
| `valid` | 1,070 | 1,007 | **63** | 6,362 | 5.95 | 316 |
| `test` | 1,070 | 1,020 | **50** | 6,577 | 6.15 | 354 |

## Class Distribution & Imbalance (Combined Dataset)

| Class ID | Class Name | Normalized Code | Total Boxes | % of All Boxes | Images Containing Class |
|---|---|---|---|---|---|
| 0 | `calculus` | `tartar` | 8,634 | 13.8% | 2,164 |
| 1 | `caries` | `cavity_suspect` | 13,323 | 21.2% | 4,027 |
| 2 | `gingivitis` | `gingivitis_signs` | 10,183 | 16.2% | 2,037 |
| 3 | `tooth discoloration` | `discoloration` | 26,424 | 42.1% | 4,143 |
| 4 | `ulcer` | `oral_ulcer` | 4,156 | 6.6% | 2,251 |

## Bounding Box Size Distribution

| Split | Small (<1% area) | Medium (1–5% area) | Large (>5% area) |
|---|---|---|---|
| `train` | 12,961 | 32,448 | 4,372 |
| `valid` | 1,730 | 4,118 | 514 |
| `test` | 1,903 | 4,161 | 513 |

## Key Insights for Calibration & v2 Training

1. **Limited Negative Samples (570 / 5.33%)**: Negative images exist but are severely outnumbered (18:1 ratio of positive to negative).
2. **Tooth Discoloration Dominance**: Discoloration accounts for 26,424 boxes (42.1% of all boxes in dataset), heavily skewing model priors toward predicting discoloration whenever yellow/brown pixels appear.
3. **Multi-Class Co-occurrence**: Over 2,600 training images feature multiple co-occurring conditions, explaining cross-talk between calculus and discoloration.
4. **Hard-Negative Need**: Adding dedicated hard-negative images (clean treated teeth, flash, shadows, harmless stains) with empty label files will suppress false positive triggers without altering positive pathology features.
