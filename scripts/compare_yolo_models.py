"""Compare YOLO Models (v1 vs v2) Evaluation Harness (Phase 11B-1).

Evaluates two local model binaries (e.g., best.pt vs best_v2.pt) against the same dataset split.
Produces side-by-side comparative metrics:
- Per-class: Precision, Recall, F1, False Positives, False Negatives
- Macro averages
- Specific focus: Tooth Discoloration False Positives & Calculus <-> Discoloration confusion
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
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

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def calculate_iou(boxA: tuple[float, float, float, float], boxB: tuple[float, float, float, float]) -> float:
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
    return (
        max(0.0, x_c - w / 2.0),
        max(0.0, y_c - h / 2.0),
        min(1.0, x_c + w / 2.0),
        min(1.0, y_c + h / 2.0),
    )


def load_ground_truth(labels_dir: Path) -> dict[str, list[tuple[int, tuple[float, float, float, float]]]]:
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


def evaluate_single_model(
    model_path: Path,
    image_paths: list[Path],
    gt_data: dict,
    conf_thresh: float = 0.50,
    iou_thresh: float = 0.50,
) -> dict:
    from ultralytics import YOLO

    model = YOLO(str(model_path))
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)
    calculus_pred_discoloration_gt = 0
    discoloration_pred_calculus_gt = 0
    total_detections = 0

    for img_p in image_paths:
        stem = img_p.stem
        gts = list(gt_data.get(stem, []))
        preds = []

        try:
            res = model.predict(source=str(img_p), conf=conf_thresh, iou=0.45, verbose=False)
            if res and len(res) > 0 and res[0].boxes is not None:
                boxes = res[0].boxes
                xyxy_norm = boxes.xyxyn.cpu().numpy()
                confs = boxes.conf.cpu().numpy()
                classes = boxes.cls.cpu().numpy()
                for i in range(len(classes)):
                    c_id = int(classes[i])
                    conf = float(confs[i])
                    box = tuple(map(float, xyxy_norm[i]))
                    preds.append((c_id, conf, box))
                    total_detections += 1
        except Exception:
            continue

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
    total_tp = sum(tp.values())
    total_fp = sum(fp.values())
    total_fn = sum(fn.values())

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

    macro_f1 = sum(m["f1"] for m in per_class.values()) / max(1, len(per_class))

    return {
        "model_name": model_path.name,
        "model_path": str(model_path),
        "total_detections": total_detections,
        "total_tp": total_tp,
        "total_fp": total_fp,
        "total_fn": total_fn,
        "macro_f1": round(macro_f1, 4),
        "per_class": per_class,
        "confusion": {
            "calculus_pred_discoloration_gt": calculus_pred_discoloration_gt,
            "discoloration_pred_calculus_gt": discoloration_pred_calculus_gt,
        },
    }


def compare_models(
    model_a_path: Path,
    model_b_path: Path,
    dataset_root: Path,
    split_name: str = "valid",
    conf_thresh: float = 0.50,
    iou_thresh: float = 0.50,
    max_images: int | None = None,
) -> dict:
    try:
        import ultralytics
    except ImportError:
        return {
            "status": "ultralytics_missing",
            "model_a": str(model_a_path),
            "model_b": str(model_b_path),
            "error": "Ultralytics is not installed in the active environment. Run in an environment with ultralytics.",
        }

    if not model_a_path.exists():
        raise FileNotFoundError(f"Model A file not found: {model_a_path}")
    if not model_b_path.exists():
        raise FileNotFoundError(f"Model B file not found: {model_b_path}")

    split_dir = dataset_root / split_name
    images_dir = split_dir / "images" if (split_dir / "images").exists() else split_dir
    labels_dir = split_dir / "labels" if (split_dir / "labels").exists() else split_dir

    gt_data = load_ground_truth(labels_dir)

    image_paths = []
    with os.scandir(images_dir) as it:
        for entry in it:
            if entry.is_file() and os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
                image_paths.append(Path(entry.path))
                if max_images and len(image_paths) >= max_images:
                    break

    print(f"Evaluating Model A ({model_a_path.name}) on {len(image_paths)} images ...", flush=True)
    res_a = evaluate_single_model(model_a_path, image_paths, gt_data, conf_thresh, iou_thresh)

    print(f"Evaluating Model B ({model_b_path.name}) on {len(image_paths)} images ...", flush=True)
    res_b = evaluate_single_model(model_b_path, image_paths, gt_data, conf_thresh, iou_thresh)

    return {
        "status": "success",
        "split": split_name,
        "images_evaluated": len(image_paths),
        "conf_threshold": conf_thresh,
        "model_a": res_a,
        "model_b": res_b,
    }


def generate_comparison_markdown(results: dict) -> str:
    md = []
    md.append("# DaantShaant YOLO Model Comparison Report (v1 vs v2)")
    md.append("")
    md.append("> Generated as part of Phase 11B-1: YOLO Detector Calibration + Hard-Negative Preparation.")
    md.append("")

    if results.get("status") != "success":
        md.append(f"> [!WARNING]\n> {results.get('error', 'Comparison could not be completed.')}\n")
        return "\n".join(md)

    a = results["model_a"]
    b = results["model_b"]

    md.append("## Overview")
    md.append("")
    md.append(f"- **Model A (Baseline)**: `{a['model_name']}` (Macro F1: **{a['macro_f1']:.4f}**, Total FP: **{a['total_fp']:,}**)")
    md.append(f"- **Model B (Candidate)**: `{b['model_name']}` (Macro F1: **{b['macro_f1']:.4f}**, Total FP: **{b['total_fp']:,}**)")
    md.append(f"- **Split Evaluated**: `{results['split']}` ({results['images_evaluated']} images, conf threshold: `{results['conf_threshold']}`)")
    md.append("")

    # Highlight false positive delta
    fp_delta = b["total_fp"] - a["total_fp"]
    fp_pct = (fp_delta / max(1, a["total_fp"])) * 100
    disc_fp_a = a["per_class"]["tooth discoloration"]["fp"]
    disc_fp_b = b["per_class"]["tooth discoloration"]["fp"]
    disc_delta = disc_fp_b - disc_fp_a

    md.append("### Key Hard-Negative Highlights")
    md.append("")
    md.append(f"- **Overall False Positives**: {a['total_fp']:,} -> {b['total_fp']:,} ({fp_delta:+d} / {fp_pct:+.1f}%)")
    md.append(f"- **Tooth Discoloration False Positives**: {disc_fp_a:,} -> {disc_fp_b:,} ({disc_delta:+d})")
    md.append(f"- **Calculus -> Discoloration Confusion**: {a['confusion']['calculus_pred_discoloration_gt']} -> {b['confusion']['calculus_pred_discoloration_gt']}")
    md.append(f"- **Discoloration -> Calculus Confusion**: {a['confusion']['discoloration_pred_calculus_gt']} -> {b['confusion']['discoloration_pred_calculus_gt']}")
    md.append("")

    md.append("## Per-Class Comparison Table")
    md.append("")
    md.append("| Class Name | Metric | Model A | Model B | Delta |")
    md.append("|---|---|---|---|---|")

    for c_id, c_name in CLASS_NAMES.items():
        ca = a["per_class"][c_name]
        cb = b["per_class"][c_name]

        md.append(f"| **`{c_name}`** | Precision | {ca['precision']:.4f} | {cb['precision']:.4f} | {(cb['precision'] - ca['precision']):+.4f} |")
        md.append(f"| | Recall | {ca['recall']:.4f} | {cb['recall']:.4f} | {(cb['recall'] - ca['recall']):+.4f} |")
        md.append(f"| | F1 Score | **{ca['f1']:.4f}** | **{cb['f1']:.4f}** | **{(cb['f1'] - ca['f1']):+.4f}** |")
        md.append(f"| | False Positives | {ca['fp']:,} | {cb['fp']:,} | {(cb['fp'] - ca['fp']):+d} |")

    md.append("")
    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="Compare two YOLO model weights against the same dataset split.")
    parser.add_argument("--model-a", type=str, required=True, help="Path to baseline model (e.g. best.pt)")
    parser.add_argument("--model-b", type=str, required=True, help="Path to candidate model (e.g. best_v2.pt)")
    parser.add_argument("--dataset", type=str, default="dataset/oral-disease.yolov11")
    parser.add_argument("--split", type=str, default="valid")
    parser.add_argument("--conf", type=float, default=0.50)
    parser.add_argument("--iou", type=float, default=0.50)
    parser.add_argument("--max-images", type=int, default=None)
    parser.add_argument("--output", type=str, default="docs/evaluation/yolo_model_comparison.md")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()
    results = compare_models(
        model_a_path=Path(args.model_a),
        model_b_path=Path(args.model_b),
        dataset_root=Path(args.dataset),
        split_name=args.split,
        conf_thresh=args.conf,
        iou_thresh=args.iou,
        max_images=args.max_images,
    )

    md = generate_comparison_markdown(results)
    out_p = Path(args.output)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(md, encoding="utf-8")
    print(f"Comparison report written to: {out_p.resolve()}", flush=True)

    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
