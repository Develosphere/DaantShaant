"""Phase 11A — Specialized YOLO Dental Pathology Perception Pipeline Tests.

Validates all 16 required test conditions with mocked model and gateway components:
1. calculus -> tartar
2. caries -> cavity_suspect
3. gingivitis -> gingivitis_signs
4. tooth discoloration -> discoloration
5. ulcer -> oral_ulcer
6. low confidence detection filtered (< 0.50)
7. multiple boxes aggregate
8. generalized discoloration heuristic
9. discoloration never maps to calculus
10. calculus + discoloration preserved separately
11. detector no-findings safe result
12. detector failure does not claim healthy
13. Qwen report receives structured evidence, not image
14. Qwen cannot change triage in returned schema (guardrails)
15. oral ulcer triage safety (cautious, no cancer/systemic claims)
16. existing report contract preserved

NO real best.pt required. ZERO network/browser calls.
"""

from __future__ import annotations

import base64
import io
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from PIL import Image

from dantshaant_common.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ConditionLabel,
    DiagnoseRequest,
    DiagnoseResponse,
    UrgencyLevel,
    VisualFinding,
)
from diagnosis.classifier import diagnose
from diagnosis.triage import (
    DISCOLORATION_LIMITATION,
    HEALTHY_VERDICT,
    RULES,
    triage,
    triage_findings,
)
from teeth_analyzer.config import settings
from teeth_analyzer.inference import VisionBackendError, analyze_image
from teeth_analyzer.yolo_detector import (
    DentalDetection,
    YoloDetectorError,
    YoloInferenceError,
    YoloModelNotFoundError,
    aggregate_detections,
    findings_to_visual_findings,
    normalize_yolo_class,
    run_yolo_detection,
)
from orchestrator.clinical.report_generator import (
    build_deterministic_report_text,
    generate_clinical_report_text,
)


def _make_dummy_image_b64(width: int = 640, height: int = 480) -> str:
    """Create a non-blank image that passes mechanical quality."""
    img = Image.new("RGB", (width, height), color=(200, 180, 160))
    # Add high-contrast gradient/lines so variance of laplacian passes quality gate
    arr = np.array(img)
    arr[100:300, 100:500] = [255, 255, 255]
    arr[150:250, 150:450] = [50, 50, 50]
    out_img = Image.fromarray(arr)
    buf = io.BytesIO()
    out_img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


class MockYoloBoxes:
    def __init__(self, xyxy, conf, cls):
        self._xyxy = np.array(xyxy, dtype=np.float32)
        self._conf = np.array(conf, dtype=np.float32)
        self._cls = np.array(cls, dtype=np.int32)

    @property
    def xyxy(self):
        m = MagicMock()
        m.cpu().numpy.return_value = self._xyxy
        return m

    @property
    def conf(self):
        m = MagicMock()
        m.cpu().numpy.return_value = self._conf
        return m

    @property
    def cls(self):
        m = MagicMock()
        m.cpu().numpy.return_value = self._cls
        return m

    def __len__(self):
        return len(self._cls)


class MockYoloResult:
    def __init__(self, boxes, names):
        self.boxes = boxes
        self.names = names


# ---------------------------------------------------------------------------
# Test Cases 1-5: LOCKED Class Mapping
# ---------------------------------------------------------------------------

def test_1_calculus_maps_to_tartar():
    assert normalize_yolo_class("calculus") == "tartar"
    detections = [
        DentalDetection(
            class_name="calculus",
            normalized_type="tartar",
            confidence=0.85,
            bbox_xyxy=(100, 100, 200, 200),
        )
    ]
    findings = aggregate_detections(detections, 640, 480)
    assert len(findings) == 1
    assert findings[0].type == "tartar"


def test_2_caries_maps_to_cavity_suspect():
    assert normalize_yolo_class("caries") == "cavity_suspect"
    detections = [
        DentalDetection(
            class_name="caries",
            normalized_type="cavity_suspect",
            confidence=0.88,
            bbox_xyxy=(150, 150, 250, 250),
        )
    ]
    findings = aggregate_detections(detections, 640, 480)
    assert len(findings) == 1
    assert findings[0].type == "cavity_suspect"


def test_3_gingivitis_maps_to_gingivitis_signs():
    assert normalize_yolo_class("gingivitis") == "gingivitis_signs"
    detections = [
        DentalDetection(
            class_name="gingivitis",
            normalized_type="gingivitis_signs",
            confidence=0.79,
            bbox_xyxy=(100, 200, 300, 300),
        )
    ]
    findings = aggregate_detections(detections, 640, 480)
    assert len(findings) == 1
    assert findings[0].type == "gingivitis_signs"


