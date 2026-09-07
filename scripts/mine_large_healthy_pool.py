"""Mine Large Healthy-Negative Pool and Prepare V2 Candidates (Phase 11B-4 FINAL).

Processes the full Penyakit Gigi Skripsi dataset (2,468 images across train/valid/test),
identifies healthy-only source images, evaluates every single healthy image with
best.pt (conf >= 0.30), performs perceptual and cryptographic deduplication,
applies basic image quality filtering, and generates candidate review artifacts.

Outputs in dataset/final-healthy-negative-candidates/:
  - review.csv: Full candidate pool with review_status (UNREVIEWED for FP, AUTO_ELIGIBLE_CONTROL for clean controls)
  - candidates.json: Machine-readable candidate metadata
  - audit.json: Complete statistical audit of dataset, classes, detections, quality, duplicates
  - contact_sheet_fp_01.jpg, ...: Top 120 false-positive candidates (4x4 grids, 16 tiles each)
  - contact_sheet_control_audit_01.jpg, ...: 50 deterministic clean-control audit samples (seed 42)

Strict Safety Rules:
  1. No external image downloads.
  2. Offline local YOLO inference only.
  3. Strict SHA-256 leakage protection against benchmark valid and test splits.
  4. Original benchmark splits are 100% UNTOUCHED.
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
import random
import sys
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import yaml

# Supported DaantShaant disease classes in best.pt
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

# Priority ranking weights reflecting Phase 11B-4 Section 11:
# 1. tooth discoloration
# 2. caries
# 3. calculus
# 4. gingivitis
# 5. ulcer
CLASS_PRIORITY_ORDER = {
    "tooth discoloration": 5,
    "caries": 4,
    "calculus": 3,
    "gingivitis": 2,
    "ulcer": 1,
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def compute_file_sha256(filepath: Path) -> str:
    """Computes SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_dhash(img: Image.Image, hash_size: int = 8) -> int:
    """Computes 64-bit difference hash (dHash) for perceptual image comparison."""
    resized = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
    pixels = np.array(resized, dtype=np.int32)
    diff = pixels[:, 1:] > pixels[:, :-1]
    val = 0
    for bit in diff.flatten():
        val = (val << 1) | int(bit)
    return val


def hamming_distance(h1: int, h2: int) -> int:
    """Calculates bitwise Hamming distance between two integer hashes."""
    return bin(h1 ^ h2).count("1")


