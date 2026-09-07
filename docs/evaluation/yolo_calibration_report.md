# DaantShaant YOLO Model Calibration Report

> Generated as part of Phase 11B-1: YOLO Detector Calibration + Hard-Negative Preparation.

- **Model Path**: `services\teeth_analyzer\models\oral_disease\best.pt`
- **Split Evaluated**: `valid` (1070 images)

## Threshold Recommendations (Engineering Calibration)

> [!IMPORTANT]
> These are engineering calibration recommendations. Threshold configurations should be
> verified on the manual acceptance test set before production deployment.

| Class Name | Current Default | Recommended Best F1 | Precision-Oriented (Low FP) | Recall-Oriented (High Sens) |
|---|---|---|---|---|
| `calculus` | `0.50` | **`0.30`** | `0.30` | `0.30` |
| `caries` | `0.50` | **`0.30`** | `0.50` | `0.30` |
| `gingivitis` | `0.50` | **`0.30`** | `0.50` | `0.30` |
| `tooth discoloration` | `0.50` | **`0.30`** | `0.65` | `0.30` |
| `ulcer` | `0.50` | **`0.30`** | `0.70` | `0.30` |

## Tooth Discoloration Threshold Curve

| Threshold | Precision | Recall | F1 Score | FP Count | FN Count |
|---|---|---|---|---|---|
| `0.30` | 0.6833 | 0.8076 | 0.7403 | 1,027 | 528 |
| `0.35` | 0.7071 | 0.7708 | 0.7376 | 876 | 629 |
| `0.40` | 0.7335 | 0.7310 | 0.7323 | 729 | 738 |
| `0.45` | 0.7614 | 0.6990 | 0.7289 | 601 | 826 |
| `0.50` | 0.7833 | 0.6545 | 0.7131 | 497 | 948 |
| `0.55` | 0.8152 | 0.6188 | 0.7035 | 385 | 1,046 |
| `0.60` | 0.8390 | 0.5528 | 0.6665 | 291 | 1,227 |
| `0.65` | 0.8705 | 0.4825 | 0.6209 | 197 | 1,420 |
| `0.70` | 0.9067 | 0.3932 | 0.5486 | 111 | 1,665 |
| `0.75` | 0.9362 | 0.2890 | 0.4417 | 54 | 1,951 |
| `0.80` | 0.9727 | 0.1687 | 0.2876 | 13 | 2,281 |

## Calculus (Tartar) Threshold Curve

| Threshold | Precision | Recall | F1 Score | FP Count | FN Count |
|---|---|---|---|---|---|
| `0.30` | 0.6505 | 0.4282 | 0.5165 | 202 | 502 |
| `0.35` | 0.7060 | 0.3884 | 0.5011 | 142 | 537 |
| `0.40` | 0.7401 | 0.3405 | 0.4665 | 105 | 579 |
| `0.45` | 0.7638 | 0.2836 | 0.4136 | 77 | 629 |
| `0.50` | 0.8000 | 0.2415 | 0.3710 | 53 | 666 |
| `0.55` | 0.8404 | 0.2039 | 0.3281 | 34 | 699 |
| `0.60` | 0.8693 | 0.1743 | 0.2903 | 23 | 725 |
| `0.65` | 0.8730 | 0.1253 | 0.2191 | 16 | 768 |
| `0.70` | 0.8718 | 0.0774 | 0.1423 | 10 | 810 |
| `0.75` | 0.8222 | 0.0421 | 0.0802 | 8 | 841 |
| `0.80` | 0.7917 | 0.0216 | 0.0421 | 5 | 859 |

## Calculus <-> Tooth Discoloration Cross-Confusion

| Threshold | Calculus Pred on Discoloration GT | Discoloration Pred on Calculus GT |
|---|---|---|
| `0.30` | 18 | 27 |
| `0.35` | 10 | 24 |
| `0.40` | 5 | 19 |
| `0.45` | 4 | 15 |
| `0.50` | 1 | 15 |
| `0.55` | 1 | 11 |
| `0.60` | 0 | 7 |
| `0.65` | 0 | 3 |
| `0.70` | 0 | 1 |
| `0.75` | 0 | 0 |
| `0.80` | 0 | 0 |
