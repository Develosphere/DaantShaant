"""Test suite for Phase 11B-3: Mine Healthy Hard Negatives & Controls from External YOLO Dataset.

Tests all 14 requirements specified in Phase 11B-3 Section 16:
1. class names parsed correctly
2. healthy class detected from data.yaml
3. healthy-only images identified correctly
4. mixed-class images excluded
5. disease-only images excluded
6. zero-detection controls sampled deterministically
7. false-positive candidates ranked correctly
8. CSV generated
9. contact sheets generated
10. accepted negative produces empty label
11. multiple review CSV merge works
12. original oral-disease dataset untouched
13. original valid/test remain untouched
14. hash overlap protection works
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
from unittest.mock import MagicMock

import numpy as np
from PIL import Image
import pytest
import yaml

from scripts.mine_healthy_negatives import (
    calculate_priority_score,
    classify_dataset_images,
    create_contact_sheets,
    mine_healthy_candidates,
    parse_data_yaml,
)
from scripts.prepare_yolo_v2_dataset import (
    compute_file_hash,
    load_approved_negatives_from_review_csv,
    prepare_v2_dataset,
)


@pytest.fixture
def mock_healthy_dataset(tmp_path: Path) -> Path:
    """Creates a mock external dataset mimicking Dental Data Set.yolov11."""
    ds_root = tmp_path / "Dental Data Set"
    (ds_root / "train" / "images").mkdir(parents=True)
    (ds_root / "train" / "labels").mkdir(parents=True)

    # data.yaml
    data_yaml = {
        "nc": 7,
        "names": ['8', 'Calculus', 'CalculusCavities', 'CalculusHealthy Teeth', 'Cavities', 'Gingivitis', 'Healthy Teeth'],
        "roboflow": {
            "workspace": "test-ws",
            "project": "test-proj",
            "version": "dataset",
            "license": "CC BY 4.0",
        },
    }
    with open(ds_root / "data.yaml", "w", encoding="utf-8") as f:
        yaml.dump(data_yaml, f)

    # Image 1: Healthy-only (Class 6 only)
    (ds_root / "train" / "images" / "healthy_1.jpg").write_bytes(b"healthy_1_bytes")
    (ds_root / "train" / "labels" / "healthy_1.txt").write_text("6 0.5 0.5 0.1 0.1\n6 0.6 0.6 0.1 0.1\n", encoding="utf-8")

    # Image 2: Healthy-only (Class 6 only)
    (ds_root / "train" / "images" / "healthy_2.jpg").write_bytes(b"healthy_2_bytes")
    (ds_root / "train" / "labels" / "healthy_2.txt").write_text("6 0.4 0.4 0.1 0.1\n", encoding="utf-8")

    # Image 3: Mixed (Class 6 + Class 1 Calculus)
    (ds_root / "train" / "images" / "mixed_1.jpg").write_bytes(b"mixed_1_bytes")
    (ds_root / "train" / "labels" / "mixed_1.txt").write_text("1 0.3 0.3 0.1 0.1\n6 0.5 0.5 0.1 0.1\n", encoding="utf-8")

    # Image 4: Disease-only (Class 4 Cavities)
    (ds_root / "train" / "images" / "disease_1.jpg").write_bytes(b"disease_1_bytes")
    (ds_root / "train" / "labels" / "disease_1.txt").write_text("4 0.2 0.2 0.1 0.1\n", encoding="utf-8")

    # Image 5: Empty label
    (ds_root / "train" / "images" / "empty_1.jpg").write_bytes(b"empty_1_bytes")
    (ds_root / "train" / "labels" / "empty_1.txt").write_text("", encoding="utf-8")

    return ds_root


@pytest.fixture
def mock_benchmark_dataset(tmp_path: Path) -> Path:
    """Creates a mock original oral-disease benchmark dataset."""
    ds_root = tmp_path / "oral-disease.yolov11"
    for s in ["train", "valid", "test"]:
        (ds_root / s / "images").mkdir(parents=True)
        (ds_root / s / "labels").mkdir(parents=True)

    # Train
    (ds_root / "train" / "images" / "orig_train_1.jpg").write_bytes(b"orig_train_1_bytes")
    (ds_root / "train" / "labels" / "orig_train_1.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    # Valid
    (ds_root / "valid" / "images" / "orig_val_1.jpg").write_bytes(b"orig_val_1_bytes")
    (ds_root / "valid" / "labels" / "orig_val_1.txt").write_text("1 0.4 0.4 0.1 0.1\n", encoding="utf-8")

    # Test
    (ds_root / "test" / "images" / "orig_test_1.jpg").write_bytes(b"orig_test_1_bytes")
    (ds_root / "test" / "labels" / "orig_test_1.txt").write_text("2 0.3 0.3 0.2 0.2\n", encoding="utf-8")

    return ds_root


# 1. class names parsed correctly
def test_1_class_names_parsed_correctly(mock_healthy_dataset: Path):
    yaml_info = parse_data_yaml(mock_healthy_dataset / "data.yaml")
    assert yaml_info["names"] == ['8', 'Calculus', 'CalculusCavities', 'CalculusHealthy Teeth', 'Cavities', 'Gingivitis', 'Healthy Teeth']


# 2. healthy class detected from data.yaml
def test_2_healthy_class_detected_from_data_yaml(mock_healthy_dataset: Path):
    yaml_info = parse_data_yaml(mock_healthy_dataset / "data.yaml")
    assert yaml_info["healthy_class_id"] == 6
    assert yaml_info["healthy_class_name"] == "Healthy Teeth"


# 3. healthy-only images identified correctly
def test_3_healthy_only_images_identified_correctly(mock_healthy_dataset: Path):
    classification = classify_dataset_images(mock_healthy_dataset, split="train", healthy_class_id=6)
    healthy_stems = {p.stem for p in classification["healthy_only"]}
    assert "healthy_1" in healthy_stems
    assert "healthy_2" in healthy_stems
    assert len(classification["healthy_only"]) == 2


# 4. mixed-class images excluded
def test_4_mixed_class_images_excluded(mock_healthy_dataset: Path):
    classification = classify_dataset_images(mock_healthy_dataset, split="train", healthy_class_id=6)
    healthy_stems = {p.stem for p in classification["healthy_only"]}
    mixed_stems = {p.stem for p in classification["mixed"]}
    assert "mixed_1" not in healthy_stems
    assert "mixed_1" in mixed_stems


# 5. disease-only images excluded
def test_5_disease_only_images_excluded(mock_healthy_dataset: Path):
    classification = classify_dataset_images(mock_healthy_dataset, split="train", healthy_class_id=6)
    healthy_stems = {p.stem for p in classification["healthy_only"]}
    disease_stems = {p.stem for p in classification["disease_only"]}
    assert "disease_1" not in healthy_stems
    assert "disease_1" in disease_stems


# 6. zero-detection controls sampled deterministically
def test_6_zero_detection_controls_sampled_deterministically(mock_healthy_dataset: Path, tmp_path: Path):
    fake_model = MagicMock()
    # Return 0 detections for all images
    fake_res = MagicMock()
    fake_res.boxes = None
    fake_model.predict.return_value = [fake_res]

    res1 = mine_healthy_candidates(
        dataset_dir=mock_healthy_dataset,
        model_path=Path("fake.pt"),
        split="train",
        output_dir=tmp_path / "out1",
        original_dataset_dir=None,
        seed=42,
        model=fake_model,
    )
    res2 = mine_healthy_candidates(
        dataset_dir=mock_healthy_dataset,
        model_path=Path("fake.pt"),
        split="train",
        output_dir=tmp_path / "out2",
        original_dataset_dir=None,
        seed=42,
        model=fake_model,
    )

    controls1 = [c["filename"] for c in res1["clean_controls"]]
    controls2 = [c["filename"] for c in res2["clean_controls"]]
    assert len(controls1) == 2
    assert controls1 == controls2
    assert all(c["candidate_type"] == "CLEAN_CONTROL" for c in res1["clean_controls"])


# 7. false-positive candidates ranked correctly
def test_7_false_positive_candidates_ranked_correctly():
    det_high = [{"raw_class": "tooth discoloration", "confidence": 0.74, "normalized_finding": "discoloration"}]
    det_low = [{"raw_class": "tooth discoloration", "confidence": 0.40, "normalized_finding": "discoloration"}]

    score_high = calculate_priority_score(det_high)
    score_low = calculate_priority_score(det_low)
    assert score_high > score_low

    # Class weighting: tooth discoloration > gingivitis at equal confidence
    det_disc = [{"raw_class": "tooth discoloration", "confidence": 0.50}]
    det_ging = [{"raw_class": "gingivitis", "confidence": 0.50}]
    assert calculate_priority_score(det_disc) > calculate_priority_score(det_ging)


# 8. CSV generated with expected headers and status
def test_8_csv_generated(mock_healthy_dataset: Path, tmp_path: Path):
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

    out_dir = tmp_path / "csv_out"
    res = mine_healthy_candidates(
        dataset_dir=mock_healthy_dataset,
        model_path=Path("fake.pt"),
        split="train",
        output_dir=out_dir,
        original_dataset_dir=None,
        model=fake_model,
    )

    csv_path = res["csv_path"]
    assert csv_path.exists()
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 2
        assert reader[0]["candidate_type"] == "MODEL_FALSE_POSITIVE"
        assert reader[0]["review_status"] == "UNREVIEWED"
        assert reader[0]["top_predicted_class"] == "tooth discoloration"
        assert float(reader[0]["top_confidence"]) == 0.72


# 9. contact sheets generated
def test_9_contact_sheets_generated(tmp_path: Path):
    # Create mock candidate with an actual PIL image
    img_path = tmp_path / "test_img.jpg"
    test_img = Image.new("RGB", (200, 200), color=(100, 150, 200))
    test_img.save(img_path)

    candidates = [{
        "filename": "test_img.jpg",
        "absolute_path": str(img_path),
        "candidate_type": "MODEL_FALSE_POSITIVE",
        "top_predicted_class": "tooth discoloration",
        "top_confidence": 0.72,
        "tile_number": 1,
        "detections": [{
            "raw_class": "tooth discoloration",
            "confidence": 0.72,
            "box_xyxy": [20.0, 20.0, 80.0, 80.0],
        }],
    }]

    sheet_paths = create_contact_sheets(
        candidates=candidates,
        output_dir=tmp_path,
        cols=2,
        rows=2,
        tile_size=(200, 200),
    )
    assert len(sheet_paths) == 1
    assert sheet_paths[0].exists()
    with Image.open(sheet_paths[0]) as sheet:
        assert sheet.size == (400, 400)


# 10. accepted negative produces empty label in v2
def test_10_accepted_negative_produces_empty_label(mock_benchmark_dataset: Path, tmp_path: Path):
    neg_img = tmp_path / "clean_negative.jpg"
    neg_img.write_bytes(b"clean_neg_data")

    review_csv = tmp_path / "review.csv"
    with open(review_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["tile_number", "filename", "source_path", "review_status"])
        writer.writerow([1, "clean_negative.jpg", str(neg_img), "ACCEPT_NEGATIVE"])

    v2_dir = tmp_path / "v2_out"
    prepare_v2_dataset(
        original_dataset=mock_benchmark_dataset,
        v2_output_dir=v2_dir,
        review_csv=review_csv,
        negative_repeat=1,
    )

    label_file = v2_dir / "train" / "labels" / "neg_clean_negative.txt"
    assert label_file.exists()
    assert label_file.stat().st_size == 0


# 11. multiple review CSV merge works
def test_11_multiple_review_csv_merge_works(mock_benchmark_dataset: Path, tmp_path: Path):
    neg_img1 = tmp_path / "neg_from_review1.jpg"
    neg_img1.write_bytes(b"neg1_data")
    neg_img2 = tmp_path / "neg_from_review2.jpg"
    neg_img2.write_bytes(b"neg2_data")

    csv1 = tmp_path / "review1.csv"
    with open(csv1, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        writer.writerow(["neg_from_review1.jpg", str(neg_img1), "ACCEPT_NEGATIVE"])

    csv2 = tmp_path / "review2.csv"
    with open(csv2, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        writer.writerow(["neg_from_review2.jpg", str(neg_img2), "ACCEPT_NEGATIVE"])

    v2_dir = tmp_path / "v2_multi"
    summary = prepare_v2_dataset(
        original_dataset=mock_benchmark_dataset,
        v2_output_dir=v2_dir,
        review_csv=[csv1, csv2],
        negative_repeat=1,
    )

    assert summary["approved_negatives_unique"] == 2
    assert (v2_dir / "train" / "images" / "neg_neg_from_review1.jpg").exists()
    assert (v2_dir / "train" / "images" / "neg_neg_from_review2.jpg").exists()


# 12. original oral-disease dataset untouched
def test_12_original_oral_disease_dataset_untouched(mock_benchmark_dataset: Path, tmp_path: Path):
    neg_img = tmp_path / "neg_sample.jpg"
    neg_img.write_bytes(b"neg_sample_data")

    csv_p = tmp_path / "rev.csv"
    with open(csv_p, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        writer.writerow(["neg_sample.jpg", str(neg_img), "ACCEPT_NEGATIVE"])

    orig_train_count = len(list((mock_benchmark_dataset / "train" / "images").iterdir()))
    v2_dir = tmp_path / "v2_test12"
    prepare_v2_dataset(mock_benchmark_dataset, v2_dir, review_csv=csv_p)

    after_train_count = len(list((mock_benchmark_dataset / "train" / "images").iterdir()))
    assert orig_train_count == after_train_count


# 13. original valid/test remain untouched
def test_13_original_valid_test_remain_untouched(mock_benchmark_dataset: Path, tmp_path: Path):
    neg_img = tmp_path / "neg_sample.jpg"
    neg_img.write_bytes(b"neg_sample_data")

    csv_p = tmp_path / "rev.csv"
    with open(csv_p, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        writer.writerow(["neg_sample.jpg", str(neg_img), "ACCEPT_NEGATIVE"])

    v2_dir = tmp_path / "v2_test13"
    prepare_v2_dataset(mock_benchmark_dataset, v2_dir, review_csv=csv_p)

    # Valid images match exactly
    orig_val = [p.name for p in (mock_benchmark_dataset / "valid" / "images").iterdir()]
    v2_val = [p.name for p in (v2_dir / "valid" / "images").iterdir()]
    assert orig_val == v2_val

    # Test images match exactly
    orig_test = [p.name for p in (mock_benchmark_dataset / "test" / "images").iterdir()]
    v2_test = [p.name for p in (v2_dir / "test" / "images").iterdir()]
    assert orig_test == v2_test


# 14. hash overlap protection works
def test_14_hash_overlap_protection_works(mock_benchmark_dataset: Path, tmp_path: Path):
    # Create candidate with identical content as orig_val_1.jpg
    leak_img = tmp_path / "leak.jpg"
    leak_img.write_bytes(b"orig_val_1_bytes")

    csv_p = tmp_path / "leak.csv"
    with open(csv_p, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        writer.writerow(["leak.jpg", str(leak_img), "ACCEPT_NEGATIVE"])

    v2_dir = tmp_path / "v2_leak"
    with pytest.raises(RuntimeError, match="DATA LEAKAGE ERROR"):
        prepare_v2_dataset(mock_benchmark_dataset, v2_dir, review_csv=csv_p)
