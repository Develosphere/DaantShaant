"""Prepare YOLO v2 Dataset with Nathan-Approved Hard Negatives (Phase 11B-2).

Merges the original YOLO dataset with approved hard-negative images into:
dataset/oral-disease-v2.yolov11/

CRITICAL RULES (Phase 11B-2):
1. V2 train:
   - Original TRAIN
   + Nathan-approved hard negatives (review_status == 'ACCEPT_NEGATIVE')
2. V2 valid:
   - Original VALID unchanged! (Zero leakage into validation)
3. V2 test:
   - Original TEST unchanged! (Zero leakage into test)
4. Hard Negative Oversampling:
   - Controlled repetition via `--negative-repeat N` (default: 1, recommended: 2).
   - Generates unique copies (e.g. rep0_neg_*, rep1_neg_*) with matching 0-byte labels.
5. Strict Leakage Protection:
   - Prevents original valid / test images from entering train.
   - Calculates MD5 / SHA-256 hashes to assert split isolation.
   - Fails loudly on any cross-split leakage.
6. Original dataset is NEVER mutated.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def compute_file_hash(filepath: Path) -> str:
    """Computes SHA-256 hash of a file for exact split-leakage checking."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def resolve_negative_path(
    filename: str,
    source_path_str: str,
    review_csv_path: Path,
    original_dataset_dir: Path,
) -> Path:
    """Resolves negative image path across potential repository and dataset roots."""
    p = Path(source_path_str) if source_path_str else Path(filename)
    if p.is_absolute() and p.exists():
        return p.resolve()

    candidates = [
        Path.cwd() / p,
        Path.cwd() / "dataset" / p,
        original_dataset_dir.parent / p,
        original_dataset_dir / p,
        review_csv_path.parent / p,
        review_csv_path.parent / "images" / filename,
        Path.cwd() / "dataset" / "Dental Data Set.yolov11" / "train" / "images" / filename,
        Path.cwd() / "dataset" / "oral-disease.yolov11" / "train" / "images" / filename,
        original_dataset_dir / "train" / "images" / filename,
    ]
    for cand in candidates:
        if cand.exists():
            return cand.resolve()

    # Search in dataset directory if needed
    dataset_root = Path.cwd() / "dataset"
    if dataset_root.exists():
        matches = list(dataset_root.rglob(filename))
        if matches:
            return matches[0].resolve()

    return p.resolve()


