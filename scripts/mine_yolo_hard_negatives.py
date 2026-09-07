"""Mine YOLO Hard Negatives (Phase 11B-2).

Scans empty-label training images from the YOLO dataset against current best.pt
to identify false-positive predictions on unannotated/healthy images.

Outputs:
- review.csv: ranked metadata for all candidates
- contact sheets: visual tiles showing false positives for Nathan manual review
- review_status initialized to UNREVIEWED

Strict rules:
1. Operates ONLY on the specified split (default: 'train').
2. NEVER touches valid or test negative pools for training candidate generation.
3. Completely offline; zero external APIs, zero browser, zero training.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

from PIL import Image, ImageDraw, ImageFont

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

# Priority weights reflecting clinical importance and observed imbalance
CLASS_PRIORITY_WEIGHTS = {
    "tooth discoloration": 1.5,  # Dominant false-positive source
    "calculus": 1.4,             # High false-positive prior on clean teeth
    "caries": 1.3,               # Shadows misidentified as cavities
    "gingivitis": 1.1,
    "ulcer": 1.0,
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def find_empty_label_images(dataset_dir: Path, split: str = "train") -> list[Path]:
    """Finds all images in the specified split whose matching YOLO label is empty or missing."""
    split_dir = dataset_dir / split
    images_dir = split_dir / "images" if (split_dir / "images").exists() else split_dir
    labels_dir = split_dir / "labels" if (split_dir / "labels").exists() else split_dir

    if not images_dir.exists():
        raise FileNotFoundError(f"Images directory not found for split '{split}': {images_dir}")

    # Build map of label files
    labels_map = {}
    if labels_dir.exists():
        with os.scandir(labels_dir) as it:
            for entry in it:
                if entry.is_file() and entry.name.endswith(".txt"):
                    stem = entry.name[:-4]
                    labels_map[stem] = entry.path

    empty_images = []
    with os.scandir(images_dir) as it:
        for entry in it:
            if entry.is_file() and os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
                stem = os.path.splitext(entry.name)[0]
                lbl_path = labels_map.get(stem)
                is_empty = False
                if not lbl_path:
                    # Missing label = empty / negative
                    is_empty = True
                else:
                    try:
                        with open(lbl_path, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                        if not content:
                            is_empty = True
                        else:
                            # Check if valid lines exist
                            lines = [l.strip() for l in content.splitlines() if l.strip()]
                            if not lines:
                                is_empty = True
                    except Exception:
                        is_empty = True

                if is_empty:
                    empty_images.append(Path(entry.path))

    empty_images.sort(key=lambda p: p.name)
    return empty_images


def calculate_priority_score(detections: list[dict[str, Any]]) -> float:
    """Calculates candidate priority score based on confidence and class weights."""
    if not detections:
        return 0.0

    score = 0.0
    for det in detections:
        cls_name = det["raw_class"]
        weight = CLASS_PRIORITY_WEIGHTS.get(cls_name, 1.0)
        conf = det["confidence"]
        score += weight * (conf ** 2)

    top_conf = max(d["confidence"] for d in detections)
    score += top_conf * 2.0
    return round(score, 3)


def mine_hard_negatives(
    model_path: Path,
    dataset_dir: Path,
    split: str = "train",
    min_confidence: float = 0.30,
    top_k: int = 200,
    output_dir: Path = Path("dataset/hard-negative-candidates"),
    batch_size: int = 32,
    model: Any | None = None,
) -> dict[str, Any]:
    """Runs YOLO against empty-label images in the chosen split and mines false positives."""
    if split in ("valid", "test"):
        print(f"[!] WARNING: Mining on split '{split}'. Remember Section 4: Only 'train' negatives should enter v2 training!", file=sys.stderr)

    if model is None:
        from ultralytics import YOLO
        print(f"Loading YOLO model: {model_path} ...", flush=True)
        model = YOLO(str(model_path))

    empty_images = find_empty_label_images(dataset_dir, split=split)
    print(f"Discovered {len(empty_images)} empty-label images in '{split}' split.", flush=True)

    candidates = []
    class_counter = Counter()

    # Process in batches for speed
    total = len(empty_images)
    print(f"Running inference at min_confidence={min_confidence:.2f} ...", flush=True)

    for i in range(0, total, batch_size):
        batch = empty_images[i : i + batch_size]
        batch_paths = [str(p) for p in batch]

        try:
            results = model.predict(source=batch_paths, conf=min_confidence, iou=0.45, verbose=False)
        except Exception as exc:
            print(f"Inference error on batch {i}: {exc}", file=sys.stderr)
            continue

        for p, res in zip(batch, results):
            boxes = res.boxes
            if boxes is None or len(boxes) == 0:
                continue

            xyxy = boxes.xyxy.cpu().numpy()
            xyxyn = boxes.xyxyn.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            clss = boxes.cls.cpu().numpy()

            detections = []
            for j in range(len(clss)):
                c_id = int(clss[j])
                raw_cls = CLASS_NAMES.get(c_id, f"class_{c_id}")
                norm_cls = NORMALIZED_NAMES.get(raw_cls, raw_cls)
                c_conf = round(float(confs[j]), 4)
                box_xyxy = [round(float(v), 2) for v in xyxy[j]]
                box_xyxyn = [round(float(v), 4) for v in xyxyn[j]]

                class_counter[raw_cls] += 1
                detections.append({
                    "class_id": c_id,
                    "raw_class": raw_cls,
                    "normalized_finding": norm_cls,
                    "confidence": c_conf,
                    "box_xyxy": box_xyxy,
                    "box_xyxyn": box_xyxyn,
                })

            detections.sort(key=lambda d: -d["confidence"])
            top_det = detections[0]
            priority = calculate_priority_score(detections)

            candidates.append({
                "filename": p.name,
                "source_path": str(p.relative_to(dataset_dir.parent) if dataset_dir.parent in p.parents else p),
                "absolute_path": str(p.resolve()),
                "top_class": top_det["raw_class"],
                "top_normalized": top_det["normalized_finding"],
                "top_confidence": top_det["confidence"],
                "detection_count": len(detections),
                "all_predictions": json.dumps(detections),
                "priority": priority,
                "review_status": "UNREVIEWED",
                "detections": detections,
            })

        if (i + batch_size) % 128 == 0 or (i + batch_size) >= total:
            print(f"  Processed {min(i + batch_size, total)}/{total} images — {len(candidates)} false positives mined so far", flush=True)

    # Rank candidates by highest priority score, then top confidence
    candidates.sort(key=lambda c: (-c["priority"], -c["top_confidence"]))

    if top_k and len(candidates) > top_k:
        selected_candidates = candidates[:top_k]
    else:
        selected_candidates = candidates

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write review.csv
    csv_path = output_dir / "review.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "filename",
            "source_path",
            "top_class",
            "top_confidence",
            "detection_count",
            "all_predictions",
            "priority",
            "review_status",
        ])
        for c in selected_candidates:
            writer.writerow([
                c["filename"],
                c["source_path"],
                c["top_class"],
                f"{c['top_confidence']:.4f}",
                c["detection_count"],
                c["all_predictions"],
                f"{c['priority']:.3f}",
                c["review_status"],
            ])

    # 2. Write candidates.json with full rich metadata
    json_path = output_dir / "candidates.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "split": split,
            "min_confidence": min_confidence,
            "total_negatives_evaluated": len(empty_images),
            "false_positives_mined": len(candidates),
            "candidates_retained": len(selected_candidates),
            "class_distribution": dict(class_counter),
            "candidates": selected_candidates,
        }, f, indent=2)

    print(f"\nMined {len(candidates)} false-positive images from {len(empty_images)} empty-label images.")
    print(f"Top {len(selected_candidates)} candidates saved to:\n  CSV: {csv_path}\n  JSON: {json_path}")
    print("\nClass breakdown of false-positive detections:")
    for cls_name, cnt in class_counter.most_common():
        print(f"  - {cls_name}: {cnt} detections")

    return {
        "total_empty_images": len(empty_images),
        "false_positives_mined": len(candidates),
        "selected_count": len(selected_candidates),
        "class_counter": dict(class_counter),
        "csv_path": csv_path,
        "json_path": json_path,
        "candidates": selected_candidates,
    }


def create_contact_sheets(
    candidates: list[dict[str, Any]],
    output_dir: Path,
    cols: int = 4,
    rows: int = 5,
    tile_size: tuple[int, int] = (320, 320),
) -> list[Path]:
    """Renders visual contact sheets of mined false-positive candidates for manual review."""
    if not candidates:
        print("No candidates to render on contact sheet.")
        return []

    per_sheet = cols * rows
    num_sheets = math.ceil(len(candidates) / per_sheet)
    sheet_paths = []

    # Box colors per class
    COLORS = {
        "calculus": (230, 126, 34),          # Orange
        "caries": (231, 76, 60),             # Red
        "gingivitis": (155, 89, 182),        # Purple
        "tooth discoloration": (241, 196, 15), # Yellow
        "ulcer": (52, 152, 219),             # Blue
    }

    print(f"Rendering {num_sheets} contact sheet(s) ({cols}x{rows} tiles per sheet) ...", flush=True)

    for sheet_idx in range(num_sheets):
        sheet_candidates = candidates[sheet_idx * per_sheet : (sheet_idx + 1) * per_sheet]
        sheet_w = cols * tile_size[0]
        sheet_h = rows * tile_size[1]
        sheet_img = Image.new("RGB", (sheet_w, sheet_h), color=(20, 24, 30))
        draw_sheet = ImageDraw.Draw(sheet_img)

        for tile_idx, c in enumerate(sheet_candidates):
            c_col = tile_idx % cols
            c_row = tile_idx // cols
            x_offset = c_col * tile_size[0]
            y_offset = c_row * tile_size[1]

            img_path = Path(c["absolute_path"])
            try:
                with Image.open(img_path) as raw_img:
                    raw_rgb = raw_img.convert("RGB")
                    orig_w, orig_h = raw_rgb.size
                    tile_img = raw_rgb.resize(tile_size, Image.Resampling.BILINEAR)
            except Exception as e:
                # Placeholder tile if image cannot be read
                tile_img = Image.new("RGB", tile_size, color=(50, 50, 50))
                orig_w, orig_h = tile_size

            # Draw bounding boxes scaled to tile
            tile_draw = ImageDraw.Draw(tile_img)
            scale_x = tile_size[0] / max(1, orig_w)
            scale_y = tile_size[1] / max(1, orig_h)

            for det in c.get("detections", []):
                cls_name = det["raw_class"]
                color = COLORS.get(cls_name, (255, 255, 255))
                bx = det["box_xyxy"]
                tx1 = bx[0] * scale_x
                ty1 = bx[1] * scale_y
                tx2 = bx[2] * scale_x
                ty2 = bx[3] * scale_y

                # Draw rectangle
                tile_draw.rectangle([tx1, ty1, tx2, ty2], outline=color, width=2)

                # Draw label
                label_text = f"{cls_name} {det['confidence']:.2f}"
                tile_draw.rectangle([tx1, max(0, ty1 - 16), tx1 + len(label_text) * 7, ty1], fill=color)
                tile_draw.text((tx1 + 2, max(0, ty1 - 15)), label_text, fill=(0, 0, 0))

            # Header info overlay on tile top
            header_text = f"#{sheet_idx * per_sheet + tile_idx + 1} | {c['filename'][:16]} | {c['top_class']} ({c['top_confidence']:.2f})"
            tile_draw.rectangle([0, 0, tile_size[0], 18], fill=(0, 0, 0, 180))
            tile_draw.text((4, 2), header_text, fill=(255, 255, 255))

            # Paste into sheet
            sheet_img.paste(tile_img, (x_offset, y_offset))
            # Grid border
            draw_sheet.rectangle([x_offset, y_offset, x_offset + tile_size[0], y_offset + tile_size[1]], outline=(60, 70, 80), width=1)

        sheet_file = output_dir / f"contact_sheet_{sheet_idx + 1:02d}.jpg"
        sheet_img.save(sheet_file, quality=88)
        sheet_paths.append(sheet_file)
        print(f"  Saved contact sheet: {sheet_file}", flush=True)

    return sheet_paths


def main():
    parser = argparse.ArgumentParser(description="Mine hard negatives from empty-label YOLO training dataset.")
    parser.add_argument("--model", type=str, default="services/teeth_analyzer/models/oral_disease/best.pt")
    parser.add_argument("--dataset", type=str, default="dataset/oral-disease.yolov11")
    parser.add_argument("--split", type=str, default="train", help="Dataset split to mine (must be train for v2)")
    parser.add_argument("--min-confidence", type=float, default=0.30)
    parser.add_argument("--top-k", type=int, default=200)
    parser.add_argument("--output-dir", type=str, default="dataset/hard-negative-candidates")
    parser.add_argument("--no-contact-sheet", action="store_true", help="Skip contact sheet generation")

    args = parser.parse_args()

    model_p = Path(args.model)
    dataset_p = Path(args.dataset)
    out_p = Path(args.output_dir)

    if not model_p.exists():
        print(f"Error: Model not found at {model_p}", file=sys.stderr)
        sys.exit(1)

    if not dataset_p.exists():
        print(f"Error: Dataset not found at {dataset_p}", file=sys.stderr)
        sys.exit(1)

    mining_res = mine_hard_negatives(
        model_path=model_p,
        dataset_dir=dataset_p,
        split=args.split,
        min_confidence=args.min_confidence,
        top_k=args.top_k,
        output_dir=out_p,
    )

    if not args.no_contact_sheet:
        create_contact_sheets(mining_res["candidates"], output_dir=out_p)

    print("\n[✓] Hard-negative mining completed successfully.")


if __name__ == "__main__":
    main()
