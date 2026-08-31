"""Deterministic vision stub when Gemini is unavailable."""

from dantshaant_common.schemas import VisualFinding


def analyze_with_stub(jpeg_bytes: bytes, locale: str) -> list[VisualFinding]:
    _ = jpeg_bytes, locale
    return [
        VisualFinding(label="healthy_tissue", confidence=0.88, region="general"),
        VisualFinding(label="plaque_detected", confidence=0.35, region="lower_anterior"),
    ]
