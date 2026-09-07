"""Test suite for Phase 11B-1: YOLO Detector Calibration + Hard Negatives.

Tests all 13 requirements specified in Phase 11B-1 Section 19:
1. global confidence fallback works
2. each class override works
3. discoloration threshold is independent
4. calculus threshold is independent
5. low-confidence boxes filter correctly
6. dataset audit counts empty labels correctly
7. hard-negative image gets empty label
8. original dataset is never mutated
9. deterministic split reproducible
10. quality warning does NOT derive from YOLO confidence
11. detector moderate confidence does not claim low image quality
12. no-detection conservative wording preserved
13. model path switch works without code changes
"""

from __future__ import annotations

from pathlib import Path
import random
import shutil
import tempfile
from unittest.mock import MagicMock, patch
import uuid

import numpy as np
import pytest

from dantshaant_common.schemas import (
    ActionTrigger,
    ConditionLabel,
    DiagnoseRequest,
    VisualFinding,
)
from diagnosis.classifier import BELOW_THRESHOLD_LIMITATION, diagnose
from orchestrator.clinical.report_generator import build_deterministic_report_text
from scripts.audit_yolo_dataset import audit_split
from scripts.prepare_yolo_v2_dataset import prepare_v2_dataset
from teeth_analyzer.config import Settings, get_confidence_threshold, settings
from teeth_analyzer.yolo_detector import (
    DentalDetection,
    aggregate_detections,
    findings_to_visual_findings,
    get_yolo_model,
    reset_yolo_model,
    run_yolo_detection,
)


# 1. Global confidence fallback works
def test_1_global_confidence_fallback():
    s = Settings(_env_file=None, yolo_dental_confidence_threshold=0.50)
    assert get_confidence_threshold("calculus", s) == 0.50
    assert get_confidence_threshold("tartar", s) == 0.50
    assert get_confidence_threshold("tooth discoloration", s) == 0.50
    assert get_confidence_threshold("discoloration", s) == 0.50
    assert get_confidence_threshold("caries", s) == 0.50
    assert get_confidence_threshold("cavity_suspect", s) == 0.50
    assert get_confidence_threshold("gingivitis", s) == 0.50
    assert get_confidence_threshold("ulcer", s) == 0.50
    assert get_confidence_threshold("unknown_class", s) == 0.50


# 2. Each class override works
def test_2_each_class_override_works():
    s = Settings(
        _env_file=None,
        yolo_dental_confidence_threshold=0.50,
        yolo_calculus_confidence_threshold=0.55,
        yolo_caries_confidence_threshold=0.60,
        yolo_gingivitis_confidence_threshold=0.62,
        yolo_discoloration_confidence_threshold=0.68,
        yolo_ulcer_confidence_threshold=0.72,
    )
    assert get_confidence_threshold("calculus", s) == 0.55
    assert get_confidence_threshold("tartar", s) == 0.55
    assert get_confidence_threshold("caries", s) == 0.60
    assert get_confidence_threshold("cavity_suspect", s) == 0.60
    assert get_confidence_threshold("gingivitis", s) == 0.62
    assert get_confidence_threshold("gingivitis_signs", s) == 0.62
    assert get_confidence_threshold("tooth discoloration", s) == 0.68
    assert get_confidence_threshold("discoloration", s) == 0.68
    assert get_confidence_threshold("ulcer", s) == 0.72
    assert get_confidence_threshold("oral_ulcer", s) == 0.72


# 3. Discoloration threshold is independent
def test_3_discoloration_threshold_is_independent():
    s = Settings(
        _env_file=None,
        yolo_dental_confidence_threshold=0.50,
        yolo_discoloration_confidence_threshold=0.65,
    )
    assert get_confidence_threshold("discoloration", s) == 0.65
    assert get_confidence_threshold("tooth discoloration", s) == 0.65
    # Other classes must remain at 0.50
    assert get_confidence_threshold("calculus", s) == 0.50
    assert get_confidence_threshold("caries", s) == 0.50
    assert get_confidence_threshold("gingivitis", s) == 0.50
    assert get_confidence_threshold("ulcer", s) == 0.50


