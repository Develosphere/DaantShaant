"""Test suite for Phase 11B-4.1: Modal v2 Dataset Extraction & Path Resolution.

Tests:
1. CASE A: Flat ZIP layout (train/images, valid/images, test/images directly at root)
2. CASE B: Nested ZIP layout (some-folder/train/images, some-folder/valid/images, some-folder/test/images)
3. Failure when valid/images is absent (find_dataset_root raises RuntimeError)
4. Split count verification (verify_dataset_counts succeeds with non-zero images/labels, fails when any count is 0)
5. Clean data.yaml rewriting (generate_v2_data_yaml writes absolute paths, correct classes 0-4, and no '../' paths)
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import zipfile

import pytest
import yaml

from scripts.modal_train_yolo_v2 import (
    CLASS_NAMES,
    find_dataset_root,
    generate_v2_data_yaml,
    verify_dataset_counts,
)


def _create_dummy_split_files(base_dir: Path, split_name: str, num_images: int = 3, num_labels: int = 3):
    img_dir = base_dir / split_name / "images"
    lbl_dir = base_dir / split_name / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    for i in range(num_images):
        (img_dir / f"{split_name}_{i}.jpg").write_bytes(b"dummy_image_bytes")
    for i in range(num_labels):
        (lbl_dir / f"{split_name}_{i}.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")


def test_find_dataset_root_case_a_flat(tmp_path: Path):
    """CASE A: Flat ZIP layout where train/, valid/, test/ are at top level."""
    zip_path = tmp_path / "dataset_flat.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for split in ["train", "valid", "test"]:
            zf.writestr(f"{split}/images/img1.jpg", b"jpeg_bytes")
            zf.writestr(f"{split}/labels/img1.txt", "0 0.5 0.5 0.2 0.2\n")
        zf.writestr("data.yaml", "names: ['calculus', 'caries', 'gingivitis', 'tooth discoloration', 'ulcer']\n")

    extract_dir = tmp_path / "extract_flat"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    resolved_root = find_dataset_root(extract_dir)
    assert resolved_root == extract_dir
    assert (resolved_root / "train" / "images").is_dir()
    assert (resolved_root / "valid" / "images").is_dir()
    assert (resolved_root / "test" / "images").is_dir()

    counts = verify_dataset_counts(resolved_root)
    assert counts["train"]["images"] == 1
    assert counts["train"]["labels"] == 1
    assert counts["valid"]["images"] == 1
    assert counts["valid"]["labels"] == 1
    assert counts["test"]["images"] == 1
    assert counts["test"]["labels"] == 1


def test_find_dataset_root_case_b_nested(tmp_path: Path):
    """CASE B: Nested ZIP layout where train/, valid/, test/ are under a folder like oral-disease-v2.yolov11/."""
    zip_path = tmp_path / "dataset_nested.zip"
    nested_folder = "oral-disease-v2.yolov11"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for split in ["train", "valid", "test"]:
            zf.writestr(f"{nested_folder}/{split}/images/img1.jpg", b"jpeg_bytes")
            zf.writestr(f"{nested_folder}/{split}/labels/img1.txt", "0 0.5 0.5 0.2 0.2\n")
        zf.writestr(f"{nested_folder}/data.yaml", "names: ['calculus', 'caries', 'gingivitis', 'tooth discoloration', 'ulcer']\n")

    extract_dir = tmp_path / "extract_nested"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    resolved_root = find_dataset_root(extract_dir)
    assert resolved_root == extract_dir / nested_folder
    assert (resolved_root / "train" / "images").is_dir()
    assert (resolved_root / "valid" / "images").is_dir()
    assert (resolved_root / "test" / "images").is_dir()

    counts = verify_dataset_counts(resolved_root)
    assert counts["train"]["images"] == 1
    assert counts["train"]["labels"] == 1
    assert counts["valid"]["images"] == 1
    assert counts["valid"]["labels"] == 1
    assert counts["test"]["images"] == 1
    assert counts["test"]["labels"] == 1


def test_find_dataset_root_missing_valid_images_fails(tmp_path: Path):
    """Failure test: when valid/images is absent, find_dataset_root raises RuntimeError."""
    extract_dir = tmp_path / "extract_broken"
    extract_dir.mkdir(parents=True, exist_ok=True)

    # Only train and test, missing valid
    _create_dummy_split_files(extract_dir, "train")
    _create_dummy_split_files(extract_dir, "test")

    with pytest.raises(RuntimeError, match="Could not locate dataset root"):
        find_dataset_root(extract_dir)


def test_verify_dataset_counts_zero_images_fails(tmp_path: Path):
    """Failure test: when a split has 0 images, verify_dataset_counts raises RuntimeError."""
    ds_root = tmp_path / "empty_split_dataset"
    for split in ["train", "valid", "test"]:
        _create_dummy_split_files(ds_root, split)

    # Empty out valid images
    for img in (ds_root / "valid" / "images").glob("*"):
        img.unlink()

    with pytest.raises(RuntimeError, match="Split 'valid' has invalid counts"):
        verify_dataset_counts(ds_root)


def test_generate_v2_data_yaml_structure(tmp_path: Path):
    """Verifies generated data.yaml has absolute path, relative split subdirs, and correct class dict."""
    ds_root = tmp_path / "dummy_root"
    yaml_out = tmp_path / "out" / "daantshaant-v2-data.yaml"

    result_path = generate_v2_data_yaml(ds_root, output_yaml_path=yaml_out)
    assert result_path.exists()

    with open(result_path, "r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)

    assert loaded["path"] == str(ds_root.resolve())
    assert loaded["train"] == "train/images"
    assert loaded["val"] == "valid/images"
    assert loaded["test"] == "test/images"
    assert loaded["nc"] == 5
    assert loaded["names"] == CLASS_NAMES
    assert ".." not in loaded["train"]
    assert ".." not in loaded["val"]
    assert ".." not in loaded["test"]