def test_4_tooth_discoloration_maps_to_discoloration():
    assert normalize_yolo_class("tooth discoloration") == "discoloration"
    detections = [
        DentalDetection(
            class_name="tooth discoloration",
            normalized_type="discoloration",
            confidence=0.91,
            bbox_xyxy=(100, 100, 200, 200),
        )
    ]
    findings = aggregate_detections(detections, 640, 480)
    assert len(findings) == 1
    assert findings[0].type == "discoloration"


def test_5_ulcer_maps_to_oral_ulcer():
    assert normalize_yolo_class("ulcer") == "oral_ulcer"
    detections = [
        DentalDetection(
            class_name="ulcer",
            normalized_type="oral_ulcer",
            confidence=0.84,
            bbox_xyxy=(50, 50, 120, 120),
        )
    ]
    findings = aggregate_detections(detections, 640, 480)
    assert len(findings) == 1
    assert findings[0].type == "oral_ulcer"


# ---------------------------------------------------------------------------
# Test Case 6: Confidence Filtering
# ---------------------------------------------------------------------------

def test_6_low_confidence_detection_filtered():
    # Model returns one detection at 0.42 (below 0.50 threshold)
    names = {0: "calculus", 1: "caries"}
    boxes = MockYoloBoxes(
        xyxy=[[100, 100, 200, 200]],
        conf=[0.42],
        cls=[0],
    )
    mock_model = MagicMock()
    mock_model.predict.return_value = [MockYoloResult(boxes, names)]

    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    res = run_yolo_detection(dummy_img, model=mock_model, threshold=0.50)

    assert len(res.detections) == 0
    assert len(res.findings) == 0


# ---------------------------------------------------------------------------
# Test Case 7: Multiple Boxes Aggregate
# ---------------------------------------------------------------------------

def test_7_multiple_boxes_aggregate():
    detections = [
        DentalDetection(
            class_name="caries",
            normalized_type="cavity_suspect",
            confidence=0.80,
            bbox_xyxy=(100, 100, 150, 150),
        ),
        DentalDetection(
            class_name="caries",
            normalized_type="cavity_suspect",
            confidence=0.89,
            bbox_xyxy=(160, 100, 200, 150),
        ),
    ]
    findings = aggregate_detections(detections, 640, 480)
    assert len(findings) == 1
    assert findings[0].type == "cavity_suspect"
    assert findings[0].detection_count == 2
    assert findings[0].confidence == 0.89
    assert findings[0].distribution == "multiple"


# ---------------------------------------------------------------------------
# Test Case 8: Generalized Discoloration Heuristic
# ---------------------------------------------------------------------------

def test_8_generalized_discoloration_heuristic():
    # Discoloration detections spread across left, center, right of dentition
    detections = [
        DentalDetection(
            class_name="tooth discoloration",
            normalized_type="discoloration",
            confidence=0.85,
            bbox_xyxy=(50, 100, 150, 200),  # left
        ),
        DentalDetection(
            class_name="tooth discoloration",
            normalized_type="discoloration",
            confidence=0.92,
            bbox_xyxy=(250, 100, 350, 200),  # center
        ),
        DentalDetection(
            class_name="tooth discoloration",
            normalized_type="discoloration",
            confidence=0.88,
            bbox_xyxy=(450, 100, 580, 200),  # right
        ),
    ]
    findings = aggregate_detections(detections, 640, 480)
    assert len(findings) == 1
    assert findings[0].type == "discoloration"
    assert findings[0].distribution == "generalized"
    assert findings[0].detection_count == 3


# ---------------------------------------------------------------------------
# Test Case 9: Discoloration Never Maps to Calculus
# ---------------------------------------------------------------------------

def test_9_discoloration_never_maps_to_calculus():
    assert normalize_yolo_class("tooth discoloration") != "tartar"
    assert normalize_yolo_class("tooth discoloration") != "calculus"

    detections = [
        DentalDetection(
            class_name="tooth discoloration",
            normalized_type="discoloration",
            confidence=0.95,
            bbox_xyxy=(100, 100, 500, 300),
        )
    ]
    findings = aggregate_detections(detections, 640, 480)
    assert all(f.type != "tartar" for f in findings)
    assert findings[0].type == "discoloration"


# ---------------------------------------------------------------------------
# Test Case 10: Calculus + Discoloration Preserved Separately
# ---------------------------------------------------------------------------

def test_10_calculus_and_discoloration_preserved_separately():
    detections = [
        DentalDetection(
            class_name="calculus",
            normalized_type="tartar",
            confidence=0.82,
            bbox_xyxy=(100, 200, 180, 250),
        ),
        DentalDetection(
            class_name="tooth discoloration",
            normalized_type="discoloration",
            confidence=0.90,
            bbox_xyxy=(200, 100, 500, 300),
        ),
    ]
    findings = aggregate_detections(detections, 640, 480)
    types = {f.type for f in findings}
    assert "tartar" in types
    assert "discoloration" in types
    assert len(findings) == 2