# 4. Calculus threshold is independent
def test_4_calculus_threshold_is_independent():
    s = Settings(
        _env_file=None,
        yolo_dental_confidence_threshold=0.50,
        yolo_calculus_confidence_threshold=0.75,
    )
    assert get_confidence_threshold("calculus", s) == 0.75
    assert get_confidence_threshold("tartar", s) == 0.75
    # Discoloration must remain at global fallback 0.50
    assert get_confidence_threshold("discoloration", s) == 0.50
    assert get_confidence_threshold("caries", s) == 0.50


# 5. Low-confidence boxes filter correctly
def test_5_low_confidence_boxes_filter_correctly():
    fake_model = MagicMock()
    fake_boxes = MagicMock()
    # 2 detections: discoloration at 0.58, caries at 0.72
    fake_boxes.xyxy.cpu().numpy.return_value = np.array(
        [[10.0, 10.0, 50.0, 50.0], [60.0, 60.0, 100.0, 100.0]]
    )
    fake_boxes.conf.cpu().numpy.return_value = np.array([0.58, 0.72])
    fake_boxes.cls.cpu().numpy.return_value = np.array([3, 1])  # 3: tooth discoloration, 1: caries
    fake_boxes.__len__.return_value = 2

    fake_res = MagicMock()
    fake_res.boxes = fake_boxes
    fake_res.names = {1: "caries", 3: "tooth discoloration"}
    fake_model.predict.return_value = [fake_res]

    img = np.zeros((200, 200, 3), dtype=np.uint8)

    # When discoloration threshold is set to 0.65 (higher than 0.58),
    # the 0.58 discoloration box must be filtered out while caries 0.72 is kept.
    with patch("teeth_analyzer.yolo_detector.get_confidence_threshold") as mock_thresh:
        mock_thresh.side_effect = lambda cls_name: 0.65 if "discoloration" in cls_name else 0.50
        result = run_yolo_detection(img, model=fake_model)

    assert len(result.detections) == 1
    assert result.detections[0].normalized_type == "cavity_suspect"
    assert result.detections[0].confidence == 0.72
    assert "discoloration" not in result.detection_counts_by_class


