"""Mine Healthy Hard Negatives and Controls from External YOLO Dataset (Phase 11B-3).

Identifies healthy-only images from an external dataset (e.g. Dental Data Set.yolov11),
evaluates them with the current DaantShaant oral disease detector (best.pt),
and generates candidate pools:
  A. MODEL_FALSE_POSITIVE: Images where best.pt predicts supported oral disease classes (>= 0.30)
  B. CLEAN_CONTROL: Healthy images where best.pt produces 0 detections (>= 0.30)

Outputs:
  - dataset/healthy-negative-candidates/review.csv
  - dataset/healthy-negative-candidates/candidates.json
  - dataset/healthy-negative-candidates/contact_sheet_01.jpg

Strict Safety Rules:
  1. Never touches original oral-disease valid/test benchmark splits.
  2. Asserts zero SHA-256 hash overlap with benchmark splits.
  3. Healthy bounding boxes are NEVER converted to DaantShaant disease labels.
  4. Accepted negatives will produce EMPTY (0-byte) labels in YOLO v2.
  5. Initial review_status is UNREVIEWED.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

from PIL import Image, ImageDraw, ImageFont
import yaml

# Supported DaantShaant disease classes
DAANTSHAANT_CLASSES = {
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
    "caries": 1.4,               # Shadows misidentified as cavities
    "calculus": 1.3,             # False-positive prior on clean teeth
    "gingivitis": 1.1,
    "ulcer": 1.0,
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def compute_file_hash(filepath: Path) -> str:
    """Computes SHA-256 hash of a file for deduplication and leakage prevention."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_data_yaml(yaml_path: Path) -> dict[str, Any]:
    """Parses dataset data.yaml and dynamically identifies the healthy class ID and metadata."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"data.yaml not found at: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    names = data.get("names", [])
    if isinstance(names, dict):
        # Convert dict index to list
        sorted_keys = sorted(int(k) for k in names.keys())
        names = [names[k] for k in sorted_keys]

    healthy_id: int | None = None
    healthy_name: str | None = None

    for idx, name in enumerate(names):
        norm = str(name).strip().lower()
        if norm in ("healthy", "healthy teeth", "healthy tooth", "healthy_teeth", "healthy_tooth"):
            healthy_id = idx
            healthy_name = str(name)
            break

    if healthy_id is None:
        raise ValueError(
            f"Could not identify a healthy class in data.yaml names: {names}. "
            "Expected 'healthy' or 'healthy teeth'."
        )

    return {
        "names": names,
        "healthy_class_id": healthy_id,
        "healthy_class_name": healthy_name,
        "roboflow": data.get("roboflow", {}),
    }


def classify_dataset_images(
    dataset_dir: Path,
    split: str = "train",
    healthy_class_id: int = 6,
) -> dict[str, Any]:
    """Scans dataset split images and labels, partitioning into healthy-only, mixed, and disease-only.
    
    Excludes any image containing disease bounding boxes from the healthy-only candidate set.
    """
    split_dir = dataset_dir / split
    images_dir = split_dir / "images" if (split_dir / "images").exists() else split_dir
    labels_dir = split_dir / "labels" if (split_dir / "labels").exists() else split_dir

    if not images_dir.exists():
        raise FileNotFoundError(f"Images directory not found for split '{split}': {images_dir}")

    labels_map: dict[str, Path] = {}
    if labels_dir.exists():
        with os.scandir(labels_dir) as it:
            for entry in it:
                if entry.is_file() and entry.name.endswith(".txt"):
                    stem = entry.name[:-4]
                    labels_map[stem] = Path(entry.path)

    images = []
    with os.scandir(images_dir) as it:
        for entry in it:
            if entry.is_file() and os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
                images.append(Path(entry.path))

    images.sort(key=lambda p: p.name)

    healthy_only: list[Path] = []
    mixed: list[Path] = []
    disease_only: list[Path] = []
    empty: list[Path] = []
    box_counter = Counter()

    for img_p in images:
        lbl_p = labels_map.get(img_p.stem)
        if not lbl_p or not lbl_p.exists():
            empty.append(img_p)
            continue

        try:
            content = lbl_p.read_text(encoding="utf-8").strip()
        except Exception:
            content = ""

        if not content:
            empty.append(img_p)
            continue

        class_ids = set()
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if parts:
                try:
                    cid = int(parts[0])
                    class_ids.add(cid)
                    box_counter[cid] += 1
                except ValueError:
                    pass

        if not class_ids:
            empty.append(img_p)
        elif class_ids == {healthy_class_id}:
            healthy_only.append(img_p)
        elif healthy_class_id in class_ids:
            mixed.append(img_p)
        else:
            disease_only.append(img_p)

    return {
        "total_images": len(images),
        "healthy_only": healthy_only,
        "mixed": mixed,
        "disease_only": disease_only,
        "empty": empty,
        "box_counter": dict(box_counter),
    }


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


def mine_healthy_candidates(
    dataset_dir: Path,
    model_path: Path,
    split: str = "train",
    min_confidence: float = 0.30,
    output_dir: Path = Path("dataset/healthy-negative-candidates"),
    original_dataset_dir: Path | None = Path("dataset/oral-disease.yolov11"),
    control_sample_size: int = 50,
    seed: int = 42,
    model: Any | None = None,
) -> dict[str, Any]:
    """Runs best.pt against healthy-only images to mine false positives and normal controls."""
    # 1. Parse data.yaml
    data_yaml_path = dataset_dir / "data.yaml"
    yaml_info = parse_data_yaml(data_yaml_path)
    healthy_id = yaml_info["healthy_class_id"]
    healthy_name = yaml_info["healthy_class_name"]

    print(f"Parsed data.yaml from {dataset_dir}:")
    print(f"  Class names: {yaml_info['names']}")
    print(f"  Healthy class: index {healthy_id} ('{healthy_name}')")

    # 2. Classify images
    classification = classify_dataset_images(dataset_dir, split=split, healthy_class_id=healthy_id)
    healthy_only_images = classification["healthy_only"]
    print(f"\nDataset Image Breakdown ({split} split):")
    print(f"  Total images: {classification['total_images']}")
    print(f"  Healthy-only images: {len(healthy_only_images)}")
    print(f"  Mixed (healthy + disease) images: {len(classification['mixed'])} [EXCLUDED]")
    print(f"  Disease-only images: {len(classification['disease_only'])} [EXCLUDED]")
    print(f"  Empty-label images: {len(classification['empty'])}")

    # 3. Load YOLO detector
    if model is None:
        from ultralytics import YOLO
        print(f"\nLoading detector model: {model_path} ...", flush=True)
        model = YOLO(str(model_path))

    # 4. Run detector against healthy-only images
    false_positives: list[dict[str, Any]] = []
    clean_controls: list[dict[str, Any]] = []
    fp_class_counter = Counter()

    print(f"\nEvaluating {len(healthy_only_images)} healthy-only images with best.pt (conf >= {min_confidence:.2f}) ...", flush=True)

    for img_p in healthy_only_images:
        try:
            results = model.predict(source=str(img_p), conf=min_confidence, iou=0.45, verbose=False)
            res = results[0]
        except Exception as exc:
            print(f"Inference failed on {img_p.name}: {exc}", file=sys.stderr)
            continue

        boxes = res.boxes
        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.cpu().numpy()
            xyxyn = boxes.xyxyn.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            clss = boxes.cls.cpu().numpy()

            detections = []
            for j in range(len(clss)):
                c_id = int(clss[j])
                raw_cls = DAANTSHAANT_CLASSES.get(c_id, f"class_{c_id}")
                norm_cls = NORMALIZED_NAMES.get(raw_cls, raw_cls)
                c_conf = round(float(confs[j]), 4)
                box_xyxy = [round(float(v), 2) for v in xyxy[j]]
                box_xyxyn = [round(float(v), 4) for v in xyxyn[j]]

                fp_class_counter[raw_cls] += 1
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

            false_positives.append({
                "filename": img_p.name,
                "source_path": str(img_p.relative_to(dataset_dir.parent) if dataset_dir.parent in img_p.parents else img_p),
                "absolute_path": str(img_p.resolve()),
                "source_split": split,
                "source_healthy_class": healthy_name,
                "candidate_type": "MODEL_FALSE_POSITIVE",
                "top_predicted_class": top_det["raw_class"],
                "top_confidence": top_det["confidence"],
                "detection_count": len(detections),
                "all_predictions": json.dumps(detections),
                "priority": priority,
                "review_status": "UNREVIEWED",
                "review_note": f"Detector falsely flagged {len(detections)} boxes as {top_det['raw_class']} on healthy tooth image.",
                "detections": detections,
            })
        else:
            # Clean control
            clean_controls.append({
                "filename": img_p.name,
                "source_path": str(img_p.relative_to(dataset_dir.parent) if dataset_dir.parent in img_p.parents else img_p),
                "absolute_path": str(img_p.resolve()),
                "source_split": split,
                "source_healthy_class": healthy_name,
                "candidate_type": "CLEAN_CONTROL",
                "top_predicted_class": "none",
                "top_confidence": 0.0,
                "detection_count": 0,
                "all_predictions": "[]",
                "priority": 0.0,
                "review_status": "UNREVIEWED",
                "review_note": "Clean healthy control; detector produced zero detections >= 0.30.",
                "detections": [],
            })

    # Sort false positives by priority score desc, then top confidence desc
    false_positives.sort(key=lambda c: (-c["priority"], -c["top_confidence"]))

    # Sort clean controls deterministically by filename
    clean_controls.sort(key=lambda c: c["filename"])

    # Sample controls if needed
    if len(clean_controls) > control_sample_size:
        import random
        rng = random.Random(seed)
        selected_controls = rng.sample(clean_controls, control_sample_size)
        selected_controls.sort(key=lambda c: c["filename"])
    else:
        selected_controls = clean_controls

    # Combine candidates: false positives first, clean controls next
    all_candidates = false_positives + selected_controls

    # Assign 1-indexed tile numbers
    for idx, c in enumerate(all_candidates, 1):
        c["tile_number"] = idx

    # 5. Check exact deduplication & benchmark leakage
    hashes: dict[str, str] = {}
    for c in all_candidates:
        h = compute_file_hash(Path(c["absolute_path"]))
        if h in hashes:
            print(f"[!] Duplicate detected within candidates: {c['filename']} == {hashes[h]}", file=sys.stderr)
        hashes[h] = c["filename"]

    # Check benchmark isolation if original dataset provided
    if original_dataset_dir and original_dataset_dir.exists():
        for b_split in ["valid", "test"]:
            b_dir = original_dataset_dir / b_split / "images"
            if b_dir.exists():
                for b_file in b_dir.glob("*.*"):
                    bh = compute_file_hash(b_file)
                    if bh in hashes:
                        raise RuntimeError(
                            f"[DATA LEAKAGE ERROR] Healthy candidate '{hashes[bh]}' matches "
                            f"benchmark {b_split} image '{b_file.name}'! Benchmark isolation violated."
                        )

    # 6. Save review.csv and candidates.json
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "review.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "tile_number",
            "filename",
            "source_path",
            "source_split",
            "source_healthy_class",
            "candidate_type",
            "top_predicted_class",
            "top_confidence",
            "detection_count",
            "all_predictions",
            "priority",
            "review_status",
            "review_note",
        ])
        for c in all_candidates:
            writer.writerow([
                c["tile_number"],
                c["filename"],
                c["source_path"],
                c["source_split"],
                c["source_healthy_class"],
                c["candidate_type"],
                c["top_predicted_class"],
                f"{c['top_confidence']:.4f}",
                c["detection_count"],
                c["all_predictions"],
                f"{c['priority']:.3f}",
                c["review_status"],
                c["review_note"],
            ])

    json_path = output_dir / "candidates.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "dataset": str(dataset_dir),
            "split": split,
            "min_confidence": min_confidence,
            "total_healthy_only_evaluated": len(healthy_only_images),
            "false_positives_mined": len(false_positives),
            "clean_controls_retained": len(selected_controls),
            "total_candidates": len(all_candidates),
            "fp_class_distribution": dict(fp_class_counter),
            "candidates": all_candidates,
        }, f, indent=2)

    print(f"\n[✓] Generated candidate files:\n  CSV:  {csv_path}\n  JSON: {json_path}")
    print(f"Total false-positive hard negatives: {len(false_positives)}")
    print(f"Total clean normal controls:        {len(selected_controls)}")
    print("False-positive predictions by class:")
    for cls_name, cnt in fp_class_counter.most_common():
        print(f"  - {cls_name}: {cnt} detections")

    return {
        "classification": classification,
        "false_positives": false_positives,
        "clean_controls": selected_controls,
        "all_candidates": all_candidates,
        "fp_class_counter": dict(fp_class_counter),
        "csv_path": csv_path,
        "json_path": json_path,
    }


def create_contact_sheets(
    candidates: list[dict[str, Any]],
    output_dir: Path,
    cols: int = 4,
    rows: int = 4,
    tile_size: tuple[int, int] = (360, 360),
) -> list[Path]:
    """Renders visual contact sheets for manual review of healthy false positives and controls."""
    if not candidates:
        print("No candidates to render on contact sheet.")
        return []

    per_sheet = cols * rows
    num_sheets = math.ceil(len(candidates) / per_sheet)
    sheet_paths = []

    COLORS = {
        "calculus": (230, 126, 34),          # Orange
        "caries": (231, 76, 60),             # Red
        "gingivitis": (155, 89, 182),        # Purple
        "tooth discoloration": (241, 196, 15), # Yellow
        "ulcer": (52, 152, 219),             # Blue
    }

    try:
        font_header = ImageFont.truetype("arial.ttf", 14)
        font_box = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        font_header = ImageFont.load_default()
        font_box = ImageFont.load_default()

    print(f"Rendering {num_sheets} contact sheet(s) ({cols}x{rows} tiles per sheet) ...", flush=True)

    for sheet_idx in range(num_sheets):
        sheet_candidates = candidates[sheet_idx * per_sheet : (sheet_idx + 1) * per_sheet]
        sheet_w = cols * tile_size[0]
        sheet_h = rows * tile_size[1]
        sheet_img = Image.new("RGB", (sheet_w, sheet_h), color=(18, 22, 28))
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
            except Exception:
                tile_img = Image.new("RGB", tile_size, color=(40, 40, 40))
                orig_w, orig_h = tile_size

            tile_draw = ImageDraw.Draw(tile_img)
            scale_x = tile_size[0] / max(1, orig_w)
            scale_y = tile_size[1] / max(1, orig_h)

            is_fp = c["candidate_type"] == "MODEL_FALSE_POSITIVE"

            if is_fp:
                for det in c.get("detections", []):
                    cls_name = det["raw_class"]
                    color = COLORS.get(cls_name, (255, 255, 255))
                    bx = det["box_xyxy"]
                    tx1 = bx[0] * scale_x
                    ty1 = bx[1] * scale_y
                    tx2 = bx[2] * scale_x
                    ty2 = bx[3] * scale_y

                    tile_draw.rectangle([tx1, ty1, tx2, ty2], outline=color, width=2)
                    label_text = f"{cls_name} {det['confidence']:.2f}"
                    tile_draw.rectangle([tx1, max(0, ty1 - 16), tx1 + len(label_text) * 7, ty1], fill=color)
                    tile_draw.text((tx1 + 2, max(0, ty1 - 15)), label_text, fill=(0, 0, 0), font=font_box)

            # Header info overlay
            tile_num = c.get("tile_number", sheet_idx * per_sheet + tile_idx + 1)
            if is_fp:
                header_text = f"#{tile_num} [FP] {c['filename'][:14]} | {c['top_predicted_class']} ({c['top_confidence']:.2f})"
                hdr_bg = (180, 40, 40, 220)
            else:
                header_text = f"#{tile_num} [CONTROL] {c['filename'][:14]} | 0 detections"
                hdr_bg = (30, 140, 60, 220)

            tile_draw.rectangle([0, 0, tile_size[0], 22], fill=hdr_bg)
            tile_draw.text((4, 3), header_text, fill=(255, 255, 255), font=font_header)

            sheet_img.paste(tile_img, (x_offset, y_offset))
            draw_sheet.rectangle([x_offset, y_offset, x_offset + tile_size[0], y_offset + tile_size[1]], outline=(60, 70, 80), width=1)

        sheet_file = output_dir / f"contact_sheet_{sheet_idx + 1:02d}.jpg"
        sheet_img.save(sheet_file, quality=90)
        sheet_paths.append(sheet_file)
        print(f"  Saved contact sheet: {sheet_file}", flush=True)

    return sheet_paths


def main():
    parser = argparse.ArgumentParser(description="Mine healthy hard negatives and clean controls from external YOLO dataset.")
    parser.add_argument("--dataset", type=str, default="dataset/Dental Data Set.yolov11")
    parser.add_argument("--model", type=str, default="services/teeth_analyzer/models/oral_disease/best.pt")
    parser.add_argument("--split", type=str, default="train")
    parser.add_argument("--min-confidence", type=float, default=0.30)
    parser.add_argument("--output-dir", type=str, default="dataset/healthy-negative-candidates")
    parser.add_argument("--original-dataset", type=str, default="dataset/oral-disease.yolov11")
    parser.add_argument("--control-sample-size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-contact-sheet", action="store_true")

    args = parser.parse_args()

    mining_res = mine_healthy_candidates(
        dataset_dir=Path(args.dataset),
        model_path=Path(args.model),
        split=args.split,
        min_confidence=args.min_confidence,
        output_dir=Path(args.output_dir),
        original_dataset_dir=Path(args.original_dataset) if args.original_dataset else None,
        control_sample_size=args.control_sample_size,
        seed=args.seed,
    )

    if not args.no_contact_sheet:
        create_contact_sheets(mining_res["all_candidates"], output_dir=Path(args.output_dir))

    print("\n[✓] Healthy negative mining completed successfully.")


if __name__ == "__main__":
    main()
