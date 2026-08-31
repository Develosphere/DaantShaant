"""Gemini Flash vision — dental visual findings as structured JSON."""

from __future__ import annotations

import json
import logging
import re

from dantshaant_common.schemas import VisualFinding

from teeth_analyzer.config import settings

logger = logging.getLogger(__name__)

VISION_PROMPT = """You are a dental vision assistant analyzing a photo of teeth or the mouth.
Inspect carefully for: cavities/decay, plaque, tartar, gum inflammation, discoloration,
missing or damaged teeth, cracks, and overall oral health.

Return ONLY valid JSON (no markdown fences) in this exact shape:
{
  "findings": [
    {"label": "<snake_case_label>", "confidence": 0.0-1.0, "region": "<optional area>"}
  ]
}

Allowed labels (use the most specific match):
- healthy_tissue — only if teeth and gums look clearly healthy
- plaque_detected
- tartar
- cavity_suspect — early decay, dark spots, holes starting
- cavity_advanced — obvious large cavities or severe decay
- gingivitis_signs — red/swollen/bleeding gums
- gum_disease_severe
- discoloration — yellow/brown/stained teeth
- missing_or_damaged_teeth — broken, chipped, or missing teeth

Rules:
- List ALL visible issues, not only the dominant one.
- Do NOT label healthy_tissue with high confidence if decay, heavy plaque, or gum disease is visible.
- If the image is not a clear teeth/mouth photo, return one finding: unknown with low confidence.
- Be clinically conservative: flag suspected problems rather than calling severe cases healthy.
Locale hint: __LOCALE__.
"""


def _build_prompt(locale: str) -> str:
    return VISION_PROMPT.replace("__LOCALE__", locale)


def _extract_response_text(response) -> str:
    if getattr(response, "text", None):
        return response.text
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        feedback = getattr(response, "prompt_feedback", None)
        raise RuntimeError(f"Gemini returned no candidates. feedback={feedback}")
    parts = candidates[0].content.parts
    texts = [p.text for p in parts if getattr(p, "text", None)]
    if not texts:
        finish = getattr(candidates[0], "finish_reason", "unknown")
        raise RuntimeError(f"Gemini response has no text (finish_reason={finish})")
    return "".join(texts)


def _parse_findings(text: str) -> list[VisualFinding]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    data = json.loads(text)
    raw = data.get("findings", data if isinstance(data, list) else [])
    findings: list[VisualFinding] = []
    for item in raw:
        findings.append(
            VisualFinding(
                label=str(item.get("label", "unknown")).lower().replace(" ", "_"),
                confidence=float(item.get("confidence", 0.5)),
                region=item.get("region"),
            )
        )
    return findings or [VisualFinding(label="unknown", confidence=0.3, region="general")]


def analyze_with_gemini(jpeg_bytes: bytes, locale: str) -> list[VisualFinding]:
    if not settings.gemini_api_key:
        raise RuntimeError(
            "TEETH_ANALYZER_GEMINI_API_KEY is not set. Add it to the repo root .env file."
        )

    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)
    prompt = _build_prompt(locale)
    part = {"mime_type": "image/jpeg", "data": jpeg_bytes}

    try:
        response = model.generate_content(
            [prompt, part],
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 1024,
                "response_mime_type": "application/json",
            },
        )
    except TypeError:
        # Older google-generativeai without response_mime_type
        response = model.generate_content(
            [prompt, part],
            generation_config={"temperature": 0.1, "max_output_tokens": 1024},
        )

    text = _extract_response_text(response)
    findings = _parse_findings(text)
    logger.info("Gemini findings: %s", [f.model_dump() for f in findings])
    return findings
