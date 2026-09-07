"""Test suite for Phase 11B-4: Large Healthy-Negative Mining + V2 Dataset Preparation.

Validates all 19 requirements specified in Phase 11B-4 Section 26:
1. local class discovery
2. healthy-only extraction
3. mixed exclusion
4. all healthy candidates processed
5. FP/control classification
6. quality exclusion
7. SHA duplicate detection
8. deterministic control sample
9. FP ranking
10. control status AUTO_ELIGIBLE_CONTROL
11. explicit audited-control opt-in
12. accepted-only merge
13. cross-source dedup
14. benchmark leakage abort
15. benchmark valid unchanged
16. benchmark test unchanged
17. repeat=1 recommendation for large pool
18. negative percentage calculation
19. Modal script still valid
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

from scripts.mine_large_healthy_pool import (
    calculate_fp_priority,
    compute_dhash,
    compute_file_sha256,
    evaluate_image_quality,
    find_healthy_only_images,
    hamming_distance,
    parse_source_data_yaml,
    perform_deduplication,
    run_mining_pipeline,
)
from scripts.prepare_yolo_v2_dataset import (
    compute_file_hash,
    load_approved_negatives_from_review_csv,
    prepare_v2_dataset,
)


@pytest.fixture
def mock_penyakit_dataset(tmp_path: Path) -> Path:
    """Creates a mock dataset matching Penyakit Gigi Skripsi structure."""
    ds_root = tmp_path / "Penyakit Gigi Skripsi.yolov11"
    for s in ["train", "valid", "test"]:
        (ds_root / s / "images").mkdir(parents=True)
        (ds_root / s / "labels").mkdir(parents=True)

    # data.yaml
    data_yaml = {
        "train": "../train/images",
        "val": "../valid/images",
        "test": "../test/images",
        "nc": 3,
        "names": ["calculus", "caries", "healthy"],
        "roboflow": {
            "workspace": "nathan-asif-blm21",
            "project": "penyakit-gigi-skripsi-i77mi",
            "version": "dataset",
            "license": "CC BY 4.0",
            "url": "https://universe.roboflow.com/nathan-asif-blm21/penyakit-gigi-skripsi-i77mi/dataset/dataset",
        },
    }
    with open(ds_root / "data.yaml", "w", encoding="utf-8") as f:
        yaml.dump(data_yaml, f)

    # Create dummy images with real PIL image bytes
    def make_img(path: Path, color=(120, 120, 120)):
        img = Image.new("RGB", (200, 200), color=color)
        img.save(path)

    # Train: 1 healthy-only, 1 mixed, 1 disease-only
    make_img(ds_root / "train" / "images" / "train_h1.jpg", (100, 100, 100))
    (ds_root / "train" / "labels" / "train_h1.txt").write_text("2 0.5 0.5 0.2 0.2\n2 0.6 0.6 0.2 0.2\n", encoding="utf-8")

    make_img(ds_root / "train" / "images" / "train_mixed.jpg", (110, 110, 110))
    (ds_root / "train" / "labels" / "train_mixed.txt").write_text("0 0.4 0.4 0.1 0.1\n2 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    make_img(ds_root / "train" / "images" / "train_dis.jpg", (120, 120, 120))
    (ds_root / "train" / "labels" / "train_dis.txt").write_text("1 0.3 0.3 0.1 0.1\n", encoding="utf-8")

    # Valid: 1 healthy-only
    make_img(ds_root / "valid" / "images" / "valid_h1.jpg", (130, 130, 130))
    (ds_root / "valid" / "labels" / "valid_h1.txt").write_text("2 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    # Test: 1 healthy-only, 1 empty
    make_img(ds_root / "test" / "images" / "test_h1.jpg", (140, 140, 140))
    (ds_root / "test" / "labels" / "test_h1.txt").write_text("2 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    make_img(ds_root / "test" / "images" / "test_empty.jpg", (150, 150, 150))
    (ds_root / "test" / "labels" / "test_empty.txt").write_text("", encoding="utf-8")

    return ds_root


@pytest.fixture
def mock_benchmark_dataset(tmp_path: Path) -> Path:
    """Creates a mock benchmark dataset."""
    ds_root = tmp_path / "benchmark_oral_disease"
    for s in ["train", "valid", "test"]:
        (ds_root / s / "images").mkdir(parents=True)
        (ds_root / s / "labels").mkdir(parents=True)

    (ds_root / "train" / "images" / "train_01.jpg").write_bytes(b"bench_train_01")
    (ds_root / "train" / "labels" / "train_01.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    (ds_root / "valid" / "images" / "valid_01.jpg").write_bytes(b"bench_valid_01")
    (ds_root / "valid" / "labels" / "valid_01.txt").write_text("1 0.4 0.4 0.1 0.1\n", encoding="utf-8")

    (ds_root / "test" / "images" / "test_01.jpg").write_bytes(b"bench_test_01")
    (ds_root / "test" / "labels" / "test_01.txt").write_text("2 0.3 0.3 0.2 0.2\n", encoding="utf-8")

    return ds_root


# 1. local class discovery
def test_1_local_class_discovery(mock_penyakit_dataset: Path):
    yaml_info = parse_source_data_yaml(mock_penyakit_dataset / "data.yaml")
    assert yaml_info["names"] == ["calculus", "caries", "healthy"]
    assert yaml_info["healthy_id"] == 2
    assert yaml_info["healthy_name"] == "healthy"
    assert yaml_info["calculus_id"] == 0
    assert yaml_info["caries_id"] == 1
    assert yaml_info["license"] == "CC BY 4.0"
    assert yaml_info["project"] == "penyakit-gigi-skripsi-i77mi"


# 2. healthy-only extraction
def test_2_healthy_only_extraction(mock_penyakit_dataset: Path):
    classif = find_healthy_only_images(mock_penyakit_dataset, healthy_id=2)
    assert classif["healthy_only_count"] == 3  # train_h1, valid_h1, test_h1
    stems = {item["filename"] for item in classif["healthy_only"]}
    assert "train_h1.jpg" in stems
    assert "valid_h1.jpg" in stems
    assert "test_h1.jpg" in stems


# 3. mixed exclusion
def test_3_mixed_exclusion(mock_penyakit_dataset: Path):
    classif = find_healthy_only_images(mock_penyakit_dataset, healthy_id=2)
    stems = {item["filename"] for item in classif["healthy_only"]}
    assert "train_mixed.jpg" not in stems
    assert "train_dis.jpg" not in stems
    assert "test_empty.jpg" not in stems
    assert classif["mixed_count"] == 1
    assert classif["disease_only_count"] == 1
    assert classif["empty_count"] == 1


# 4. all healthy candidates processed
def test_4_all_healthy_candidates_processed(mock_penyakit_dataset: Path, tmp_path: Path):
    fake_model = MagicMock()
    fake_res = MagicMock()
    fake_res.boxes = None
    fake_model.predict.return_value = [fake_res]

    res = run_mining_pipeline(
        dataset_dir=mock_penyakit_dataset,
        model_path=Path("fake.pt"),
        output_dir=tmp_path / "out_p4",
        original_benchmark_dir=None,
        model=fake_model,
    )
    # Exactly 3 healthy-only images evaluated
    assert len(res["control_candidates"]) + len(res["fp_candidates"]) == 3


# 5. FP/control classification
def test_5_fp_control_classification(mock_penyakit_dataset: Path, tmp_path: Path):
    fake_model = MagicMock()

    # Image 1 gets a false-positive detection; others get 0
    fp_boxes = MagicMock()
    fp_boxes.xyxy.cpu().numpy.return_value = np.array([[10.0, 10.0, 50.0, 50.0]])
    fp_boxes.xyxyn.cpu().numpy.return_value = np.array([[0.1, 0.1, 0.5, 0.5]])
    fp_boxes.conf.cpu().numpy.return_value = np.array([0.75])
    fp_boxes.cls.cpu().numpy.return_value = np.array([3])  # tooth discoloration
    fp_boxes.__len__.return_value = 1

    res_fp = MagicMock()
    res_fp.boxes = fp_boxes
    res_ctrl = MagicMock()
    res_ctrl.boxes = None

    fake_model.predict.side_effect = [[res_fp], [res_ctrl], [res_ctrl]]

    res = run_mining_pipeline(
        dataset_dir=mock_penyakit_dataset,
        model_path=Path("fake.pt"),
        output_dir=tmp_path / "out_p5",
        original_benchmark_dir=None,
        model=fake_model,
    )

    assert len(res["fp_candidates"]) == 1
    assert res["fp_candidates"][0]["candidate_type"] == "MODEL_FALSE_POSITIVE"
    assert res["fp_candidates"][0]["top_predicted_class"] == "tooth discoloration"
    assert len(res["control_candidates"]) == 2
    assert all(c["candidate_type"] == "CLEAN_CONTROL" for c in res["control_candidates"])


# 6. quality exclusion
def test_6_quality_exclusion(tmp_path: Path):
    # Test tiny image
    tiny_p = tmp_path / "tiny.jpg"
    Image.new("RGB", (64, 64), color=(100, 100, 100)).save(tiny_p)
    q_tiny = evaluate_image_quality(tiny_p)
    assert q_tiny["quality_status"] == "FAIL_TINY"

    # Test extreme overexposure (all white)
    white_p = tmp_path / "white.jpg"
    Image.new("RGB", (200, 200), color=(255, 255, 255)).save(white_p)
    q_white = evaluate_image_quality(white_p)
    assert q_white["quality_status"] == "FAIL_OVEREXPOSURE"

    # Test normal clean image
    clean_p = tmp_path / "clean.jpg"
    # Create noisy image with good contrast and edges
    arr = np.random.randint(50, 200, (200, 200, 3), dtype=np.uint8)
    Image.fromarray(arr).save(clean_p)
    q_clean = evaluate_image_quality(clean_p)
    assert q_clean["quality_status"] == "PASS"


# 7. SHA duplicate detection & perceptual dHash
def test_7_sha_and_dhash_duplicate_detection(tmp_path: Path):
    img1_p = tmp_path / "img1.png"
    arr1 = np.random.randint(50, 200, (200, 200, 3), dtype=np.uint8)
    Image.fromarray(arr1).save(img1_p)

    # img2: exact byte duplicate
    img2_p = tmp_path / "img2.png"
    img2_p.write_bytes(img1_p.read_bytes())

    # img3: slight perturbation (near duplicate: different bytes, identical dHash)
    img3_p = tmp_path / "img3.png"
    arr3 = arr1.copy()
    arr3[10:15, 10:15] = (arr3[10:15, 10:15] + 2) % 255
    Image.fromarray(arr3).save(img3_p)

    items = [
        {"absolute_path": str(img1_p)},
        {"absolute_path": str(img2_p)},
        {"absolute_path": str(img3_p)},
    ]

    exact_cnt, near_cnt = perform_deduplication(items, dhash_distance_threshold=5)
    assert exact_cnt == 1  # img2 is exact duplicate
    assert near_cnt == 1   # img3 is near duplicate
    assert items[0]["duplicate_status"] == "PRIMARY"
    assert items[1]["duplicate_status"] == "EXACT_DUPLICATE"
    assert items[2]["duplicate_status"] == "NEAR_DUPLICATE"


# 8. deterministic control sample
def test_8_deterministic_control_sample(mock_penyakit_dataset: Path, tmp_path: Path):
    fake_model = MagicMock()
    fake_res = MagicMock()
    fake_res.boxes = None
    fake_model.predict.return_value = [fake_res]

    res1 = run_mining_pipeline(
        dataset_dir=mock_penyakit_dataset,
        model_path=Path("fake.pt"),
        output_dir=tmp_path / "out_s1",
        original_benchmark_dir=None,
        seed=42,
        model=fake_model,
    )
    res2 = run_mining_pipeline(
        dataset_dir=mock_penyakit_dataset,
        model_path=Path("fake.pt"),
        output_dir=tmp_path / "out_s2",
        original_benchmark_dir=None,
        seed=42,
        model=fake_model,
    )

    sample1 = [c["filename"] for c in res1["control_audit_sample"]]
    sample2 = [c["filename"] for c in res2["control_audit_sample"]]
    assert sample1 == sample2


# 9. FP ranking
def test_9_fp_ranking():
    # Priority order: tooth discoloration > caries > calculus > gingivitis > ulcer
    det_disc = [{"raw_class": "tooth discoloration", "confidence": 0.50, "box_xyxyn": [0.1, 0.1, 0.3, 0.3]}]
    det_caries = [{"raw_class": "caries", "confidence": 0.50, "box_xyxyn": [0.1, 0.1, 0.3, 0.3]}]
    det_calc = [{"raw_class": "calculus", "confidence": 0.50, "box_xyxyn": [0.1, 0.1, 0.3, 0.3]}]
    det_ging = [{"raw_class": "gingivitis", "confidence": 0.50, "box_xyxyn": [0.1, 0.1, 0.3, 0.3]}]
    det_ulcer = [{"raw_class": "ulcer", "confidence": 0.50, "box_xyxyn": [0.1, 0.1, 0.3, 0.3]}]

    p_disc = calculate_fp_priority(det_disc)
    p_caries = calculate_fp_priority(det_caries)
    p_calc = calculate_fp_priority(det_calc)
    p_ging = calculate_fp_priority(det_ging)
    p_ulcer = calculate_fp_priority(det_ulcer)

    assert p_disc > p_caries > p_calc > p_ging > p_ulcer


# 10. control status AUTO_ELIGIBLE_CONTROL
def test_10_control_status_auto_eligible_control(mock_penyakit_dataset: Path, tmp_path: Path):
    fake_model = MagicMock()
    fake_res = MagicMock()
    fake_res.boxes = None
    fake_model.predict.return_value = [fake_res]

    res = run_mining_pipeline(
        dataset_dir=mock_penyakit_dataset,
        model_path=Path("fake.pt"),
        output_dir=tmp_path / "out_p10",
        original_benchmark_dir=None,
        model=fake_model,
    )

    for ctrl in res["eligible_controls"]:
        assert ctrl["candidate_type"] == "CLEAN_CONTROL"
        assert ctrl["review_status"] == "AUTO_ELIGIBLE_CONTROL"


# 11. explicit audited-control opt-in
def test_11_explicit_audited_control_opt_in(tmp_path: Path):
    dummy_img1 = tmp_path / "c1.jpg"
    dummy_img1.write_bytes(b"c1_bytes")
    dummy_img2 = tmp_path / "c2.jpg"
    dummy_img2.write_bytes(b"c2_bytes")

    csv_path = tmp_path / "test_rev.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        writer.writerow(["c1.jpg", str(dummy_img1), "ACCEPT_NEGATIVE"])
        writer.writerow(["c2.jpg", str(dummy_img2), "AUTO_ELIGIBLE_CONTROL"])

    # Default (opt-in False): only ACCEPT_NEGATIVE
    loaded_default = load_approved_negatives_from_review_csv(
        csv_path, original_dataset_dir=tmp_path, include_audited_controls=False
    )
    assert len(loaded_default) == 1
    assert loaded_default[0][0] == "c1.jpg"

    # Explicit opt-in: both ACCEPT_NEGATIVE and AUTO_ELIGIBLE_CONTROL
    loaded_optin = load_approved_negatives_from_review_csv(
        csv_path, original_dataset_dir=tmp_path, include_audited_controls=True
    )
    assert len(loaded_optin) == 2


# 12. accepted-only merge
def test_12_accepted_only_merge(tmp_path: Path):
    unrev_img = tmp_path / "unrev.jpg"
    unrev_img.write_bytes(b"unrev_bytes")
    rej_img = tmp_path / "rej.jpg"
    rej_img.write_bytes(b"rej_bytes")

    csv_path = tmp_path / "unreviewed.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        writer.writerow(["unrev.jpg", str(unrev_img), "UNREVIEWED"])
        writer.writerow(["rej.jpg", str(rej_img), "REJECT_QUALITY"])

    loaded = load_approved_negatives_from_review_csv(csv_path, original_dataset_dir=tmp_path)
    assert len(loaded) == 0


# 13. cross-source dedup
def test_13_cross_source_dedup(mock_benchmark_dataset: Path, tmp_path: Path):
    img_shared = tmp_path / "shared_neg.jpg"
    img_shared.write_bytes(b"identical_negative_content")

    # CSV 1 and CSV 2 reference images with identical hash
    csv1 = tmp_path / "csv1.csv"
    with open(csv1, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        writer.writerow(["neg1.jpg", str(img_shared), "ACCEPT_NEGATIVE"])

    csv2 = tmp_path / "csv2.csv"
    with open(csv2, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        writer.writerow(["neg2.jpg", str(img_shared), "ACCEPT_NEGATIVE"])

    v2_dir = tmp_path / "v2_dedup"
    summary = prepare_v2_dataset(
        original_dataset=mock_benchmark_dataset,
        v2_output_dir=v2_dir,
        review_csv=[csv1, csv2],
        negative_repeat=1,
    )
    # Deduplicated by SHA-256: 1 unique instance
    assert summary["approved_negatives_unique"] == 1


# 14. benchmark leakage abort
def test_14_benchmark_leakage_abort(mock_benchmark_dataset: Path, tmp_path: Path):
    # Create candidate with identical content as benchmark valid_01.jpg
    leak_img = tmp_path / "leak.jpg"
    leak_img.write_bytes(b"bench_valid_01")

    csv_p = tmp_path / "leak.csv"
    with open(csv_p, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        writer.writerow(["leak.jpg", str(leak_img), "ACCEPT_NEGATIVE"])

    v2_dir = tmp_path / "v2_leak"
    with pytest.raises(RuntimeError, match="DATA LEAKAGE ERROR"):
        prepare_v2_dataset(mock_benchmark_dataset, v2_dir, review_csv=csv_p)


# 15. benchmark valid unchanged
def test_15_benchmark_valid_unchanged(mock_benchmark_dataset: Path, tmp_path: Path):
    clean_neg = tmp_path / "clean_sample.jpg"
    clean_neg.write_bytes(b"unique_clean_neg_data")

    csv_p = tmp_path / "clean.csv"
    with open(csv_p, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        writer.writerow(["clean_sample.jpg", str(clean_neg), "ACCEPT_NEGATIVE"])

    v2_dir = tmp_path / "v2_valid_check"
    prepare_v2_dataset(mock_benchmark_dataset, v2_dir, review_csv=csv_p)

    orig_val_bytes = (mock_benchmark_dataset / "valid" / "images" / "valid_01.jpg").read_bytes()
    v2_val_bytes = (v2_dir / "valid" / "images" / "valid_01.jpg").read_bytes()
    assert orig_val_bytes == v2_val_bytes


# 16. benchmark test unchanged
def test_16_benchmark_test_unchanged(mock_benchmark_dataset: Path, tmp_path: Path):
    clean_neg = tmp_path / "clean_sample2.jpg"
    clean_neg.write_bytes(b"unique_clean_neg_data2")

    csv_p = tmp_path / "clean2.csv"
    with open(csv_p, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        writer.writerow(["clean_sample2.jpg", str(clean_neg), "ACCEPT_NEGATIVE"])

    v2_dir = tmp_path / "v2_test_check"
    prepare_v2_dataset(mock_benchmark_dataset, v2_dir, review_csv=csv_p)

    orig_test_bytes = (mock_benchmark_dataset / "test" / "images" / "test_01.jpg").read_bytes()
    v2_test_bytes = (v2_dir / "test" / "images" / "test_01.jpg").read_bytes()
    assert orig_test_bytes == v2_test_bytes


# 17. repeat=1 recommendation for large pool
def test_17_repeat_recommendation_for_large_pool(mock_benchmark_dataset: Path, tmp_path: Path):
    # Simulate a CSV with 500 negatives
    csv_p = tmp_path / "large_neg.csv"
    with open(csv_p, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        for i in range(500):
            p = tmp_path / f"large_neg_{i}.jpg"
            p.write_bytes(f"neg_content_{i}".encode("utf-8"))
            writer.writerow([f"large_neg_{i}.jpg", str(p), "ACCEPT_NEGATIVE"])

    v2_dir = tmp_path / "v2_large"
    summary = prepare_v2_dataset(
        mock_benchmark_dataset,
        v2_dir,
        review_csv=csv_p,
        negative_repeat=2,
        dry_run=True,
    )
    assert summary["recommended_repeat"] == 1


# 18. negative percentage calculation
def test_18_negative_percentage_calculation(mock_benchmark_dataset: Path, tmp_path: Path):
    neg_p = tmp_path / "neg_pct.jpg"
    neg_p.write_bytes(b"neg_pct_bytes")

    csv_p = tmp_path / "neg_pct.csv"
    with open(csv_p, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "source_path", "review_status"])
        writer.writerow(["neg_pct.jpg", str(neg_p), "ACCEPT_NEGATIVE"])

    # mock_benchmark_dataset has 1 train image. With 1 negative added, total = 2 (50.0%)
    v2_dir = tmp_path / "v2_pct"
    summary = prepare_v2_dataset(
        mock_benchmark_dataset,
        v2_dir,
        review_csv=csv_p,
        negative_repeat=1,
        dry_run=True,
    )
    assert summary["original_train_count"] == 1
    assert summary["v2_train_total"] == 2
    assert summary["negative_fraction_percentage"] == 50.0
    assert summary["negative_balance_exceeds_threshold"] is True


# 19. Modal script still valid
def test_19_modal_script_still_valid():
    modal_script_p = Path("scripts/modal_train_yolo_v2.py")
    assert modal_script_p.exists()
    content = modal_script_p.read_text(encoding="utf-8")

    # Architecture checks
    assert 'gpu="A10G"' in content
    assert "/root/best_v1.pt" in content
    assert "/root/oral-disease-v2.zip" in content
    assert "daantshaant-yolo-v2-output" in content
    assert "modal_yaml = Path(" in content

    # Hyperparameters
    assert "epochs=12" in content
    assert "imgsz=640" in content
    assert "batch=16" in content
    assert "workers=8" in content
    assert "patience=4" in content
    assert 'optimizer="AdamW"' in content
    assert "lr0=0.0005" in content
    assert "close_mosaic=3" in content
    assert "seed=42" in content
    assert "plots=True" in content