def parse_source_data_yaml(yaml_path: Path) -> dict[str, Any]:
    """Parses Penyakit Gigi Skripsi data.yaml and extracts class metadata."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"data.yaml not found at: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    names = data.get("names", [])
    if isinstance(names, dict):
        sorted_keys = sorted(int(k) for k in names.keys())
        names = [names[k] for k in sorted_keys]

    healthy_id: int | None = None
    calculus_id: int | None = None
    caries_id: int | None = None

    for idx, name in enumerate(names):
        norm = str(name).strip().lower()
        if norm in ("healthy", "healthy teeth", "healthy tooth"):
            healthy_id = idx
        elif norm in ("calculus", "tartar"):
            calculus_id = idx
        elif norm in ("caries", "cavity", "cavities"):
            caries_id = idx

    if healthy_id is None:
        raise ValueError(f"Could not identify healthy class in: {names}")

    return {
        "names": names,
        "healthy_id": healthy_id,
        "healthy_name": names[healthy_id],
        "calculus_id": calculus_id,
        "caries_id": caries_id,
        "roboflow": data.get("roboflow", {}),
        "license": data.get("roboflow", {}).get("license", "CC BY 4.0"),
        "url": data.get("roboflow", {}).get("url", ""),
        "project": data.get("roboflow", {}).get("project", ""),
        "workspace": data.get("roboflow", {}).get("workspace", ""),
    }


def find_healthy_only_images(
    dataset_dir: Path,
    healthy_id: int = 2,
    splits: list[str] | None = None,
) -> dict[str, Any]:
    """Scans all available splits and extracts strictly healthy-only images.
    
    Excludes any mixed annotations, disease-only annotations, or empty labels.
    """
    if splits is None:
        splits = ["train", "valid", "test"]

    healthy_only_list: list[dict[str, Any]] = []
    mixed_list: list[Path] = []
    disease_only_list: list[Path] = []
    empty_list: list[Path] = []
    total_images = 0
    split_counts: dict[str, dict[str, int]] = {}

    for split in splits:
        split_dir = dataset_dir / split
        img_dir = split_dir / "images" if (split_dir / "images").exists() else split_dir
        lbl_dir = split_dir / "labels" if (split_dir / "labels").exists() else split_dir

        if not img_dir.exists():
            continue

        split_total = 0
        split_h_only = 0
        split_mixed = 0
        split_dis_only = 0
        split_empty = 0

        with os.scandir(img_dir) as it:
            for entry in it:
                if entry.is_file() and os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
                    total_images += 1
                    split_total += 1
                    img_path = Path(entry.path)
                    lbl_path = lbl_dir / f"{img_path.stem}.txt"

                    if not lbl_path.exists():
                        empty_list.append(img_path)
                        split_empty += 1
                        continue

                    try:
                        content = lbl_path.read_text(encoding="utf-8").strip()
                    except Exception:
                        content = ""

                    if not content:
                        empty_list.append(img_path)
                        split_empty += 1
                        continue

                    class_ids = set()
                    box_count = 0
                    for line in content.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split()
                        if parts:
                            try:
                                cid = int(parts[0])
                                class_ids.add(cid)
                                box_count += 1
                            except ValueError:
                                pass

                    if not class_ids or box_count == 0:
                        empty_list.append(img_path)
                        split_empty += 1
                    elif class_ids == {healthy_id}:
                        healthy_only_list.append({
                            "path": img_path,
                            "filename": img_path.name,
                            "split": split,
                            "relative_source": f"{split}/images/{img_path.name}",
                            "healthy_box_count": box_count,
                        })
                        split_h_only += 1
                    elif healthy_id in class_ids and len(class_ids) > 1:
                        mixed_list.append(img_path)
                        split_mixed += 1
                    else:
                        disease_only_list.append(img_path)
                        split_dis_only += 1

        split_counts[split] = {
            "total": split_total,
            "healthy_only": split_h_only,
            "mixed": split_mixed,
            "disease_only": split_dis_only,
            "empty": split_empty,
        }

    healthy_only_list.sort(key=lambda x: (x["split"], x["filename"]))

    return {
        "total_images": total_images,
        "healthy_only": healthy_only_list,
        "healthy_only_count": len(healthy_only_list),
        "mixed_count": len(mixed_list),
        "disease_only_count": len(disease_only_list),
        "empty_count": len(empty_list),
        "split_counts": split_counts,
    }


def evaluate_image_quality(img_path: Path) -> dict[str, Any]:
    """Evaluates basic physical image quality: resolution, brightness, blur, overexposure.
    
    Returns metrics and quality_status (PASS, or FAIL_*).
    """
    try:
        with Image.open(img_path) as img:
            w, h = img.size
            if w < 128 or h < 128:
                return {
                    "width": w,
                    "height": h,
                    "brightness": 0.0,
                    "blur_score": 0.0,
                    "overexposure_ratio": 0.0,
                    "quality_status": "FAIL_TINY",
                    "quality_note": f"Image too small: {w}x{h}",
                }
            rgb = np.array(img.convert("RGB"))
    except Exception as exc:
        return {
            "width": 0,
            "height": 0,
            "brightness": 0.0,
            "blur_score": 0.0,
            "overexposure_ratio": 0.0,
            "quality_status": "FAIL_CORRUPT",
            "quality_note": f"Corrupt or unreadable image: {exc}",
        }

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    brightness = float(np.mean(gray))
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    overexposure_ratio = float(np.mean(gray > 250))

    # Strict physical unusable filters (Section 9):
    # Do NOT interpret clinical disease from image-quality metrics.
    # overexposure_ratio > 0.35 represents severe pixel blowout.
    # blur_score < 2.5 represents severe full-frame blur/defocus.
    if overexposure_ratio > 0.35:
        status = "FAIL_OVEREXPOSURE"
        note = f"Severe overexposure ({overexposure_ratio * 100:.1f}% pixels > 250)"
    elif blur_score < 2.5:
        status = "FAIL_BLUR"
        note = f"Severe blur (Laplacian variance {blur_score:.2f} < 2.5)"
    else:
        status = "PASS"
        note = "Passes basic physical quality checks"

    return {
        "width": w,
        "height": h,
        "brightness": round(brightness, 2),
        "blur_score": round(blur_score, 2),
        "overexposure_ratio": round(overexposure_ratio, 4),
        "quality_status": status,
        "quality_note": note,
    }


def perform_deduplication(
    items: list[dict[str, Any]],
    dhash_distance_threshold: int = 5,
) -> tuple[int, int]:
    """Identifies exact SHA-256 duplicates and near dHash duplicates across candidates.
    
    Populates duplicate_status, duplicate_group, sha256, and dhash fields in-place.
    """
    sha_map: dict[str, str] = {}
    dhash_entries: list[tuple[int, str]] = []  # (dhash_int, group_id)
    group_counter = 0

    exact_dup_count = 0
    near_dup_count = 0

    for item in items:
        p = Path(item["absolute_path"])
        sha = compute_file_sha256(p)
        item["sha256"] = sha

        # Exact duplicate check
        if sha in sha_map:
            item["duplicate_status"] = "EXACT_DUPLICATE"
            item["duplicate_group"] = sha_map[sha]
            exact_dup_count += 1
            continue

        # Compute perceptual dHash
        try:
            with Image.open(p) as img:
                dh = compute_dhash(img)
                item["dhash"] = f"{dh:016x}"
        except Exception:
            dh = 0
            item["dhash"] = "0000000000000000"

        # Check near duplicate against previous primary images
        matched_group = None
        for prev_dh, grp in dhash_entries:
            if hamming_distance(dh, prev_dh) <= dhash_distance_threshold:
                matched_group = grp
                break

        if matched_group is not None:
            item["duplicate_status"] = "NEAR_DUPLICATE"
            item["duplicate_group"] = matched_group
            near_dup_count += 1
        else:
            group_counter += 1
            grp_id = f"group_{group_counter:04d}"
            item["duplicate_status"] = "PRIMARY"
            item["duplicate_group"] = grp_id
            sha_map[sha] = grp_id
            dhash_entries.append((dh, grp_id))

    return exact_dup_count, near_dup_count


def calculate_fp_priority(detections: list[dict[str, Any]]) -> float:
    """Calculates candidate priority score according to Section 11 specifications:
    
    1. tooth discoloration
    2. caries
    3. calculus
    4. gingivitis
    5. ulcer
    Within class: highest confidence first + larger detection count + broader coverage.
    """
    if not detections:
        return 0.0

    # Sort detections so highest confidence is first
    detections.sort(key=lambda d: -d["confidence"])
    top_det = detections[0]
    top_cls = top_det["raw_class"]
    top_conf = top_det["confidence"]

    cls_weight = CLASS_PRIORITY_ORDER.get(top_cls, 1)

    # Coverage: aggregate normalized area of all predicted boxes
    total_area = 0.0
    for det in detections:
        bx = det.get("box_xyxyn", [0, 0, 0, 0])
        w = max(0.0, bx[2] - bx[0])
        h = max(0.0, bx[3] - bx[1])
        total_area += w * h

    score = (
        (cls_weight * 10.0)
        + (top_conf * 5.0)
        + min(len(detections) * 0.5, 3.0)
        + (total_area * 2.0)
    )
    return round(score, 3)


def run_mining_pipeline(
    dataset_dir: Path = Path("dataset/Penyakit Gigi Skripsi.yolov11"),
    model_path: Path = Path("services/teeth_analyzer/models/oral_disease/best.pt"),
    output_dir: Path = Path("dataset/final-healthy-negative-candidates"),
    original_benchmark_dir: Path | None = Path("dataset/oral-disease.yolov11"),
    min_confidence: float = 0.30,
    control_audit_sample_size: int = 50,
    top_fp_contact_sheet_cap: int = 120,
    seed: int = 42,
    model: Any | None = None,
) -> dict[str, Any]:
    """Executes the complete Phase 11B-4 large healthy-negative mining pipeline."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Parse data.yaml
    yaml_info = parse_source_data_yaml(dataset_dir / "data.yaml")
    healthy_id = yaml_info["healthy_id"]
    healthy_name = yaml_info["healthy_name"]

    print("=" * 70)
    print("PHASE 11B-4 FINAL: LARGE HEALTHY-NEGATIVE MINING")
    print("=" * 70)
    print(f"Dataset: {dataset_dir}")
    print(f"Classes: {yaml_info['names']}")
    print(f"Healthy class ID: {healthy_id} ('{healthy_name}')")
    print(f"Calculus class ID: {yaml_info['calculus_id']}")
    print(f"Caries class ID: {yaml_info['caries_id']}")
    print(f"License: {yaml_info['license']}")
    print(f"Roboflow project: {yaml_info['project']}")

    # 2. Extract healthy-only images across all splits
    print("\nScanning dataset for healthy-only images across train/valid/test ...", flush=True)
    classif = find_healthy_only_images(dataset_dir, healthy_id=healthy_id)
    healthy_items = classif["healthy_only"]

    print(f"Total dataset images: {classif['total_images']}")
    print(f"  Healthy-only images:  {classif['healthy_only_count']}")
    print(f"  Mixed-class images:   {classif['mixed_count']} [EXCLUDED]")
    print(f"  Disease-only images:  {classif['disease_only_count']} [EXCLUDED]")
    print(f"  Empty-label images:   {classif['empty_count']}")
    print("Split breakdown:")
    for spl, cnts in classif["split_counts"].items():
        print(f"  - {spl}: total={cnts['total']}, healthy_only={cnts['healthy_only']}, mixed={cnts['mixed']}, disease_only={cnts['disease_only']}")

    # 3. Load YOLO model
    if model is None:
        from ultralytics import YOLO
        print(f"\nLoading detector weights from {model_path} ...", flush=True)
        model = YOLO(str(model_path))

    # 4. Run local inference on ALL healthy-only images
    print(f"\nRunning inference on all {len(healthy_items)} healthy-only images (conf >= {min_confidence:.2f}) ...", flush=True)
    all_evaluated: list[dict[str, Any]] = []
    fp_class_counter = Counter()

    for item in healthy_items:
        img_p = item["path"]
        abs_p = img_p.resolve()

        # Physical quality metrics
        q_metrics = evaluate_image_quality(img_p)

        # Model inference
        try:
            results = model.predict(source=str(img_p), conf=min_confidence, iou=0.45, verbose=False)
            res = results[0]
            boxes = res.boxes
        except Exception as exc:
            print(f"Inference failed on {img_p.name}: {exc}", file=sys.stderr)
            boxes = None

        detections = []
        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.cpu().numpy()
            xyxyn = boxes.xyxyn.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            clss = boxes.cls.cpu().numpy()

            for j in range(len(clss)):
                c_id = int(clss[j])
                raw_cls = DAANTSHAANT_CLASSES.get(c_id, f"class_{c_id}")
                norm_cls = NORMALIZED_NAMES.get(raw_cls, raw_cls)
                c_conf = round(float(confs[j]), 4)
                bx_xyxy = [round(float(v), 2) for v in xyxy[j]]
                bx_xyxyn = [round(float(v), 4) for v in xyxyn[j]]

                fp_class_counter[raw_cls] += 1
                detections.append({
                    "class_id": c_id,
                    "raw_class": raw_cls,
                    "normalized_finding": norm_cls,
                    "confidence": c_conf,
                    "box_xyxy": bx_xyxy,
                    "box_xyxyn": bx_xyxyn,
                })

            detections.sort(key=lambda d: -d["confidence"])
            top_det = detections[0]
            candidate_type = "MODEL_FALSE_POSITIVE"
            top_class = top_det["raw_class"]
            top_conf = top_det["confidence"]
            priority = calculate_fp_priority(detections)
        else:
            candidate_type = "CLEAN_CONTROL"
            top_class = "none"
            top_conf = 0.0
            priority = 0.0

        all_evaluated.append({
            "filename": img_p.name,
            "source_path": item["relative_source"],
            "absolute_path": str(abs_p),
            "source_split": item["split"],
            "source_healthy_class": healthy_name,
            "candidate_type": candidate_type,
            "top_predicted_class": top_class,
            "top_confidence": top_conf,
            "detection_count": len(detections),
            "all_predictions": json.dumps(detections),
            "priority": priority,
            "detections": detections,
            # Quality fields
            "quality_status": q_metrics["quality_status"],
            "quality_note": q_metrics["quality_note"],
            "image_width": q_metrics["width"],
            "image_height": q_metrics["height"],
            "brightness": q_metrics["brightness"],
            "blur_score": q_metrics["blur_score"],
            "overexposure_ratio": q_metrics["overexposure_ratio"],
        })

    # 5. Deduplication
    print("\nComputing SHA-256 and perceptual dHash for deduplication ...", flush=True)
    exact_dups, near_dups = perform_deduplication(all_evaluated, dhash_distance_threshold=5)
    print(f"  Exact duplicates detected: {exact_dups}")
    print(f"  Near duplicates detected:  {near_dups}")

    # 6. Assign review_status according to Section 11, 12, 14
    for c in all_evaluated:
        is_fp = c["candidate_type"] == "MODEL_FALSE_POSITIVE"
        q_pass = c["quality_status"] == "PASS"
        not_dup = c["duplicate_status"] == "PRIMARY"

        if is_fp:
            if not q_pass:
                c["review_status"] = f"REJECT_{c['quality_status']}"
                c["review_note"] = f"Quality filter failed: {c['quality_note']}"
            elif c["duplicate_status"] == "EXACT_DUPLICATE":
                c["review_status"] = "REJECT_DUPLICATE"
                c["review_note"] = f"Exact duplicate of group {c['duplicate_group']}"
            else:
                c["review_status"] = "UNREVIEWED"
                c["review_note"] = f"Flagged {c['detection_count']} false-positive box(es) as {c['top_predicted_class']} (conf {c['top_confidence']:.2f})."
        else:
            # CLEAN_CONTROL
            if not q_pass:
                c["review_status"] = f"REJECT_{c['quality_status']}"
                c["review_note"] = f"Quality filter failed: {c['quality_note']}"
            elif c["duplicate_status"] == "EXACT_DUPLICATE":
                c["review_status"] = "REJECT_DUPLICATE"
                c["review_note"] = f"Exact duplicate of group {c['duplicate_group']}"
            elif c["duplicate_status"] == "NEAR_DUPLICATE":
                c["review_status"] = "REJECT_NEAR_DUPLICATE"
                c["review_note"] = f"Near duplicate variant of group {c['duplicate_group']}"
            else:
                c["review_status"] = "AUTO_ELIGIBLE_CONTROL"
                c["review_note"] = "Zero detections >= 0.30, passed physical quality filters, unique."

    # 7. Partition false positives and clean controls
    fp_candidates = [c for c in all_evaluated if c["candidate_type"] == "MODEL_FALSE_POSITIVE"]
    control_candidates = [c for c in all_evaluated if c["candidate_type"] == "CLEAN_CONTROL"]

    # Sort false positives by priority desc, then top confidence desc, then detection count desc
    fp_candidates.sort(key=lambda c: (-c["priority"], -c["top_confidence"], -c["detection_count"]))

    # Sort controls deterministically by filename
    control_candidates.sort(key=lambda c: (c["source_split"], c["filename"]))

    # 8. Leakage check against original oral-disease benchmark dataset (Section 22)
    if original_benchmark_dir and original_benchmark_dir.exists():
        print("\nVerifying benchmark isolation against original valid & test splits ...", flush=True)
        valid_dir = original_benchmark_dir / "valid" / "images"
        test_dir = original_benchmark_dir / "test" / "images"
        train_dir = original_benchmark_dir / "train" / "images"

        benchmark_valid_hashes = {compute_file_sha256(p): p.name for p in valid_dir.glob("*.*")} if valid_dir.exists() else {}
        benchmark_test_hashes = {compute_file_sha256(p): p.name for p in test_dir.glob("*.*")} if test_dir.exists() else {}
        benchmark_train_hashes = {compute_file_sha256(p): p.name for p in train_dir.glob("*.*")} if train_dir.exists() else {}

        train_dup_count = 0
        for c in all_evaluated:
            c_sha = c["sha256"]
            if c_sha in benchmark_valid_hashes:
                raise RuntimeError(
                    f"[BENCHMARK DATA LEAKAGE] Healthy candidate '{c['filename']}' matches "
                    f"original benchmark VALID image '{benchmark_valid_hashes[c_sha]}'! Aborting."
                )
            if c_sha in benchmark_test_hashes:
                raise RuntimeError(
                    f"[BENCHMARK DATA LEAKAGE] Healthy candidate '{c['filename']}' matches "
                    f"original benchmark TEST image '{benchmark_test_hashes[c_sha]}'! Aborting."
                )
            if c_sha in benchmark_train_hashes:
                train_dup_count += 1

        print(f"  Zero overlap with original VALID ({len(benchmark_valid_hashes)} images) - PASSED.")
        print(f"  Zero overlap with original TEST ({len(benchmark_test_hashes)} images) - PASSED.")
        if train_dup_count > 0:
            print(f"  Notice: {train_dup_count} images share identical hashes with original train split.")

    # Combine all candidates in review order: False Positives first, Controls next
    ordered_all_candidates = fp_candidates + control_candidates
    for idx, c in enumerate(ordered_all_candidates, 1):
        c["tile_number"] = idx

    # 9. Create deterministic sample of 50 CLEAN_CONTROL images for manual audit (Section 13)
    eligible_controls = [c for c in control_candidates if c["review_status"] == "AUTO_ELIGIBLE_CONTROL"]
    rng = random.Random(seed)
    if len(eligible_controls) > control_audit_sample_size:
        control_audit_sample = rng.sample(eligible_controls, control_audit_sample_size)
        control_audit_sample.sort(key=lambda c: c["filename"])
    else:
        control_audit_sample = list(eligible_controls)

    for idx, c in enumerate(control_audit_sample, 1):
        c["control_audit_tile_number"] = idx

    # 10. Write review.csv
    csv_path = output_dir / "review.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "tile_number",
            "filename",
            "source_path",
            "source_split",
            "candidate_type",
            "top_predicted_class",
            "top_confidence",
            "detection_count",
            "priority",
            "review_status",
            "duplicate_status",
            "duplicate_group",
            "quality_status",
            "image_width",
            "image_height",
            "brightness",
            "blur_score",
            "overexposure_ratio",
            "sha256",
            "dhash",
            "all_predictions",
            "review_note",
        ])
        for c in ordered_all_candidates:
            writer.writerow([
                c["tile_number"],
                c["filename"],
                c["source_path"],
                c["source_split"],
                c["candidate_type"],
                c["top_predicted_class"],
                f"{c['top_confidence']:.4f}",
                c["detection_count"],
                f"{c['priority']:.3f}",
                c["review_status"],
                c["duplicate_status"],
                c["duplicate_group"],
                c["quality_status"],
                c["image_width"],
                c["image_height"],
                f"{c['brightness']:.2f}",
                f"{c['blur_score']:.2f}",
                f"{c['overexposure_ratio']:.4f}",
                c["sha256"],
                c.get("dhash", ""),
                c["all_predictions"],
                c["review_note"],
            ])

    # 11. Write candidates.json
    json_path = output_dir / "candidates.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "dataset": str(dataset_dir),
            "source_classes": yaml_info["names"],
            "healthy_class_id": healthy_id,
            "min_confidence": min_confidence,
            "total_healthy_only_evaluated": len(healthy_items),
            "false_positives_count": len(fp_candidates),
            "clean_controls_count": len(control_candidates),
            "auto_eligible_controls_count": len(eligible_controls),
            "fp_class_distribution": dict(fp_class_counter),
            "candidates": ordered_all_candidates,
        }, f, indent=2)

    # 12. Write audit.json
    quality_rejects = sum(1 for c in all_evaluated if c["quality_status"] != "PASS")
    discoloration_fps = sum(1 for c in fp_candidates if c["top_predicted_class"] == "tooth discoloration")
    caries_fps = sum(1 for c in fp_candidates if c["top_predicted_class"] == "caries")
    calculus_fps = sum(1 for c in fp_candidates if c["top_predicted_class"] == "calculus")
    gingivitis_fps = sum(1 for c in fp_candidates if c["top_predicted_class"] == "gingivitis")
    ulcer_fps = sum(1 for c in fp_candidates if c["top_predicted_class"] == "ulcer")

    audit_summary = {
        "dataset_name": "Penyakit Gigi Skripsi.yolov11",
        "roboflow_project": yaml_info["project"],
        "roboflow_url": yaml_info["url"],
        "license": yaml_info["license"],
        "source_classes": yaml_info["names"],
        "healthy_class_id": healthy_id,
        "calculus_class_id": yaml_info["calculus_id"],
        "caries_class_id": yaml_info["caries_id"],
        "total_source_images": classif["total_images"],
        "train_images": classif["split_counts"].get("train", {}).get("total", 0),
        "valid_images": classif["split_counts"].get("valid", {}).get("total", 0),
        "test_images": classif["split_counts"].get("test", {}).get("total", 0),
        "healthy_only_images": classif["healthy_only_count"],
        "unique_healthy_only_images": len(set(c["sha256"] for c in all_evaluated)),
        "mixed_images_excluded": classif["mixed_count"],
        "disease_only_images_excluded": classif["disease_only_count"],
        "empty_label_images_excluded": classif["empty_count"],
        "fp_images_ge_030": len(fp_candidates),
        "clean_control_images": len(control_candidates),
        "auto_eligible_controls": len(eligible_controls),
        "tooth_discoloration_fp_images": discoloration_fps,
        "caries_fp_images": caries_fps,
        "calculus_fp_images": calculus_fps,
        "gingivitis_fp_images": gingivitis_fps,
        "ulcer_fp_images": ulcer_fps,
        "fp_class_detections": dict(fp_class_counter),
        "exact_duplicates": exact_dups,
        "near_duplicates": near_dups,
        "quality_rejects": quality_rejects,
        "control_audit_sample_size": len(control_audit_sample),
        "existing_trusted_negatives": 14,
        "potential_final_healthy_pool": 14 + len(fp_candidates) + len(eligible_controls),
    }

    audit_path = output_dir / "audit.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit_summary, f, indent=2)

    print(f"\n[✓] Generated candidate files:\n  CSV:   {csv_path}\n  JSON:  {json_path}\n  AUDIT: {audit_path}")
    print(f"\nSummary:")
    print(f"  False positives (MODEL_FALSE_POSITIVE): {len(fp_candidates)}")
    print(f"  Clean controls (CLEAN_CONTROL):         {len(control_candidates)}")
    print(f"  Auto-eligible clean controls:           {len(eligible_controls)}")
    print(f"  Quality rejections:                     {quality_rejects}")
    print(f"  Exact duplicates:                       {exact_dups}")
    print(f"  Near duplicates:                        {near_dups}")

    return {
        "audit_summary": audit_summary,
        "fp_candidates": fp_candidates,
        "control_candidates": control_candidates,
        "eligible_controls": eligible_controls,
        "control_audit_sample": control_audit_sample,
        "ordered_all_candidates": ordered_all_candidates,
        "csv_path": csv_path,
        "json_path": json_path,
        "audit_path": audit_path,
    }