# ---------------------------------------------------------------------------
# Test Case 11: Detector No-Findings Safe Result
# ---------------------------------------------------------------------------

def test_11_detector_no_findings_safe_result():
    # Empty findings list maps to safe healthy_tissue visual finding
    visual_findings = findings_to_visual_findings([])
    assert len(visual_findings) == 1
    assert visual_findings[0].label == "healthy_tissue"
    assert visual_findings[0].distribution == "none"

    # Triage returns non-definitive healthy verdict
    t_res = triage_findings(visual_findings, overall_quality_score=0.9)
    assert t_res.urgency_level == UrgencyLevel.ROUTINE
    assert "no obvious concerning visual finding" in t_res.verdict.lower()


# ---------------------------------------------------------------------------
# Test Case 12: Detector Failure Does Not Claim Healthy
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_12_detector_failure_does_not_claim_healthy():
    img_b64 = _make_dummy_image_b64()
    req = AnalyzeRequest(user_id=uuid4(), image_base64=img_b64)

    with patch("teeth_analyzer.inference.run_yolo_detection", side_effect=YoloInferenceError("YOLO crashed")):
        with patch.object(settings, "vision_provider", "yolo"):
            with patch.object(settings, "yolo_allow_qwen_technical_fallback", False):
                with pytest.raises(VisionBackendError) as exc_info:
                    await analyze_image(req)
                assert "YOLO dental perception failed" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test Case 13: Qwen Report Receives Structured Evidence, Not Image
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_13_qwen_report_receives_structured_evidence_not_image():
    mock_gateway = MagicMock()
    mock_gateway.generate_text = AsyncMock()
    mock_gateway.generate_text.return_value = MagicMock(
        content='{"summary": "Observed localized tartar.", "finding_explanations": ["Tartar detected."], "recommended_steps": ["Cleaning."], "professional_notes": "Notes."}'
    )

    findings = [{"label": "tartar", "confidence": 0.85, "region": "localized"}]
    triage_dict = {
        "condition_summary": "Possible calculus / tartar buildup",
        "urgency_level": "soon",
        "recommended_actions": ["Arrange professional cleaning"],
        "recommended_specialist": "general dentist",
    }

    report = await generate_clinical_report_text(
        findings=findings,
        triage=triage_dict,
        gateway=mock_gateway,
    )

    assert mock_gateway.generate_text.called
    call_args = mock_gateway.generate_text.call_args[0][0]
    prompt_str = call_args.prompt

    # Prompt MUST contain structured JSON evidence
    assert "Possible calculus / tartar buildup" in prompt_str
    assert "tartar" in prompt_str
    # Prompt MUST NOT contain raw image bytes or data URL
    assert "data:image" not in prompt_str
    assert "base64" not in prompt_str


# ---------------------------------------------------------------------------
# Test Case 14: Qwen Hard Guardrails / Fallback on Violation
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_14_qwen_cannot_change_triage_guardrails_enforced():
    # If Qwen hallucinates forbidden diagnostic labels (cancer/fluorosis), guardrails trigger fallback
    mock_gateway = MagicMock()
    mock_gateway.generate_text = AsyncMock()
    mock_gateway.generate_text.return_value = MagicMock(
        content='{"summary": "You have oral cancer and fluorosis.", "finding_explanations": ["Fluorosis detected."], "recommended_steps": ["Chemo."], "professional_notes": "Cancer."}'
    )

    findings = [{"label": "discoloration", "confidence": 0.90, "region": "generalized"}]
    triage_dict = {
        "condition_summary": "Visible tooth discoloration",
        "urgency_level": "routine",
        "recommended_actions": ["Maintain oral hygiene"],
        "recommended_specialist": "general dentist",
    }

    report = await generate_clinical_report_text(
        findings=findings,
        triage=triage_dict,
        gateway=mock_gateway,
    )

    # Hallucinated output rejected, fell back to safe deterministic text
    assert report.source == "deterministic"
    assert "cancer" not in report.summary.lower()
    assert "fluorosis" not in report.summary.lower()
    assert "discoloration" in report.summary.lower()


# ---------------------------------------------------------------------------
# Test Case 15: Oral Ulcer Triage Safety
# ---------------------------------------------------------------------------

def test_15_oral_ulcer_triage_safety():
    finding = VisualFinding(label="oral_ulcer", confidence=0.88, region="localized")
    decision = triage([finding], overall_quality_score=0.95)

    assert decision.result.urgency_level == UrgencyLevel.SOON
    assert decision.condition_label == ConditionLabel.ORAL_ULCER
    assert "visible oral ulcer" in decision.result.condition_summary.lower()

    # Ensure cautious safety phrasing, no cancer or systemic disease claims
    full_text = " ".join(decision.result.possible_concerns + decision.result.recommended_actions).lower()
    assert "cancer" not in full_text
    assert "malignan" not in full_text
    assert "systemic" not in full_text
    assert "persist" in full_text or "10-14 days" in full_text


