"""Offline YOLO Detector Calibration & Threshold Analysis (Phase 11B-1).

Evaluates a local YOLO model binary (e.g., best.pt) against validation or test splits.
Sweeps confidence thresholds from 0.30 to 0.80 and computes:
- Per-class Precision, Recall, F1, False Positives, False Negatives
- Calculus <-> Tooth Discoloration cross-class confusion
- Recommended thresholds: Best F1, Precision-oriented, Recall-oriented

DOES NOT call external APIs.
DOES NOT automatically modify production configuration.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
import os
from pathlib import Path
import sys

CLASS_NAMES = {
    0: "calculus",
    1: "caries",
    2: "gingivitis",
    3: "tooth discoloration",
    4: "ulcer",
}

NORMALIZED_NAMES = {
    "calculus": "tartar",
    "caries": "cavity_suspect",
    "gingivitis": "gingivitis_signs",
    "tooth discoloration": "discoloration",
    "ulcer": "oral_ulcer",
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_THRESHOLDS = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]


def calculate_iou(boxA: tuple[float, float, float, float], boxB: tuple[float, float, float, float]) -> float:
    """Calculate IoU between two boxes in xyxy format."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    inter_w = max(0.0, xB - xA)
    inter_h = max(0.0, yB - yA)
    inter_area = inter_w * inter_h

    areaA = max(0.0, boxA[2] - boxA[0]) * max(0.0, boxA[3] - boxA[1])
    areaB = max(0.0, boxB[2] - boxB[0]) * max(0.0, boxB[3] - boxB[1])
    union_area = areaA + areaB - inter_area

    if union_area <= 0.0:
        return 0.0
    return inter_area / union_area


def yolo_to_xyxy(x_c: float, y_c: float, w: float, h: float) -> tuple[float, float, float, float]:
    """Convert normalized YOLO format (center_x, center_y, width, height) to normalized xyxy."""
    x1 = max(0.0, x_c - w / 2.0)
    y1 = max(0.0, y_c - h / 2.0)
    x2 = min(1.0, x_c + w / 2.0)
    y2 = min(1.0, y_c + h / 2.0)
    return (x1, y1, x2, y2)


def load_ground_truth(labels_dir: Path) -> dict[str, list[tuple[int, tuple[float, float, float, float]]]]:
    """Loads all ground truth boxes per image stem."""
    gt_map = defaultdict(list)
    if not labels_dir.exists():
        return gt_map

    with os.scandir(labels_dir) as it:
        for entry in it:
            if entry.is_file() and entry.name.endswith(".txt"):
                stem = entry.name[:-4]
                try:
                    with open(entry.path, "r", encoding="utf-8") as f:
                        for line in f:
                            parts = line.strip().split()
                            if len(parts) >= 5:
                                cls_id = int(parts[0])
                                xc, yc, w, h = map(float, parts[1:5])
                                gt_map[stem].append((cls_id, yolo_to_xyxy(xc, yc, w, h)))
                except Exception:
                    continue
    return gt_map


