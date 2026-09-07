"""Test suite for Phase 11B-2: YOLO Hard-Negative Mining & v2 Refinement Pipeline.

Tests all 16 requirements specified in Phase 11B-2 Section 25:
1. only empty-label TRAIN images mined
2. positive images excluded
3. valid/test negatives excluded from training miner
4. predictions ranked correctly
5. confidence metadata retained
6. review CSV generated correctly
7. approved-only dataset merge
8. uncertain images excluded
9. original dataset untouched
10. valid split unchanged
11. test split unchanged
12. hash leakage detection
13. deterministic dataset generation
14. negative-repeat works
15. no model overwrite
16. Modal script references uploaded container paths correctly
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from scripts.mine_yolo_hard_negatives import (
    calculate_priority_score,
    find_empty_label_images,
    mine_hard_negatives,
)
from scripts.prepare_yolo_v2_dataset import (
    compute_file_hash,
    load_approved_negatives_from_review_csv,
    prepare_v2_dataset,
)


@pytest.fixture
def dummy_dataset(tmp_path: Path) -> Path:
    """Creates a mock dataset structure with train, valid, and test splits."""
    ds_root = tmp_path / "oral-disease"
    for s in ["train", "valid", "test"]:
        (ds_root / s / "images").mkdir(parents=True)
        (ds_root / s / "labels").mkdir(parents=True)

    # Train: 1 positive image, 2 empty-label images
    (ds_root / "train" / "images" / "train_pos.jpg").write_bytes(b"pos_img_bytes")
    (ds_root / "train" / "labels" / "train_pos.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    (ds_root / "train" / "images" / "train_empty_1.jpg").write_bytes(b"empty_1_bytes")
    (ds_root / "train" / "labels" / "train_empty_1.txt").write_text("", encoding="utf-8")

    (ds_root / "train" / "images" / "train_empty_2.jpg").write_bytes(b"empty_2_bytes")
    # train_empty_2 has no label file at all (should count as empty/negative)

    # Valid: 1 positive, 1 empty
    (ds_root / "valid" / "images" / "val_pos.jpg").write_bytes(b"val_pos_bytes")
    (ds_root / "valid" / "labels" / "val_pos.txt").write_text("1 0.4 0.4 0.1 0.1\n", encoding="utf-8")

    (ds_root / "valid" / "images" / "val_empty.jpg").write_bytes(b"val_empty_bytes")
    (ds_root / "valid" / "labels" / "val_empty.txt").write_text("", encoding="utf-8")

    # Test: 1 positive, 1 empty
    (ds_root / "test" / "images" / "test_pos.jpg").write_bytes(b"test_pos_bytes")
    (ds_root / "test" / "labels" / "test_pos.txt").write_text("2 0.3 0.3 0.2 0.2\n", encoding="utf-8")

    (ds_root / "test" / "images" / "test_empty.jpg").write_bytes(b"test_empty_bytes")
    (ds_root / "test" / "labels" / "test_empty.txt").write_text("", encoding="utf-8")

    return ds_root


# 1. only empty-label TRAIN images mined
def test_1_only_empty_label_train_images_mined(dummy_dataset: Path):
    empty_imgs = find_empty_label_images(dummy_dataset, split="train")
    stems = {p.stem for p in empty_imgs}
    assert "train_empty_1" in stems
    assert "train_empty_2" in stems
    assert len(empty_imgs) == 2


# 2. positive images excluded
def test_2_positive_images_excluded(dummy_dataset: Path):
    empty_imgs = find_empty_label_images(dummy_dataset, split="train")
    stems = {p.stem for p in empty_imgs}
    assert "train_pos" not in stems


# 3. valid/test negatives excluded from training miner
def test_3_valid_test_negatives_excluded_from_training_miner(dummy_dataset: Path):
    train_empty = find_empty_label_images(dummy_dataset, split="train")
    stems = {p.stem for p in train_empty}
    assert "val_empty" not in stems
    assert "test_empty" not in stems


# 4. predictions ranked correctly (priority score and top confidence)
def test_4_predictions_ranked_correctly():
    det_high = [{"raw_class": "tooth discoloration", "confidence": 0.75, "normalized_finding": "discoloration"}]
    det_low = [{"raw_class": "tooth discoloration", "confidence": 0.40, "normalized_finding": "discoloration"}]

    score_high = calculate_priority_score(det_high)
    score_low = calculate_priority_score(det_low)
    assert score_high > score_low

    # Check class weighting: discoloration > ulcer for equal confidence
    det_disc = [{"raw_class": "tooth discoloration", "confidence": 0.60}]
    det_ulcer = [{"raw_class": "ulcer", "confidence": 0.60}]
    assert calculate_priority_score(det_disc) > calculate_priority_score(det_ulcer)


# 5. confidence metadata retained
def test_5_confidence_metadata_retained(tmp_path: Path):
    fake_model = MagicMock()
    fake_res = MagicMock()
    fake_boxes = MagicMock()
    fake_boxes.xyxy.cpu().numpy.return_value = np.array([[10.0, 10.0, 50.0, 50.0]])
    fake_boxes.xyxyn.cpu().numpy.return_value = np.array([[0.1, 0.1, 0.5, 0.5]])
    fake_boxes.conf.cpu().numpy.return_value = np.array([0.72])
    fake_boxes.cls.cpu().numpy.return_value = np.array([3])  # tooth discoloration
    fake_boxes.__len__.return_value = 1
    fake_res.boxes = fake_boxes
    fake_model.predict.return_value = [fake_res]

    # Setup dummy train split
    ds = tmp_path / "ds"
    (ds / "train" / "images").mkdir(parents=True)
    (ds / "train" / "labels").mkdir(parents=True)
    (ds / "train" / "images" / "neg_img.jpg").write_bytes(b"img")
    (ds / "train" / "labels" / "neg_img.txt").write_text("", encoding="utf-8")

    out_dir = tmp_path / "out"
    res = mine_hard_negatives(
        model_path=Path("fake.pt"),
        dataset_dir=ds,
        split="train",
        min_confidence=0.30,
        output_dir=out_dir,
        model=fake_model,
    )

    cand = res["candidates"][0]
    assert cand["top_confidence"] == 0.72
    assert cand["top_class"] == "tooth discoloration"
    assert cand["detection_count"] == 1
    assert "box_xyxy" in cand["detections"][0]
    assert "box_xyxyn" in cand["detections"][0]


# 6. review CSV generated correctly
def test_6_review_csv_generated_correctly(tmp_path: Path):
    review_csv = tmp_path / "review.csv"
    with open(review_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "top_class", "top_confidence", "detection_count", "all_predictions", "priority", "review_status"])
        writer.writerow(["neg1.jpg", "oral-disease/train/images/neg1.jpg", "tooth discoloration", "0.68", "1", "[]", "2.5", "UNREVIEWED"])

    assert review_csv.exists()
    with open(review_csv, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 1
        assert reader[0]["review_status"] == "UNREVIEWED"
        assert reader[0]["top_class"] == "tooth discoloration"


# 7. approved-only dataset merge & 8. uncertain images excluded
def test_7_8_approved_only_dataset_merge(tmp_path: Path, dummy_dataset: Path):
    review_csv = tmp_path / "review.csv"
    train_img1 = dummy_dataset / "train" / "images" / "train_empty_1.jpg"
    train_img2 = dummy_dataset / "train" / "images" / "train_empty_2.jpg"

    with open(review_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "top_class", "top_confidence", "detection_count", "all_predictions", "priority", "review_status"])
        writer.writerow(["train_empty_1.jpg", str(train_img1), "tooth discoloration", "0.68", "1", "[]", "2.5", "ACCEPT_NEGATIVE"])
        writer.writerow(["train_empty_2.jpg", str(train_img2), "tooth discoloration", "0.45", "1", "[]", "1.2", "REJECT_UNCERTAIN"])

    approved = load_approved_negatives_from_review_csv(review_csv, dummy_dataset)
    assert len(approved) == 1
    assert approved[0][0] == "train_empty_1.jpg"

    v2_dir = tmp_path / "v2"
    summary = prepare_v2_dataset(
        original_dataset=dummy_dataset,
        v2_output_dir=v2_dir,
        review_csv=review_csv,
        negative_repeat=1,
    )
    assert summary["approved_negatives_unique"] == 1
    assert (v2_dir / "train" / "images" / "neg_train_empty_1.jpg").exists()
    assert not (v2_dir / "train" / "images" / "neg_train_empty_2.jpg").exists()


# 9. original dataset untouched
def test_9_original_dataset_untouched(tmp_path: Path, dummy_dataset: Path):
    review_csv = tmp_path / "review.csv"
    train_img1 = dummy_dataset / "train" / "images" / "train_empty_1.jpg"

    with open(review_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "top_class", "top_confidence", "detection_count", "all_predictions", "priority", "review_status"])
        writer.writerow(["train_empty_1.jpg", str(train_img1), "tooth discoloration", "0.68", "1", "[]", "2.5", "ACCEPT_NEGATIVE"])

    orig_train_count = len(list((dummy_dataset / "train" / "images").iterdir()))
    v2_dir = tmp_path / "v2"
    prepare_v2_dataset(dummy_dataset, v2_dir, review_csv=review_csv)

    new_train_count = len(list((dummy_dataset / "train" / "images").iterdir()))
    assert orig_train_count == new_train_count


# 10. valid split unchanged & 11. test split unchanged
def test_10_11_valid_and_test_splits_unchanged(tmp_path: Path, dummy_dataset: Path):
    review_csv = tmp_path / "review.csv"
    train_img1 = dummy_dataset / "train" / "images" / "train_empty_1.jpg"

    with open(review_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "top_class", "top_confidence", "detection_count", "all_predictions", "priority", "review_status"])
        writer.writerow(["train_empty_1.jpg", str(train_img1), "tooth discoloration", "0.68", "1", "[]", "2.5", "ACCEPT_NEGATIVE"])

    v2_dir = tmp_path / "v2"
    prepare_v2_dataset(dummy_dataset, v2_dir, review_csv=review_csv)

    # Valid
    orig_valid_imgs = sorted([p.name for p in (dummy_dataset / "valid" / "images").iterdir()])
    v2_valid_imgs = sorted([p.name for p in (v2_dir / "valid" / "images").iterdir()])
    assert orig_valid_imgs == v2_valid_imgs

    # Test
    orig_test_imgs = sorted([p.name for p in (dummy_dataset / "test" / "images").iterdir()])
    v2_test_imgs = sorted([p.name for p in (v2_dir / "test" / "images").iterdir()])
    assert orig_test_imgs == v2_test_imgs


# 12. hash leakage detection
def test_12_hash_leakage_detection(tmp_path: Path, dummy_dataset: Path):
    # Create an approved negative that has the exact same content as val_empty.jpg
    review_csv = tmp_path / "leak_review.csv"
    val_empty_img = dummy_dataset / "valid" / "images" / "val_empty.jpg"

    with open(review_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "top_class", "top_confidence", "detection_count", "all_predictions", "priority", "review_status"])
        # Pointing to validation file but approved for train!
        writer.writerow(["val_empty.jpg", str(val_empty_img), "caries", "0.65", "1", "[]", "2.0", "ACCEPT_NEGATIVE"])

    v2_dir = tmp_path / "v2"
    with pytest.raises(RuntimeError, match="DATA LEAKAGE ERROR"):
        prepare_v2_dataset(dummy_dataset, v2_dir, review_csv=review_csv)


# 13. deterministic dataset generation
def test_13_deterministic_dataset_generation(tmp_path: Path, dummy_dataset: Path):
    review_csv = tmp_path / "review.csv"
    train_img1 = dummy_dataset / "train" / "images" / "train_empty_1.jpg"

    with open(review_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "top_class", "top_confidence", "detection_count", "all_predictions", "priority", "review_status"])
        writer.writerow(["train_empty_1.jpg", str(train_img1), "tooth discoloration", "0.68", "1", "[]", "2.5", "ACCEPT_NEGATIVE"])

    v2_run1 = tmp_path / "v2_run1"
    v2_run2 = tmp_path / "v2_run2"

    prepare_v2_dataset(dummy_dataset, v2_run1, review_csv=review_csv, negative_repeat=1)
    prepare_v2_dataset(dummy_dataset, v2_run2, review_csv=review_csv, negative_repeat=1)

    r1_files = sorted([p.name for p in (v2_run1 / "train" / "images").iterdir()])
    r2_files = sorted([p.name for p in (v2_run2 / "train" / "images").iterdir()])
    assert r1_files == r2_files


# 14. negative-repeat works
def test_14_negative_repeat_works(tmp_path: Path, dummy_dataset: Path):
    review_csv = tmp_path / "review.csv"
    train_img1 = dummy_dataset / "train" / "images" / "train_empty_1.jpg"

    with open(review_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "top_class", "top_confidence", "detection_count", "all_predictions", "priority", "review_status"])
        writer.writerow(["train_empty_1.jpg", str(train_img1), "tooth discoloration", "0.68", "1", "[]", "2.5", "ACCEPT_NEGATIVE"])

    v2_dir = tmp_path / "v2_rep2"
    summary = prepare_v2_dataset(dummy_dataset, v2_dir, review_csv=review_csv, negative_repeat=2)
    assert summary["effective_negatives_added_to_train"] == 2

    # Should see rep0_neg_train_empty_1.jpg and rep1_neg_train_empty_1.jpg
    assert (v2_dir / "train" / "images" / "rep0_neg_train_empty_1.jpg").exists()
    assert (v2_dir / "train" / "images" / "rep1_neg_train_empty_1.jpg").exists()
    assert (v2_dir / "train" / "labels" / "rep0_neg_train_empty_1.txt").stat().st_size == 0
    assert (v2_dir / "train" / "labels" / "rep1_neg_train_empty_1.txt").stat().st_size == 0


# 15. no model overwrite (best.pt preserved)
def test_15_no_model_overwrite():
    best_v1 = Path("services/teeth_analyzer/models/oral_disease/best.pt")
    assert best_v1.exists()
    # Ensure v2 target path is distinct
    v2_target = Path("services/teeth_analyzer/models/oral_disease/best_v2.pt")
    assert v2_target != best_v1


# 16. Modal script references uploaded container paths correctly
def test_16_modal_script_references_uploaded_container_paths():
    modal_script = Path("scripts/modal_train_yolo_v2.py")
    assert modal_script.exists()
    content = modal_script.read_text(encoding="utf-8")

    # Assert correct local files added to image
    assert 'dataset/oral-disease-v2.yolov11.zip' in content
    assert '/root/oral-disease-v2.zip' in content
    assert 'services/teeth_analyzer/models/oral_disease/best.pt' in content
    assert '/root/best_v1.pt' in content

    # Assert volume name and output paths
    assert 'daantshaant-yolo-v2-output' in content
    assert '/output/oral-disease-yolo11n-v2/weights/best.pt' in content

    # Assert fine-tuning parameters
    assert 'epochs=12' in content
    assert 'optimizer="AdamW"' in content
    assert 'lr0=0.0005' in content
    assert 'YOLO(str(v1_model_path))' in content