# ---------------------------------------------------------------------------
# Test Case 16: Existing Report Contract Preserved
# ---------------------------------------------------------------------------

def test_16_existing_report_contract_preserved():
    findings = [
        VisualFinding(label="tartar", confidence=0.85, region="localized", distribution="localized", detection_count=1)
    ]
    diag_req = DiagnoseRequest(
        user_id=uuid4(),
        analysis_id=uuid4(),
        findings=findings,
        overall_quality_score=0.90,
    )
    diag_resp: DiagnoseResponse = diagnose(diag_req)

    # Legacy contract fields preserved
    assert isinstance(diag_resp.condition_label, ConditionLabel)
    assert diag_resp.condition_label == ConditionLabel.PLAQUE_TARTAR
    assert diag_resp.confidence == 0.85
    assert diag_resp.meets_threshold is True
    assert diag_resp.triage is not None
    assert diag_resp.triage.urgency_level == UrgencyLevel.SOON
    assert len(diag_resp.triage.possible_concerns) > 0
    assert len(diag_resp.triage.recommended_actions) > 0


# ---------------------------------------------------------------------------
# Test Case 17: Exact Caries Detection Pipeline Regression
# ---------------------------------------------------------------------------

def test_17_caries_detection_pipeline_regression():
    """Verify that mocked raw detections:
      caries 0.655
      caries 0.558
      caries 0.524
    With threshold: caries = 0.55
    Yields:
      Expected accepted detections: 0.655 and 0.558 (0.524 dropped)
      Expected normalized evidence: cavity_suspect present
      Expected triage/report state: NOT healthy/no-finding
    """
    mock_model = MagicMock()
    mock_boxes = MockYoloBoxes(
        xyxy=[
            [100, 100, 150, 150],
            [200, 200, 250, 250],
            [300, 300, 350, 350],
        ],
        conf=[0.655, 0.558, 0.524],
        cls=[1, 1, 1],
    )
    names = {0: "calculus", 1: "caries", 2: "gingivitis", 3: "tooth discoloration", 4: "ulcer"}
    mock_res = MockYoloResult(boxes=mock_boxes, names=names)
    mock_model.predict.return_value = [mock_res]

    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)

    from teeth_analyzer.config import Settings
    s = Settings(
        _env_file=None,
        yolo_dental_confidence_threshold=0.50,
        yolo_caries_confidence_threshold=0.55,
    )
    with patch("teeth_analyzer.yolo_detector.settings", s):
        result = run_yolo_detection(dummy_img, model=mock_model)

    # Expected accepted detections: exactly 2 survive (0.655 and 0.558)
    assert len(result.detections) == 2
    accepted_confs = [d.confidence for d in result.detections]
    assert accepted_confs == [0.655, 0.558]
    for d in result.detections:
        assert d.class_name == "caries"
        assert d.normalized_type == "cavity_suspect"

    # Expected normalized evidence: cavity_suspect present
    findings = findings_to_visual_findings(result.findings)
    assert len(findings) == 1
    assert findings[0].label == "cavity_suspect"
    assert findings[0].confidence == 0.655
    assert findings[0].detection_count == 2

    # Expected triage/report state: NOT healthy/no-finding
    diag_req = DiagnoseRequest(
        user_id=uuid4(),
        analysis_id=uuid4(),
        findings=findings,
        overall_quality_score=0.90,
    )
    diag_resp = diagnose(diag_req)
    assert diag_resp.condition_label != ConditionLabel.HEALTHY
    assert diag_resp.condition_label == ConditionLabel.EARLY_CAVITY
    assert diag_resp.triage is not None
    assert diag_resp.triage.urgency_level == UrgencyLevel.SOON
    assert "healthy" not in diag_resp.triage.condition_summary.lower()
    assert "no obvious concerning" not in diag_resp.triage.condition_summary.lower()
    assert "early tooth decay" in diag_resp.triage.condition_summary.lower()


# ---------------------------------------------------------------------------
# Test Case 18: Preprocessing Preserves Natural Pixels Without CLAHE Distortion
# ---------------------------------------------------------------------------

def test_18_preprocessing_preserves_natural_pixels_without_clahe():
    """Verify normalize_image does not distort intraoral pixels with CLAHE."""
    from teeth_analyzer.preprocess import normalize_image

    # An intraoral pixel block within max_edge_px
    test_img = np.array([
        [[100, 120, 140], [105, 125, 145]],
        [[110, 130, 150], [115, 135, 155]],
    ], dtype=np.uint8)

    norm = normalize_image(test_img)
    # Must preserve exact pixel values when no downsampling is needed
    np.testing.assert_array_equal(test_img, norm)