# 6. Dataset audit counts empty labels correctly
def test_6_dataset_audit_counts_empty_labels_correctly(tmp_path: Path):
    split_dir = tmp_path / "valid"
    images_dir = split_dir / "images"
    labels_dir = split_dir / "labels"
    images_dir.mkdir(parents=True)
    labels_dir.mkdir(parents=True)

    # Image 1: has boxes
    (images_dir / "pos_1.jpg").write_bytes(b"fake_jpg_1")
    (labels_dir / "pos_1.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    # Image 2: empty label file (true negative)
    (images_dir / "neg_1.jpg").write_bytes(b"fake_jpg_2")
    (labels_dir / "neg_1.txt").write_text("", encoding="utf-8")

    res = audit_split(split_dir)
    assert res["total_images"] == 2
    assert res["images_with_boxes"] == 1
    assert res["empty_label_images"] == 1
    assert res["total_boxes"] == 1


# 7. Hard-negative image gets empty label
def test_7_hard_negative_image_gets_empty_label(tmp_path: Path):
    orig_dir = tmp_path / "orig"
    for s in ["train", "valid", "test"]:
        (orig_dir / s / "images").mkdir(parents=True)
        (orig_dir / s / "labels").mkdir(parents=True)

    hard_dir = tmp_path / "hard_negatives"
    (hard_dir / "images").mkdir(parents=True)
    (hard_dir / "labels").mkdir(parents=True)

    # Drop 2 hard negative images
    (hard_dir / "images" / "clean_teeth_1.jpg").write_bytes(b"clean1")
    (hard_dir / "images" / "clean_teeth_2.jpg").write_bytes(b"clean2")

    v2_dir = tmp_path / "v2"
    prepare_v2_dataset(orig_dir, hard_dir, v2_dir, seed=42)

    # Check that in v2, every hard negative image has a matching 0-byte label file
    labels_created = list(v2_dir.glob("**/labels/neg_*.txt"))
    assert len(labels_created) == 2
    for lbl in labels_created:
        assert lbl.stat().st_size == 0
        assert lbl.read_text(encoding="utf-8") == ""


# 8. Original dataset is never mutated
def test_8_original_dataset_is_never_mutated(tmp_path: Path):
    orig_dir = tmp_path / "orig"
    (orig_dir / "train" / "images").mkdir(parents=True)
    (orig_dir / "train" / "labels").mkdir(parents=True)
    (orig_dir / "train" / "images" / "orig_img.jpg").write_bytes(b"orig_bytes")
    (orig_dir / "train" / "labels" / "orig_img.txt").write_text("1 0.5 0.5 0.1 0.1\n", encoding="utf-8")

    hard_dir = tmp_path / "hard_neg"
    (hard_dir / "images").mkdir(parents=True)
    (hard_dir / "images" / "neg.jpg").write_bytes(b"neg_bytes")

    v2_dir = tmp_path / "v2"
    prepare_v2_dataset(orig_dir, hard_dir, v2_dir, seed=42)

    # Original train files must remain exactly 1 image and 1 label with identical content
    orig_imgs = list((orig_dir / "train" / "images").iterdir())
    orig_lbls = list((orig_dir / "train" / "labels").iterdir())
    assert len(orig_imgs) == 1
    assert len(orig_lbls) == 1
    assert orig_lbls[0].read_text(encoding="utf-8") == "1 0.5 0.5 0.1 0.1\n"


# 9. Deterministic split reproducible
def test_9_deterministic_split_reproducible(tmp_path: Path):
    orig_dir = tmp_path / "orig"
    for s in ["train", "valid", "test"]:
        (orig_dir / s / "images").mkdir(parents=True)
        (orig_dir / s / "labels").mkdir(parents=True)

    hard_dir = tmp_path / "hard_neg"
    (hard_dir / "images").mkdir(parents=True)
    for i in range(10):
        (hard_dir / "images" / f"neg_{i}.jpg").write_bytes(f"bytes_{i}".encode())

    v2_dir_1 = tmp_path / "v2_run1"
    v2_dir_2 = tmp_path / "v2_run2"

    prepare_v2_dataset(orig_dir, hard_dir, v2_dir_1, seed=42)
    prepare_v2_dataset(orig_dir, hard_dir, v2_dir_2, seed=42)

    # Files placed in train, valid, test must match exactly across both runs
    train_files_1 = sorted([p.name for p in (v2_dir_1 / "train" / "images").iterdir()])
    train_files_2 = sorted([p.name for p in (v2_dir_2 / "train" / "images").iterdir()])
    assert train_files_1 == train_files_2

    val_files_1 = sorted([p.name for p in (v2_dir_1 / "valid" / "images").iterdir()])
    val_files_2 = sorted([p.name for p in (v2_dir_2 / "valid" / "images").iterdir()])
    assert val_files_1 == val_files_2


# 10. Quality warning does NOT derive from YOLO confidence
def test_10_quality_warning_does_not_derive_from_yolo_confidence():
    # Sharp image (overall_quality_score=0.92) but moderate confidence (0.55)
    request = DiagnoseRequest(
        user_id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        findings=[VisualFinding(label="cavity_advanced", confidence=0.55, region="general")],
        overall_quality_score=0.92,
    )
    resp = diagnose(request)
    # Must NOT trigger REQUEST_CLEARER_PHOTO because physical quality is high
    assert resp.action_trigger != ActionTrigger.REQUEST_CLEARER_PHOTO
    assert resp.meets_threshold is False
    # Urgency must still reflect the detected clinical finding
    assert resp.condition_label == ConditionLabel.ADVANCED_CAVITY


# 11. Detector moderate confidence does not claim low image quality
def test_11_moderate_confidence_does_not_claim_low_quality():
    request = DiagnoseRequest(
        user_id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        findings=[VisualFinding(label="cavity_advanced", confidence=0.60, region="general")],
        overall_quality_score=0.90,
    )
    resp = diagnose(request)
    assert resp.meets_threshold is False
    assert resp.triage is not None

    # Verify that the below-threshold limitation states moderate confidence rather than blurry photo
    limitations_text = " ".join(resp.triage.limitations)
    assert "Moderate screening confidence" in limitations_text
    assert "clearer, well-lit photo" not in limitations_text


# 12. No-detection conservative wording preserved
def test_12_no_detection_conservative_wording_preserved():
    visual_findings = findings_to_visual_findings([])
    assert len(visual_findings) == 1
    assert visual_findings[0].label == "healthy_tissue"

    # Test report text generation with empty findings
    report = build_deterministic_report_text(
        findings=[],
        triage={
            "condition_summary": "Routine oral health",
            "urgency_level": "routine",
            "recommended_actions": ["Maintain good oral hygiene"],
            "recommended_specialist": "general dentist",
        },
    )
    # Must preserve non-definitive wording
    assert "no obvious concerning findings" in report.summary
    assert "Healthy teeth" not in report.summary
    assert "Perfectly healthy" not in report.summary


# 13. Model path switch works without code changes
def test_13_model_path_switch_works_without_code_changes(monkeypatch):
    custom_path = "services/teeth_analyzer/models/oral_disease/best_v2.pt"
    monkeypatch.setenv("YOLO_DENTAL_MODEL_PATH", custom_path)
    monkeypatch.setenv("TEETH_ANALYZER_YOLO_DENTAL_MODEL_PATH", custom_path)
    s = Settings(yolo_dental_model_path=custom_path)
    assert s.yolo_dental_model_path == custom_path

    # Verify YoloDetectionResult derives model_version from filename stem
    fake_model = MagicMock()
    fake_boxes = MagicMock()
    fake_boxes.xyxy.cpu().numpy.return_value = np.empty((0, 4))
    fake_boxes.conf.cpu().numpy.return_value = np.empty((0,))
    fake_boxes.cls.cpu().numpy.return_value = np.empty((0,))
    fake_boxes.__len__.return_value = 0
    fake_res = MagicMock()
    fake_res.boxes = fake_boxes
    fake_model.predict.return_value = [fake_res]

    img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("teeth_analyzer.yolo_detector.settings", s):
        result = run_yolo_detection(img, model=fake_model)
    assert result.model_version == "best_v2"


# 14. Phase 11B Final Frozen Engineering Thresholds
def test_14_phase11b_final_frozen_thresholds():
    """Verify the exact frozen engineering screening thresholds for Phase 11B.

    calculus -> 0.35
    caries -> 0.55
    gingivitis -> 0.50
    tooth discoloration -> 0.65
    ulcer -> 0.65
    unknown/unconfigured fallback -> 0.50
    """
    # Verify active production configuration (loaded from .env)
    prod_settings = Settings()
    assert prod_settings.yolo_dental_confidence_threshold == 0.50
    assert prod_settings.yolo_calculus_confidence_threshold == 0.35
    assert prod_settings.yolo_caries_confidence_threshold == 0.55
    assert prod_settings.yolo_gingivitis_confidence_threshold == 0.50
    assert prod_settings.yolo_discoloration_confidence_threshold == 0.65
    assert prod_settings.yolo_ulcer_confidence_threshold == 0.65

    # Test raw YOLO labels
    assert get_confidence_threshold("calculus", prod_settings) == 0.35
    assert get_confidence_threshold("caries", prod_settings) == 0.55
    assert get_confidence_threshold("gingivitis", prod_settings) == 0.50
    assert get_confidence_threshold("tooth discoloration", prod_settings) == 0.65
    assert get_confidence_threshold("ulcer", prod_settings) == 0.65

    # Test normalized clinical codes
    assert get_confidence_threshold("tartar", prod_settings) == 0.35
    assert get_confidence_threshold("cavity_suspect", prod_settings) == 0.55
    assert get_confidence_threshold("gingivitis_signs", prod_settings) == 0.50
    assert get_confidence_threshold("discoloration", prod_settings) == 0.65
    assert get_confidence_threshold("oral_ulcer", prod_settings) == 0.65

    # Test unconfigured/unknown class fallback to global 0.50
    assert get_confidence_threshold("healthy_tissue", prod_settings) == 0.50
    assert get_confidence_threshold("unknown_pathology", prod_settings) == 0.50


# 15. DentalTensor Vision v1.0 Model Checkpoint, SHA256 Verification & Loader
def test_15_dentaltensor_v1_checkpoint_and_loader():
    """Verify DentalTensor branded checkpoint, byte-for-byte match with best_v2.pt, and rollback retention."""
    import hashlib

    repo_root = Path(__file__).resolve().parents[3]
    v1_baseline = repo_root / "services" / "teeth_analyzer" / "models" / "oral_disease" / "best.pt"
    v2_checkpoint = repo_root / "services" / "teeth_analyzer" / "models" / "oral_disease" / "best_v2.pt"
    branded_checkpoint = (
        repo_root / "services" / "teeth_analyzer" / "models" / "oral_disease" / "dentaltensor_nathan_asif_v1.pt"
    )

    # All three binaries must physically exist on disk
    assert v1_baseline.is_file(), "V1 baseline best.pt must be retained as rollback checkpoint"
    assert v2_checkpoint.is_file(), "V2 checkpoint best_v2.pt must be retained as rollback checkpoint"
    assert branded_checkpoint.is_file(), "Branded checkpoint dentaltensor_nathan_asif_v1.pt must exist"

    # Verify SHA256 byte-for-byte equality between best_v2.pt and dentaltensor_nathan_asif_v1.pt
    with open(v2_checkpoint, "rb") as f_v2, open(branded_checkpoint, "rb") as f_branded:
        sha_v2 = hashlib.sha256(f_v2.read()).hexdigest()
        sha_branded = hashlib.sha256(f_branded.read()).hexdigest()
    assert sha_v2 == sha_branded, "Branded checkpoint must match best_v2.pt byte-for-byte"

    # Verify active production configuration resolves dentaltensor_nathan_asif_v1.pt
    prod_settings = Settings()
    assert "dentaltensor_nathan_asif_v1.pt" in prod_settings.yolo_dental_model_path

    # Verify lazy singleton loader honors configured branded path
    reset_yolo_model()
    fake_yolo_cls = MagicMock()
    fake_instance = MagicMock()
    fake_yolo_cls.return_value = fake_instance

    mock_ultralytics = MagicMock()
    mock_ultralytics.YOLO = fake_yolo_cls

    with patch.dict("sys.modules", {"ultralytics": mock_ultralytics}):
        model = get_yolo_model(model_path=prod_settings.yolo_dental_model_path)
        assert model is fake_instance
        # Assert YOLO was instantiated with the resolved branded path
        fake_yolo_cls.assert_called_once()
        called_path = str(fake_yolo_cls.call_args[0][0])
        assert called_path.endswith("dentaltensor_nathan_asif_v1.pt")

    reset_yolo_model()


# 16. DentalTensor Brand Identity & Backward-Compatible Output Metadata
def test_16_dentaltensor_brand_identity_and_compatibility():
    """Verify canonical DentalTensor metadata, developer attribution, and result schema compatibility."""
    from teeth_analyzer.config import (
        DENTALTENSOR_DEVELOPER,
        DENTALTENSOR_MODEL_DISPLAY_NAME,
        DENTALTENSOR_MODEL_NAME,
        DENTALTENSOR_MODEL_VERSION,
    )
    from teeth_analyzer.yolo_detector import YoloDetectionResult

    prod_settings = Settings()
    assert DENTALTENSOR_MODEL_NAME == "DentalTensor Vision"
    assert DENTALTENSOR_MODEL_VERSION == "1.0"
    assert DENTALTENSOR_MODEL_DISPLAY_NAME == "DentalTensor Vision v1.0"
    assert DENTALTENSOR_DEVELOPER == "Nathan Asif"

    assert prod_settings.dentaltensor_model_name == "DentalTensor Vision"
    assert prod_settings.dentaltensor_model_version == "1.0"
    assert prod_settings.dentaltensor_model_display_name == "DentalTensor Vision v1.0"
    assert prod_settings.dentaltensor_developer == "Nathan Asif"

    # Verify YoloDetectionResult identifies DentalTensor Vision v1.0
    res = YoloDetectionResult()
    assert res.model == "DentalTensor Vision v1.0"
    assert res.model_version == "dentaltensor-vision-v1.0"
    assert res.threshold == 0.50
    assert hasattr(res, "detections")
    assert hasattr(res, "findings")
    assert hasattr(res, "inference_ms")

