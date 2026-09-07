# DaantShaant YOLO Model Calibration Report

> Generated as part of Phase 11B-1: YOLO Detector Calibration + Hard-Negative Preparation.

- **Model Path**: `services\teeth_analyzer\models\oral_disease\best_v2.pt`
- **Split Evaluated**: `valid` (1070 images)

## Threshold Recommendations (Engineering Calibration)

> [!IMPORTANT]
> These are engineering calibration recommendations. Threshold configurations should be
> verified on the manual acceptance test set before production deployment.

| Class Name | Current Default | Recommended Best F1 | Precision-Oriented (Low FP) | Recall-Oriented (High Sens) |
|---|---|---|---|---|
| `calculus` | `0.50` | **`0.30`** | `0.35` | `0.30` |
| `caries` | `0.50` | **`0.30`** | `0.55` | `0.30` |
| `gingivitis` | `0.50` | **`0.30`** | `0.50` | `0.30` |
| `tooth discoloration` | `0.50` | **`0.30`** | `0.70` | `0.30` |
| `ulcer` | `0.50` | **`0.30`** | `0.65` | `0.30` |

## Tooth Discoloration Threshold Curve

| Threshold | Precision | Recall | F1 Score | FP Count | FN Count |
|---|---|---|---|---|---|
| `0.30` | 0.7006 | 0.8043 | 0.7489 | 943 | 537 |
| `0.35` | 0.7222 | 0.7711 | 0.7459 | 814 | 628 |
| `0.40` | 0.7466 | 0.7431 | 0.7448 | 692 | 705 |
| `0.45` | 0.7696 | 0.7012 | 0.7338 | 576 | 820 |
| `0.50` | 0.7980 | 0.6680 | 0.7272 | 464 | 911 |
| `0.55` | 0.8261 | 0.6199 | 0.7083 | 358 | 1,043 |
| `0.60` | 0.8564 | 0.5627 | 0.6791 | 259 | 1,200 |
| `0.65` | 0.8827 | 0.4989 | 0.6375 | 182 | 1,375 |
| `0.70` | 0.9077 | 0.4231 | 0.5772 | 118 | 1,583 |
| `0.75` | 0.9357 | 0.3236 | 0.4809 | 61 | 1,856 |
| `0.80` | 0.9645 | 0.2081 | 0.3423 | 21 | 2,173 |

## Calculus (Tartar) Threshold Curve

| Threshold | Precision | Recall | F1 Score | FP Count | FN Count |
|---|---|---|---|---|---|
| `0.30` | 0.6898 | 0.4408 | 0.5379 | 174 | 491 |
| `0.35` | 0.7181 | 0.4032 | 0.5164 | 139 | 524 |
| `0.40` | 0.7630 | 0.3519 | 0.4817 | 96 | 569 |
| `0.45` | 0.8062 | 0.2984 | 0.4356 | 63 | 616 |
| `0.50` | 0.8284 | 0.2528 | 0.3874 | 46 | 656 |
| `0.55` | 0.8592 | 0.2084 | 0.3355 | 30 | 695 |
| `0.60` | 0.8772 | 0.1708 | 0.2860 | 21 | 728 |
| `0.65` | 0.8810 | 0.1264 | 0.2211 | 15 | 767 |
| `0.70` | 0.8684 | 0.0752 | 0.1384 | 10 | 812 |
| `0.75` | 0.8780 | 0.0410 | 0.0783 | 5 | 842 |
| `0.80` | 0.8667 | 0.0148 | 0.0291 | 2 | 865 |

## Calculus <-> Tooth Discoloration Cross-Confusion

| Threshold | Calculus Pred on Discoloration GT | Discoloration Pred on Calculus GT |
|---|---|---|
| `0.30` | 9 | 26 |
| `0.35` | 7 | 19 |
| `0.40` | 4 | 16 |
| `0.45` | 2 | 15 |
| `0.50` | 0 | 13 |
| `0.55` | 0 | 11 |
| `0.60` | 0 | 9 |
| `0.65` | 0 | 4 |
| `0.70` | 0 | 2 |
| `0.75` | 0 | 1 |
| `0.80` | 0 | 0 |