def render_contact_sheets(
    items: list[dict[str, Any]],
    output_prefix: str,
    output_dir: Path,
    cols: int = 4,
    rows: int = 4,
    tile_size: tuple[int, int] = (360, 360),
    is_control_audit: bool = False,
) -> list[Path]:
    """Renders visual contact sheets for manual visual review (16 tiles per sheet max)."""
    if not items:
        return []

    per_sheet = cols * rows
    num_sheets = math.ceil(len(items) / per_sheet)
    sheet_paths = []

    COLORS = {
        "calculus": (230, 126, 34),          # Orange
        "caries": (231, 76, 60),             # Red
        "gingivitis": (155, 89, 182),        # Purple
        "tooth discoloration": (241, 196, 15), # Yellow
        "ulcer": (52, 152, 219),             # Blue
    }

    try:
        font_header = ImageFont.truetype("arial.ttf", 13)
        font_box = ImageFont.truetype("arial.ttf", 11)
    except Exception:
        font_header = ImageFont.load_default()
        font_box = ImageFont.load_default()

    for s_idx in range(num_sheets):
        sheet_items = items[s_idx * per_sheet : (s_idx + 1) * per_sheet]
        sheet_w = cols * tile_size[0]
        sheet_h = rows * tile_size[1]
        sheet_img = Image.new("RGB", (sheet_w, sheet_h), color=(18, 22, 28))
        draw_sheet = ImageDraw.Draw(sheet_img)

        for t_idx, item in enumerate(sheet_items):
            c_col = t_idx % cols
            c_row = t_idx // cols
            x_offset = c_col * tile_size[0]
            y_offset = c_row * tile_size[1]

            img_p = Path(item["absolute_path"])
            try:
                with Image.open(img_p) as raw_img:
                    raw_rgb = raw_img.convert("RGB")
                    orig_w, orig_h = raw_rgb.size
                    tile_img = raw_rgb.resize(tile_size, Image.Resampling.BILINEAR)
            except Exception:
                tile_img = Image.new("RGB", tile_size, color=(40, 40, 40))
                orig_w, orig_h = tile_size

            tile_draw = ImageDraw.Draw(tile_img)
            scale_x = tile_size[0] / max(1, orig_w)
            scale_y = tile_size[1] / max(1, orig_h)

            is_fp = item["candidate_type"] == "MODEL_FALSE_POSITIVE"

            if is_fp:
                for det in item.get("detections", []):
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

            # Header overlay
            if is_control_audit:
                tile_num = item.get("control_audit_tile_number", t_idx + 1)
                header_text = f"Audit #{tile_num:02d} [CONTROL] {item['filename'][:16]} | 0 det"
                hdr_bg = (30, 130, 70)
            elif is_fp:
                tile_num = item.get("tile_number", s_idx * per_sheet + t_idx + 1)
                header_text = f"#{tile_num} [FP] {item['filename'][:14]} | {item['top_predicted_class']} ({item['top_confidence']:.2f})"
                hdr_bg = (180, 40, 40)
            else:
                tile_num = item.get("tile_number", s_idx * per_sheet + t_idx + 1)
                header_text = f"#{tile_num} [CONTROL] {item['filename'][:14]} | 0 det"
                hdr_bg = (40, 110, 140)

            tile_draw.rectangle([0, 0, tile_size[0], 22], fill=hdr_bg)
            tile_draw.text((4, 4), header_text, fill=(255, 255, 255), font=font_header)

            sheet_img.paste(tile_img, (x_offset, y_offset))
            draw_sheet.rectangle([x_offset, y_offset, x_offset + tile_size[0], y_offset + tile_size[1]], outline=(60, 70, 80), width=1)

        sheet_file = output_dir / f"{output_prefix}_{s_idx + 1:02d}.jpg"
        sheet_img.save(sheet_file, quality=90)
        sheet_paths.append(sheet_file)
        print(f"  Saved contact sheet: {sheet_file}")

    return sheet_paths