def evaluate_split(
    model_path: Path,
    dataset_root: Path,
    split_name: str = "valid",
    iou_thresh: float = 0.50,
    thresholds: list[float] | None = None,
    max_images: int | None = None,
) -> dict:
    threshold_list = thresholds or DEFAULT_THRESHOLDS
    split_dir = dataset_root / split_name
    images_dir = split_dir / "images" if (split_dir / "images").exists() else split_dir
    labels_dir = split_dir / "labels" if (split_dir / "labels").exists() else split_dir

    gt_data = load_ground_truth(labels_dir)

    try:
        from ultralytics import YOLO
    except ImportError:
        print("[!] Ultralytics package is not installed in the current environment.", file=sys.stderr)
        print("    Running offline calibration structure report / contract schema.", file=sys.stderr)
        return {
            "status": "ultralytics_missing",
            "model_path": str(model_path),
            "split": split_name,
            "error": "Ultralytics package is not installed in current environment. Run in an environment with ultralytics.",
        }

    print(f"Loading YOLO model from: {model_path.resolve()} ...", flush=True)
    model = YOLO(str(model_path))

    image_paths = []
    with os.scandir(images_dir) as it:
        for entry in it:
            if entry.is_file() and os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
                image_paths.append(Path(entry.path))
                if max_images and len(image_paths) >= max_images:
                    break

    print(f"Running inference on {len(image_paths)} {split_name} images at minimum conf={min(threshold_list):.2f} ...", flush=True)

    # Collect predictions for all images once at min threshold
    raw_predictions: dict[str, list[tuple[int, float, tuple[float, float, float, float]]]] = defaultdict(list)

    for idx, img_p in enumerate(image_paths):
        stem = img_p.stem
        try:
            res = model.predict(source=str(img_p), conf=min(threshold_list), iou=0.45, verbose=False)
            if res and len(res) > 0:
                boxes = res[0].boxes
                if boxes is not None and len(boxes) > 0:
                    xyxy_norm = boxes.xyxyn.cpu().numpy()
                    confs = boxes.conf.cpu().numpy()
                    classes = boxes.cls.cpu().numpy()
                    for i in range(len(classes)):
                        c_id = int(classes[i])
                        conf = float(confs[i])
                        box = tuple(map(float, xyxy_norm[i]))
                        raw_predictions[stem].append((c_id, conf, box))
        except Exception as exc:
            continue

        if (idx + 1) % 250 == 0:
            print(f"  Processed {idx + 1}/{len(image_paths)} images ...", flush=True)

    # Evaluate across all thresholds
    metrics_by_threshold = {}
    confusion_by_threshold = {}

    for t in threshold_list:
        tp = defaultdict(int)
        fp = defaultdict(int)
        fn = defaultdict(int)
        calculus_pred_discoloration_gt = 0
        discoloration_pred_calculus_gt = 0

        for img_p in image_paths:
            stem = img_p.stem
            gts = list(gt_data.get(stem, []))
            preds = [p for p in raw_predictions.get(stem, []) if p[1] >= t]

            # Match predictions to ground truth
            gt_matched = [False] * len(gts)
            for p_cls, p_conf, p_box in sorted(preds, key=lambda x: -x[1]):
                best_iou = 0.0
                best_gt_idx = -1
                for g_idx, (g_cls, g_box) in enumerate(gts):
                    if not gt_matched[g_idx] and p_cls == g_cls:
                        iou = calculate_iou(p_box, g_box)
                        if iou > best_iou:
                            best_iou = iou
                            best_gt_idx = g_idx

                if best_gt_idx >= 0 and best_iou >= iou_thresh:
                    tp[p_cls] += 1
                    gt_matched[best_gt_idx] = True
                else:
                    fp[p_cls] += 1
                    # Check cross-class confusion for calculus (0) and discoloration (3)
                    for g_idx, (g_cls, g_box) in enumerate(gts):
                        cross_iou = calculate_iou(p_box, g_box)
                        if cross_iou >= 0.30:
                            if p_cls == 0 and g_cls == 3:
                                calculus_pred_discoloration_gt += 1
                            elif p_cls == 3 and g_cls == 0:
                                discoloration_pred_calculus_gt += 1

            for g_idx, matched in enumerate(gt_matched):
                if not matched:
                    fn[gts[g_idx][0]] += 1

        per_class = {}
        for c_id, c_name in CLASS_NAMES.items():
            t_pos = tp[c_id]
            f_pos = fp[c_id]
            f_neg = fn[c_id]
            prec = t_pos / (t_pos + f_pos) if (t_pos + f_pos) > 0 else 0.0
            rec = t_pos / (t_pos + f_neg) if (t_pos + f_neg) > 0 else 0.0
            f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
            per_class[c_name] = {
                "tp": t_pos,
                "fp": f_pos,
                "fn": f_neg,
                "precision": round(prec, 4),
                "recall": round(rec, 4),
                "f1": round(f1, 4),
            }

        metrics_by_threshold[f"{t:.2f}"] = per_class
        confusion_by_threshold[f"{t:.2f}"] = {
            "calculus_pred_discoloration_gt": calculus_pred_discoloration_gt,
            "discoloration_pred_calculus_gt": discoloration_pred_calculus_gt,
        }

    # Derive recommendations per class
    recommendations = {}
    for c_id, c_name in CLASS_NAMES.items():
        best_f1_t = 0.50
        best_f1_val = 0.0
        prec_oriented_t = 0.50
        rec_oriented_t = 0.50

        for t_str, classes_m in metrics_by_threshold.items():
            t_val = float(t_str)
            m = classes_m[c_name]
            if m["f1"] > best_f1_val:
                best_f1_val = m["f1"]
                best_f1_t = t_val

        # Precision-oriented: highest threshold with recall >= 0.40
        prec_candidates = [
            (float(t_str), classes_m[c_name]["precision"])
            for t_str, classes_m in metrics_by_threshold.items()
            if classes_m[c_name]["recall"] >= 0.40
        ]
        if prec_candidates:
            prec_oriented_t = max(prec_candidates, key=lambda x: x[1])[0]

        # Recall-oriented: lowest threshold with precision >= 0.40
        rec_candidates = [
            (float(t_str), classes_m[c_name]["recall"])
            for t_str, classes_m in metrics_by_threshold.items()
            if classes_m[c_name]["precision"] >= 0.40
        ]
        if rec_candidates:
            rec_oriented_t = max(rec_candidates, key=lambda x: x[1])[0]

        recommendations[c_name] = {
            "best_f1_threshold": best_f1_t,
            "precision_oriented_threshold": prec_oriented_t,
            "recall_oriented_threshold": rec_oriented_t,
            "current_fallback": 0.50,
        }

    return {
        "status": "success",
        "model_path": str(model_path),
        "split": split_name,
        "images_evaluated": len(image_paths),
        "metrics_by_threshold": metrics_by_threshold,
        "confusion_by_threshold": confusion_by_threshold,
        "recommendations": recommendations,
    }


