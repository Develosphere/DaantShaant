"""DentalTensor Vision — Custom Oral Pathology Detector.
Developed by Nathan Asif.

Product: DentalTensor
Full Model Name: DentalTensor Vision v1.0
Model Type: YOLO11n-based oral pathology computer-vision detector
Primary Integration: DaantShaant

Roboflow Universe: oral-disease (di-qidb9/oral-disease-tabrb)
Classes (LOCKED):
  - calculus           -> tartar
  - caries             -> cavity_suspect
  - gingivitis         -> gingivitis_signs
  - tooth discoloration -> discoloration
  - ulcer              -> oral_ulcer

Responsibilities:
- Lazy-load DentalTensor Vision model once (singleton)
- Accept preprocessed image
- Run local inference via ultralytics
- Filter by centralized confidence threshold (default: 0.50)
- Aggregate detections spatially (generalized vs localized)
- Return structured internal objects
- Never perform patient-facing language generation
- Never determine final clinical urgency (delegated to deterministic triage)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from dantshaant_common.schemas import VisualFinding
from teeth_analyzer.config import get_confidence_threshold, settings

logger = logging.getLogger(__name__)

# --- Locked Class Map (Phase 11A Section 8) ---
# DO NOT invent new disease classes.
# DO NOT map discoloration to calculus, caries, fluorosis, or amelogenesis imperfecta.
YOLO_CLASS_MAP: dict[str, str] = {
    "calculus": "tartar",
    "caries": "cavity_suspect",
    "gingivitis": "gingivitis_signs",
    "tooth discoloration": "discoloration",
    "ulcer": "oral_ulcer",
}

# Inverted mapping for normalization lookup
_NORMALIZED_TO_CANONICAL = {v: k for k, v in YOLO_CLASS_MAP.items()}


class YoloDetectorError(RuntimeError):
    """Base exception for YOLO detector failures."""
    pass


class YoloModelNotFoundError(YoloDetectorError):
    """Model weight binary was not found on disk."""
    pass


class YoloInferenceError(YoloDetectorError):
    """Model loading or forward-pass inference crashed."""
    pass


@dataclass(frozen=True)
class DentalDetection:
    """One raw bounding-box detection from the YOLO model."""

    class_name: str  # raw label from YOLO model (e.g., 'calculus', 'tooth discoloration')
    normalized_type: str  # mapped clinical code (e.g., 'tartar', 'discoloration')
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]  # (x1, y1, x2, y2) in pixels
    bbox_normalized: tuple[float, float, float, float] | None = None
    area_ratio: float | None = None
    center_x: float | None = None
    center_y: float | None = None


@dataclass(frozen=True)
class AggregatedFinding:
    """Spatially aggregated clinical finding from one or more bounding boxes."""

    type: str  # e.g., 'discoloration', 'tartar', 'cavity_suspect', 'oral_ulcer'
    confidence: float
    distribution: str  # 'localized' | 'multiple' | 'generalized'
    detection_count: int
    source: str = "yolo"
    bbox_xyxy: tuple[float, float, float, float] | None = None
    # Diagnostic metadata (Phase 11B-1 Section 11) — internal evaluation only
    max_confidence: float | None = None
    mean_confidence: float | None = None
    horizontal_coverage: float | None = None
    aggregate_area_ratio: float | None = None
    image_third_coverage: tuple[str, ...] = ()


@dataclass
class YoloDetectionResult:
    """Complete structured output from DentalTensor Vision perception and aggregation."""

    model: str = "DentalTensor Vision v1.0"
    detections: list[DentalDetection] = field(default_factory=list)
    findings: list[AggregatedFinding] = field(default_factory=list)
    inference_ms: int = 0
    model_version: str = "dentaltensor-vision-v1.0"
    threshold: float = 0.50
    detection_counts_by_class: dict[str, int] = field(default_factory=dict)


# --- Lazy Model Singleton ---
_MODEL_INSTANCE: Any = None
_LOADED_MODEL_PATH: str | None = None


def get_yolo_model(model_path: str | None = None) -> Any:
    """Lazy-load the YOLO model once into memory as a singleton."""
    global _MODEL_INSTANCE, _LOADED_MODEL_PATH

    path_str = model_path or settings.yolo_dental_model_path
    resolved_path = Path(path_str)

    # If relative, resolve against repo root or cwd
    if not resolved_path.is_absolute():
        repo_root = Path(__file__).resolve().parents[4]
        candidate = repo_root / resolved_path
        if candidate.is_file():
            resolved_path = candidate
        else:
            resolved_path = Path.cwd() / resolved_path

    if _MODEL_INSTANCE is not None and _LOADED_MODEL_PATH == str(resolved_path):
        return _MODEL_INSTANCE

    if not resolved_path.is_file():
        raise YoloModelNotFoundError(
            f"DentalTensor Vision model file not found at '{resolved_path}'. "
            f"Please verify '{settings.yolo_dental_model_path}'."
        )

    try:
        from ultralytics import YOLO

        logger.info("Loading %s", settings.dentaltensor_model_display_name)
        logger.info("Developer: %s", settings.dentaltensor_developer)
        logger.info("Checkpoint: %s", resolved_path)
        model = YOLO(str(resolved_path))
        _MODEL_INSTANCE = model
        _LOADED_MODEL_PATH = str(resolved_path)
        return model
    except Exception as exc:
        raise YoloInferenceError(f"Failed to load DentalTensor Vision model from '{resolved_path}': {exc}") from exc


def reset_yolo_model() -> None:
    """Reset singleton for testing purposes."""
    global _MODEL_INSTANCE, _LOADED_MODEL_PATH
    _MODEL_INSTANCE = None
    _LOADED_MODEL_PATH = None


def normalize_yolo_class(raw_name: str) -> str:
    """Map raw YOLO class name to locked DaantShaant finding code."""
    key = raw_name.strip().lower()
    return YOLO_CLASS_MAP.get(key, key.replace(" ", "_"))


def aggregate_detections(
    detections: list[DentalDetection],
    image_width: int,
    image_height: int,
) -> list[AggregatedFinding]:
    """Deterministically aggregate bounding boxes into clinical findings.

    Heuristics:
    - Group by normalized class.
    - Distribution heuristic:
      * 1 box: 'localized'
      * 2-3 boxes: 'multiple' (or 'generalized' if spanning >50% horizontal width)
      * >=4 boxes or horizontal coverage >=0.35: 'generalized'
    - Discoloration safety:
      * Tooth discoloration is NEVER converted to tartar/calculus.
      * If both discoloration and calculus exist, both are preserved separately.
      * Broadly spread discoloration produces distribution='generalized'.
    """
    if not detections:
        return []

    # Group by normalized_type
    by_class: dict[str, list[DentalDetection]] = {}
    for d in detections:
        by_class.setdefault(d.normalized_type, []).append(d)

    findings: list[AggregatedFinding] = []

    for norm_type, boxes in by_class.items():
        count = len(boxes)
        # Confidence: highest detected confidence for this condition
        max_conf = max(b.confidence for b in boxes)

        # Horizontal image coverage
        min_x1 = min(b.bbox_xyxy[0] for b in boxes)
        max_x2 = max(b.bbox_xyxy[2] for b in boxes)
        coverage_width = max(0.0, max_x2 - min_x1)
        horizontal_ratio = coverage_width / max(1.0, float(image_width))

        # Check region spread across horizontal thirds
        # left (< 0.35), center (0.35 - 0.65), right (> 0.65)
        thirds_hit = set()
        for b in boxes:
            cx = (b.center_x or ((b.bbox_xyxy[0] + b.bbox_xyxy[2]) / 2.0)) / max(1.0, float(image_width))
            if cx < 0.35:
                thirds_hit.add("left")
            elif cx <= 0.65:
                thirds_hit.add("center")
            else:
                thirds_hit.add("right")

        # Distribution classification
        if count >= 4 and (horizontal_ratio >= 0.35 or len(thirds_hit) >= 2):
            distribution = "generalized"
        elif count >= 3 and (horizontal_ratio >= 0.45 or len(thirds_hit) >= 3):
            distribution = "generalized"
        elif norm_type == "discoloration" and (horizontal_ratio >= 0.40 or len(thirds_hit) >= 2):
            # Generalized yellow teeth heuristic: wide horizontal spread
            distribution = "generalized"
        elif count > 1:
            distribution = "multiple"
        else:
            distribution = "localized"

        # Representative bounding box (union bounding box)
        min_y1 = min(b.bbox_xyxy[1] for b in boxes)
        max_y2 = max(b.bbox_xyxy[3] for b in boxes)
        union_box = (float(min_x1), float(min_y1), float(max_x2), float(max_y2))

        mean_conf = round(float(sum(b.confidence for b in boxes) / count), 4)
        total_area = round(float(sum(b.area_ratio or 0.0 for b in boxes)), 6)
        thirds_tuple = tuple(sorted(thirds_hit))

        findings.append(
            AggregatedFinding(
                type=norm_type,
                confidence=round(float(max_conf), 4),
                distribution=distribution,
                detection_count=count,
                source="yolo",
                bbox_xyxy=union_box,
                max_confidence=round(float(max_conf), 4),
                mean_confidence=mean_conf,
                horizontal_coverage=round(float(horizontal_ratio), 4),
                aggregate_area_ratio=total_area,
                image_third_coverage=thirds_tuple,
            )
        )

    # Sort deterministically by priority: cavity_suspect > oral_ulcer > tartar > gingivitis_signs > discoloration
    priority = {
        "cavity_suspect": 0,
        "oral_ulcer": 1,
        "tartar": 2,
        "gingivitis_signs": 3,
        "discoloration": 4,
    }
    findings.sort(key=lambda f: (priority.get(f.type, 99), -f.confidence))
    return findings


def run_yolo_detection(
    image: np.ndarray | bytes,
    model: Any | None = None,
    threshold: float | None = None,
) -> YoloDetectionResult:
    """Run local YOLO inference on a preprocessed image array (BGR/RGB) or JPEG bytes.

    Filters raw detections by class-specific or explicit confidence threshold,
    applies spatial aggregation with diagnostic metadata, and returns structured result.
    """
    if threshold is not None:
        min_predict_conf = threshold
        conf_thresh = threshold
    else:
        conf_thresh = settings.yolo_dental_confidence_threshold
        # Check all class-specific overrides to find minimum threshold for predict
        all_class_thresholds = [
            get_confidence_threshold("calculus"),
            get_confidence_threshold("caries"),
            get_confidence_threshold("gingivitis"),
            get_confidence_threshold("tooth discoloration"),
            get_confidence_threshold("ulcer"),
        ]
        min_predict_conf = min(all_class_thresholds)

    start_time = time.perf_counter()

    if isinstance(image, (bytes, bytearray)):
        try:
            import cv2
            arr = np.frombuffer(image, dtype=np.uint8)
            decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if decoded is None:
                raise ValueError("cv2.imdecode returned None")
            image = decoded
        except Exception:
            try:
                import io
                from PIL import Image
                pil_img = Image.open(io.BytesIO(image)).convert("RGB")
                image = np.array(pil_img)[:, :, ::-1]
            except Exception as exc:
                raise YoloInferenceError(f"Failed to decode image bytes for YOLO inference: {exc}") from exc

    if model is None:
        model = get_yolo_model()

    h, w = image.shape[:2]

    try:
        # Run inference with YOLO's built-in NMS
        # min_predict_conf ensures no candidate box is prematurely dropped before class thresholding
        results = model.predict(
            source=image,
            conf=min_predict_conf,
            iou=0.45,
            verbose=False,
        )
    except Exception as exc:
        raise YoloInferenceError(f"YOLO forward pass failed: {exc}") from exc

    loaded_model_id = getattr(model, "ckpt_path", None) or _LOADED_MODEL_PATH or settings.yolo_dental_model_path
    logger.debug("YOLO loaded model: %s", loaded_model_id)

    raw_detections: list[DentalDetection] = []
    class_counts: dict[str, int] = {}

    if results and len(results) > 0:
        res = results[0]
        boxes = getattr(res, "boxes", None)
        names = getattr(res, "names", {})

        if boxes is not None and len(boxes) > 0:
            xyxy_list = boxes.xyxy.cpu().numpy()
            conf_list = boxes.conf.cpu().numpy()
            cls_list = boxes.cls.cpu().numpy()

            for i in range(len(cls_list)):
                conf = float(conf_list[i])
                cls_idx = int(cls_list[i])
                raw_label = names.get(cls_idx, str(cls_idx))
                norm_type = normalize_yolo_class(raw_label)

                # Class-specific confidence threshold resolver (Phase 11B-1 Section 5)
                class_thresh = threshold if threshold is not None else get_confidence_threshold(raw_label)
                decision = "KEEP" if conf >= class_thresh else "DROP"
                logger.debug(
                    "YOLO detection: cls_idx=%d class_name=%s conf=%.4f threshold=%.2f -> %s",
                    cls_idx,
                    raw_label,
                    conf,
                    class_thresh,
                    decision,
                )
                if conf < class_thresh:
                    continue

                box = xyxy_list[i]
                x1, y1, x2, y2 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
                img_area = max(1.0, float(w * h))
                area_ratio = area / img_area

                norm_box = (
                    round(x1 / w, 4),
                    round(y1 / h, 4),
                    round(x2 / w, 4),
                    round(y2 / h, 4),
                )

                detection = DentalDetection(
                    class_name=raw_label,
                    normalized_type=norm_type,
                    confidence=round(conf, 4),
                    bbox_xyxy=(x1, y1, x2, y2),
                    bbox_normalized=norm_box,
                    area_ratio=round(area_ratio, 6),
                    center_x=round(cx, 2),
                    center_y=round(cy, 2),
                )
                raw_detections.append(detection)
                class_counts[norm_type] = class_counts.get(norm_type, 0) + 1

    logger.debug(
        "YOLO accepted detections (%d): %s",
        len(raw_detections),
        [(d.class_name, d.confidence) for d in raw_detections],
    )

    # Optional development-only debug visualization (Phase 11A Section 27)
    if settings.yolo_debug_annotations and raw_detections:
        _save_debug_annotations(image, raw_detections)

    # Spatial aggregation layer
    findings = aggregate_detections(raw_detections, image_width=w, image_height=h)
    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    stem = Path(settings.yolo_dental_model_path).stem
    if "dentaltensor" in stem.lower() or stem in ("", "dentaltensor_nathan_asif_v1"):
        model_version_name = "dentaltensor-vision-v1.0"
    else:
        model_version_name = stem or "dentaltensor-vision-v1.0"

    return YoloDetectionResult(
        model=settings.dentaltensor_model_display_name,
        detections=raw_detections,
        findings=findings,
        inference_ms=elapsed_ms,
        model_version=model_version_name,
        threshold=conf_thresh,
        detection_counts_by_class=class_counts,
    )


def findings_to_visual_findings(
    findings: list[AggregatedFinding],
) -> list[VisualFinding]:
    """Convert aggregated YOLO findings to the public/downstream VisualFinding list.

    If findings is empty (clean scan / no detections above threshold), produces a
    safe healthy_tissue finding with non-definitive wording.
    """
    if not findings:
        return [
            VisualFinding(
                label="healthy_tissue",
                confidence=0.85,
                region="general",
                visibility="clear",
                distribution="none",
                detection_count=0,
            )
        ]

    visual_findings: list[VisualFinding] = []
    for f in findings:
        visual_findings.append(
            VisualFinding(
                label=f.type,
                confidence=f.confidence,
                region=f.distribution,
                visibility="clear",
                distribution=f.distribution,
                detection_count=f.detection_count,
            )
        )
    return visual_findings


def _save_debug_annotations(image: np.ndarray, detections: list[DentalDetection]) -> None:
    """Save annotated image with bounding boxes to tmp/debug/ (development-only)."""
    try:
        import cv2

        debug_dir = Path("tmp/debug")
        debug_dir.mkdir(parents=True, exist_ok=True)
        img_copy = image.copy()

        for d in detections:
            x1, y1, x2, y2 = map(int, d.bbox_xyxy)
            cv2.rectangle(img_copy, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{d.normalized_type} {d.confidence:.2f}"
            cv2.putText(
                img_copy,
                label,
                (x1, max(15, y1 - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
            )

        filename = debug_dir / f"yolo_{int(time.time())}_{uuid4().hex[:6]}.jpg"
        cv2.imwrite(str(filename), img_copy)
        logger.debug("Saved YOLO debug annotation to: %s", filename)
    except Exception as exc:
        logger.warning("Failed to save debug annotation: %s", exc)