def main():
    parser = argparse.ArgumentParser(description="Mine large healthy negative pool and prepare v2 candidates (Phase 11B-4 FINAL).")
    parser.add_argument("--dataset", type=str, default="dataset/Penyakit Gigi Skripsi.yolov11")
    parser.add_argument("--model", type=str, default="services/teeth_analyzer/models/oral_disease/best.pt")
    parser.add_argument("--output-dir", type=str, default="dataset/final-healthy-negative-candidates")
    parser.add_argument("--original-dataset", type=str, default="dataset/oral-disease.yolov11")
    parser.add_argument("--min-confidence", type=float, default=0.30)
    parser.add_argument("--control-audit-size", type=int, default=50)
    parser.add_argument("--top-fp-cap", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-contact-sheets", action="store_true")

    args = parser.parse_args()

    mining_res = run_mining_pipeline(
        dataset_dir=Path(args.dataset),
        model_path=Path(args.model),
        output_dir=Path(args.output_dir),
        original_benchmark_dir=Path(args.original_dataset) if args.original_dataset else None,
        min_confidence=args.min_confidence,
        control_audit_sample_size=args.control_audit_size,
        top_fp_contact_sheet_cap=args.top_fp_cap,
        seed=args.seed,
    )

    if not args.no_contact_sheets:
        out_d = Path(args.output_dir)
        print("\nRendering False-Positive Contact Sheets (Top 120 max) ...")
        top_fps = mining_res["fp_candidates"][:args.top_fp_cap]
        render_contact_sheets(
            items=top_fps,
            output_prefix="contact_sheet_fp",
            output_dir=out_d,
            cols=4,
            rows=4,
        )

        print("\nRendering 50-Image Control Audit Contact Sheets (seed 42) ...")
        render_contact_sheets(
            items=mining_res["control_audit_sample"],
            output_prefix="contact_sheet_control_audit",
            output_dir=out_d,
            cols=4,
            rows=4,
            is_control_audit=True,
        )

    print("\n[✓] Phase 11B-4 Mining Pipeline execution finished.")


if __name__ == "__main__":
    main()