def generate_calibration_markdown(results: dict) -> str:
    md = []
    md.append("# DaantShaant YOLO Model Calibration Report")
    md.append("")
    md.append("> Generated as part of Phase 11B-1: YOLO Detector Calibration + Hard-Negative Preparation.")
    md.append("")

    if results.get("status") != "success":
        md.append(f"> [!WARNING]\n> {results.get('error', 'Evaluation could not be completed.')}\n")
        return "\n".join(md)

    md.append(f"- **Model Path**: `{results['model_path']}`")
    md.append(f"- **Split Evaluated**: `{results['split']}` ({results['images_evaluated']} images)")
    md.append("")
    md.append("## Threshold Recommendations (Engineering Calibration)")
    md.append("")
    md.append("> [!IMPORTANT]")
    md.append("> These are engineering calibration recommendations. Threshold configurations should be")
    md.append("> verified on the manual acceptance test set before production deployment.")
    md.append("")
    md.append("| Class Name | Current Default | Recommended Best F1 | Precision-Oriented (Low FP) | Recall-Oriented (High Sens) |")
    md.append("|---|---|---|---|---|")
    for c_name, rec in results["recommendations"].items():
        md.append(
            f"| `{c_name}` | `{rec['current_fallback']:.2f}` | "
            f"**`{rec['best_f1_threshold']:.2f}`** | `{rec['precision_oriented_threshold']:.2f}` | `{rec['recall_oriented_threshold']:.2f}` |"
        )
    md.append("")

    md.append("## Tooth Discoloration Threshold Curve")
    md.append("")
    md.append("| Threshold | Precision | Recall | F1 Score | FP Count | FN Count |")
    md.append("|---|---|---|---|---|---|")
    for t_str, data in results["metrics_by_threshold"].items():
        m = data["tooth discoloration"]
        md.append(f"| `{t_str}` | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} | {m['fp']:,} | {m['fn']:,} |")
    md.append("")

    md.append("## Calculus (Tartar) Threshold Curve")
    md.append("")
    md.append("| Threshold | Precision | Recall | F1 Score | FP Count | FN Count |")
    md.append("|---|---|---|---|---|---|")
    for t_str, data in results["metrics_by_threshold"].items():
        m = data["calculus"]
        md.append(f"| `{t_str}` | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} | {m['fp']:,} | {m['fn']:,} |")
    md.append("")

    md.append("## Calculus <-> Tooth Discoloration Cross-Confusion")
    md.append("")
    md.append("| Threshold | Calculus Pred on Discoloration GT | Discoloration Pred on Calculus GT |")
    md.append("|---|---|---|")
    for t_str, conf in results["confusion_by_threshold"].items():
        md.append(f"| `{t_str}` | {conf['calculus_pred_discoloration_gt']:,} | {conf['discoloration_pred_calculus_gt']:,} |")
    md.append("")

    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="Evaluate YOLO detector calibration across confidence thresholds.")
    parser.add_argument("--model", type=str, default="services/teeth_analyzer/models/oral_disease/best.pt")
    parser.add_argument("--dataset", type=str, default="dataset/oral-disease.yolov11")
    parser.add_argument("--split", type=str, default="valid")
    parser.add_argument("--iou", type=float, default=0.50)
    parser.add_argument("--max-images", type=int, default=None, help="Limit number of images for quick smoke test")
    parser.add_argument("--output", type=str, default="docs/evaluation/yolo_calibration_report.md")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()
    model_p = Path(args.model)
    dataset_p = Path(args.dataset)

    results = evaluate_split(
        model_path=model_p,
        dataset_root=dataset_p,
        split_name=args.split,
        iou_thresh=args.iou,
        max_images=args.max_images,
    )

    md_report = generate_calibration_markdown(results)
    out_p = Path(args.output)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(md_report, encoding="utf-8")
    print(f"Calibration report written to: {out_p.resolve()}", flush=True)

    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