def load_approved_negatives_from_review_csv(
    review_csv_path: Path,
    original_dataset_dir: Path,
    include_audited_controls: bool = False,
) -> list[tuple[str, Path]]:
    """Loads approved hard negatives from review.csv.
    
    Always accepts review_status == 'ACCEPT_NEGATIVE'.
    If include_audited_controls is True, ALSO accepts review_status == 'AUTO_ELIGIBLE_CONTROL'.
    """
    if not review_csv_path.exists():
        raise FileNotFoundError(f"Review CSV not found: {review_csv_path}")

    accepted_statuses = {"ACCEPT_NEGATIVE"}
    if include_audited_controls:
        accepted_statuses.add("AUTO_ELIGIBLE_CONTROL")

    approved = []
    with open(review_csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = row.get("review_status", "").strip().upper()
            if status in accepted_statuses:
                filename = row.get("filename", "").strip()
                if not filename:
                    continue
                source_path_str = row.get("source_path", "").strip()
                resolved_p = resolve_negative_path(filename, source_path_str, review_csv_path, original_dataset_dir)

                if not resolved_p.exists():
                    raise FileNotFoundError(f"Approved negative file does not exist: {resolved_p} (filename: {filename})")
                approved.append((filename, resolved_p))

    return approved



def load_raw_hard_negatives_from_dir(hard_neg_dir: Path) -> list[tuple[str, Path]]:
    """Fallback: loads images directly from a hard-negatives directory if provided."""
    images_dir = hard_neg_dir / "images" if (hard_neg_dir / "images").exists() else hard_neg_dir
    found = []
    if images_dir.exists():
        with os.scandir(images_dir) as it:
            for entry in it:
                if entry.is_file() and os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
                    found.append((entry.name, Path(entry.path).resolve()))
    found.sort(key=lambda x: x[0])
    return found


def prepare_v2_dataset(
    original_dataset: Path,
    *args: Any,
    v2_output_dir: Path | None = None,
    review_csv: Path | str | list[Path | str] | None = None,
    hard_negatives_dir: Path | None = None,
    negative_repeat: int = 1,
    include_audited_controls: bool = False,
    seed: int = 42,
    dry_run: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    # Handle positional arguments from older callers:
    # Phase 11B-1 called: prepare_v2_dataset(orig_dir, hard_dir, v2_dir, seed=42)
    # Phase 11B-2 calls: prepare_v2_dataset(orig_dir, v2_dir, review_csv=...)
    if len(args) == 2 and v2_output_dir is None:
        # (orig, hard_neg_dir, v2_out_dir)
        hard_negatives_dir = Path(args[0])
        v2_output_dir = Path(args[1])
    elif len(args) == 1 and v2_output_dir is None:
        v2_output_dir = Path(args[0])

    if v2_output_dir is None:
        v2_output_dir = Path("dataset/oral-disease-v2.yolov11")

    if not original_dataset.exists():
        raise FileNotFoundError(f"Original dataset not found at: {original_dataset}")

    if v2_output_dir.resolve() == original_dataset.resolve():
        raise ValueError("v2_output_dir cannot be the same as original_dataset! Never mutate the original dataset.")

    if negative_repeat < 1:
        raise ValueError(f"negative_repeat must be >= 1, got {negative_repeat}")

    # 1. Collect approved negatives from one or more review CSVs
    approved_negatives: list[tuple[str, Path]] = []
    seen_hashes: set[str] = set()
    source_methods: list[str] = []

    # Normalize review_csv input into a list of Paths
    csv_paths: list[Path] = []
    if review_csv is not None:
        if isinstance(review_csv, (list, tuple)):
            csv_paths = [Path(p) for p in review_csv if p]
        else:
            csv_paths = [Path(review_csv)]
    elif hard_negatives_dir is None:
        # Check defaults: existing review_ai_recommended / hard-negative review and healthy reviews
        candidate_defaults = [
            Path("dataset/review_ai_recommended.csv"),
            Path("dataset/review_healthy_ai_recommended.csv"),
            Path("dataset/hard-negative-candidates/review.csv"),
            Path("dataset/healthy-negative-candidates/review.csv"),
            Path("dataset/final-healthy-negative-candidates/review.csv"),
        ]
        for cd in candidate_defaults:
            if cd.exists():
                csv_paths.append(cd)

    if csv_paths:
        for cp in csv_paths:
            if not cp.exists():
                print(f"[!] Warning: Specified review CSV does not exist: {cp}", file=sys.stderr)
                continue
            loaded = load_approved_negatives_from_review_csv(
                cp, original_dataset, include_audited_controls=include_audited_controls
            )
            added_from_csv = 0
            for fname, fpath in loaded:
                f_hash = compute_file_hash(fpath)
                if f_hash not in seen_hashes:
                    seen_hashes.add(f_hash)
                    approved_negatives.append((fname, fpath))
                    added_from_csv += 1
            source_methods.append(f"{cp} ({added_from_csv} approved)")
    elif hard_negatives_dir is not None:
        raw_loaded = load_raw_hard_negatives_from_dir(Path(hard_negatives_dir))
        for fname, fpath in raw_loaded:
            f_hash = compute_file_hash(fpath)
            if f_hash not in seen_hashes:
                seen_hashes.add(f_hash)
                approved_negatives.append((fname, fpath))
        source_methods.append(f"directory ({hard_negatives_dir})")
    else:
        default_dir = Path("dataset/hard-negatives")
        if default_dir.exists():
            raw_loaded = load_raw_hard_negatives_from_dir(default_dir)
            for fname, fpath in raw_loaded:
                f_hash = compute_file_hash(fpath)
                if f_hash not in seen_hashes:
                    seen_hashes.add(f_hash)
                    approved_negatives.append((fname, fpath))
            source_methods.append(f"default directory ({default_dir})")

    source_method = "; ".join(source_methods) if source_methods else "none"
    print(f"[{source_method}] Identified {len(approved_negatives)} approved hard-negative images.")
    print(f"Oversampling rate: {negative_repeat}x")
    effective_negative_count = len(approved_negatives) * negative_repeat
    print(f"Effective negative training instances to add to v2 train: {effective_negative_count}")

    # 2. Build hash sets of valid, test, and train splits to strictly prevent leakage and check duplicates
    print("Hashing untouched valid and test splits for leakage protection ...", flush=True)
    valid_hashes: dict[str, str] = {}
    test_hashes: dict[str, str] = {}
    train_hashes: dict[str, str] = {}

    for split, h_dict in [("valid", valid_hashes), ("test", test_hashes), ("train", train_hashes)]:
        s_dir = original_dataset / split
        img_dir = s_dir / "images" if (s_dir / "images").exists() else s_dir
        if img_dir.exists():
            with os.scandir(img_dir) as it:
                for entry in it:
                    if entry.is_file() and os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
                        h = compute_file_hash(Path(entry.path))
                        h_dict[h] = entry.name

    print(f"  Hashed {len(valid_hashes)} valid images and {len(test_hashes)} test images.")

    # Check that NO approved hard negative matches valid or test hashes (ABORT on match)
    train_dup_count = 0
    for fname, fpath in approved_negatives:
        neg_hash = compute_file_hash(fpath)
        if neg_hash in valid_hashes:
            raise RuntimeError(
                f"[DATA LEAKAGE ERROR] Hard-negative candidate '{fname}' ({fpath}) "
                f"matches valid split image '{valid_hashes[neg_hash]}'! "
                f"Validation set negatives must remain completely isolated."
            )
        if neg_hash in test_hashes:
            raise RuntimeError(
                f"[DATA LEAKAGE ERROR] Hard-negative candidate '{fname}' ({fpath}) "
                f"matches test split image '{test_hashes[neg_hash]}'! "
                f"Test set negatives must remain completely isolated."
            )
        if neg_hash in train_hashes:
            print(f"[!] Warning: Selected negative '{fname}' matches existing train image '{train_hashes[neg_hash]}'.", file=sys.stderr)
            train_dup_count += 1

    # Calculate class balance
    original_train_count = len(train_hashes)
    v2_train_total = original_train_count + effective_negative_count
    negative_fraction = (effective_negative_count / v2_train_total * 100) if v2_train_total > 0 else 0.0
    print(f"Negative training balance: {effective_negative_count}/{v2_train_total} ({negative_fraction:.2f}%)")
    if negative_fraction > 18.0:
        print(f"[!] WARNING: Negative training percentage ({negative_fraction:.2f}%) exceeds 18% target threshold!", file=sys.stderr)

    recommended_repeat = 1 if len(approved_negatives) >= 500 else (1 if len(approved_negatives) >= 200 else negative_repeat)

    summary = {
        "original_dataset": str(original_dataset),
        "v2_output_dir": str(v2_output_dir),
        "approved_negatives_unique": len(approved_negatives),
        "negative_repeat": negative_repeat,
        "recommended_repeat": recommended_repeat,
        "effective_negatives_added_to_train": effective_negative_count,
        "original_train_count": original_train_count,
        "v2_train_total": v2_train_total,
        "negative_fraction_percentage": round(negative_fraction, 2),
        "negative_balance_exceeds_threshold": negative_fraction > 18.0,
        "include_audited_controls": include_audited_controls,
        "train_duplicates_detected": train_dup_count,
        "validation_leakage_detected": False,
        "test_leakage_detected": False,
        "validation_set_modified": False,
        "test_set_modified": False,
        "dry_run": dry_run,
    }

    if dry_run:
        print("[Dry-run] Validation checks passed. Zero leakage detected. No files written.")
        return summary

    v2_output_dir.mkdir(parents=True, exist_ok=True)

    # 3. Process splits
    for split in ["train", "valid", "test"]:
        src_split = original_dataset / split
        dst_split = v2_output_dir / split
        dst_images = dst_split / "images"
        dst_labels = dst_split / "labels"

        dst_images.mkdir(parents=True, exist_ok=True)
        dst_labels.mkdir(parents=True, exist_ok=True)

        src_img_dir = src_split / "images" if (src_split / "images").exists() else src_split
        src_lbl_dir = src_split / "labels" if (src_split / "labels").exists() else src_split

        copied_images = 0
        copied_labels = 0

        if src_split.exists():
            # Copy original images
            if src_img_dir.exists():
                with os.scandir(src_img_dir) as it:
                    for entry in it:
                        if entry.is_file() and os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
                            dst_path = dst_images / entry.name
                            if not dst_path.exists():
                                shutil.copy2(entry.path, dst_path)
                            copied_images += 1

            # Copy original labels
            if src_lbl_dir.exists():
                with os.scandir(src_lbl_dir) as it:
                    for entry in it:
                        if entry.is_file() and entry.name.endswith(".txt"):
                            dst_path = dst_labels / entry.name
                            if not dst_path.exists():
                                shutil.copy2(entry.path, dst_path)
                            copied_labels += 1

        print(f"[{split}] Copied {copied_images} images and {copied_labels} labels from original dataset.")

        # ONLY TRAIN split receives hard negatives (Phase 11B-2 Section 4, 11, 12)
        if split == "train":
            print(f"Adding {effective_negative_count} approved hard negatives to v2 train split ...", flush=True)
            added_count = 0
            for rep_idx in range(negative_repeat):
                prefix = f"rep{rep_idx}_" if negative_repeat > 1 else ""
                for fname, fpath in approved_negatives:
                    stem = Path(fname).stem
                    ext = Path(fname).suffix

                    dst_img_name = f"{prefix}neg_{stem}{ext}"
                    dst_lbl_name = f"{prefix}neg_{stem}.txt"

                    dst_img_path = dst_images / dst_img_name
                    dst_lbl_path = dst_labels / dst_lbl_name

                    # Copy image
                    shutil.copy2(fpath, dst_img_path)
                    # Write empty 0-byte label file
                    dst_lbl_path.write_text("", encoding="utf-8")
                    added_count += 1

            print(f"Successfully added {added_count} negative instances to v2 train.")
        else:
            print(f"[{split}] Kept 100% UNTOUCHED and identical to original benchmark.")

    # 4. Generate data.yaml
    data_yaml_path = v2_output_dir / "data.yaml"
    data_yaml_content = (
        "train: train/images\n"
        "val: valid/images\n"
        "test: test/images\n"
        "\n"
        "nc: 5\n"
        "names: ['calculus', 'caries', 'gingivitis', 'tooth discoloration', 'ulcer']\n"
        "\n"
        "# DaantShaant Oral Disease v2 Dataset with Approved Hard Negatives\n"
        f"# Unique approved negatives: {len(approved_negatives)}, repeat: {negative_repeat}x\n"
    )
    data_yaml_path.write_text(data_yaml_content, encoding="utf-8")
    print(f"v2 data.yaml created at: {data_yaml_path.resolve()}", flush=True)

    return summary


def main():
    parser = argparse.ArgumentParser(description="Prepare YOLO v2 dataset with approved hard negatives.")
    parser.add_argument("--original", type=str, default="dataset/oral-disease.yolov11")
    parser.add_argument("--output", type=str, default="dataset/oral-disease-v2.yolov11")
    parser.add_argument(
        "--review-csv",
        action="append",
        dest="review_csvs",
        help="Path to review CSV(s) with review_status (can specify multiple times)",
    )
    parser.add_argument("--hard-negatives-dir", type=str, default=None)
    parser.add_argument("--negative-repeat", type=int, default=2, help="Repetition factor for approved negatives (default: 2)")
    parser.add_argument(
        "--include-audited-controls",
        action="store_true",
        help="Include AUTO_ELIGIBLE_CONTROL images from audited clean control pools in v2 training",
    )
    parser.add_argument("--dry-run", action="store_true", help="Perform verification without copying files")

    args = parser.parse_args()

    hard_dir_p = Path(args.hard_negatives_dir) if args.hard_negatives_dir else None

    summary = prepare_v2_dataset(
        original_dataset=Path(args.original),
        v2_output_dir=Path(args.output),
        review_csv=args.review_csvs,
        hard_negatives_dir=hard_dir_p,
        negative_repeat=args.negative_repeat,
        include_audited_controls=args.include_audited_controls,
        dry_run=args.dry_run,
    )

    print("\n--- Summary ---")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

