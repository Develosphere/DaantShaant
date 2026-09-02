"""Shared clinical-vision prompt + structured-output normalization (Phase 2C).

Both the Qwen (primary) and Gemini (fallback) backends use this module, so the
prompt wording and the internal result shape are IDENTICAL no matter which
provider responded. Downstream (orchestrator/Diagnosis) never needs to know the
provider, its SDK, or its response envelope.

The model performs VISUAL SCREENING only. It never produces a definitive
diagnosis, never prescribes treatment, and finding codes are observational
("suspected"/"possible"), not confirmed conditions. Findings are normalized to
the existing downstream-compatible ``VisualFinding`` list; ``visibility`` is
passed through (Phase 3B-lite triage uses it only to state screening
limitations), while the remaining screening fields (observation/limitations) are
intentionally not exposed on the public scan API.
"""

from __future__ import annotations

import json
import logging
import re

from dantshaant_common.schemas import VisualFinding

logger = logging.getLogger(__name__)

CLINICAL_VISION_PROMPT = """You are an AI dental SCREENING assistant. Analyze ONLY what is \
visually observable in this photo of teeth / mouth / oral region. Produce AI dental screening \
observations - NOT a definitive diagnosis and NOT treatment advice.

Return ONLY a single valid JSON object (no markdown fences) in this exact shape:
{
  "oral_regions_visible": ["teeth", "gums"],
  "findings": [
    {
      "finding_code": "<snake_case_code>",
      "observation": "<short visual description of what is seen>",
      "region": "<optional area>",
      "tooth_reference": null,
      "confidence": 0.0,
      "visibility": "clear|partial|limited"
    }
  ],
  "overall_observation": "<one-line summary of the visible oral condition>",
  "limitations": ["<anything that limits this screening>"]
}

Allowed finding_code values (use the most specific match; treat every code as a VISUAL \
SCREENING finding / possible concern, never a confirmed disease):
- healthy_tissue - teeth and gums look clearly healthy
- plaque_detected - visible plaque film
- tartar - visible calculus / tartar
- cavity_suspect - a visual feature possibly consistent with early decay (dark spot, small hole)
- cavity_advanced - a visual feature possibly consistent with more extensive decay
- gingivitis_signs - red / swollen / possibly bleeding gums
- gum_disease_severe - visual features possibly consistent with advanced gum disease
- discoloration - yellow / brown / stained teeth
- missing_or_damaged_teeth - broken, chipped, or missing teeth

Rules:
- Describe only visible features. Do NOT infer hidden structures or invisible conditions.
- Do NOT invent tooth numbers / references when they are not clearly identifiable.
- List ALL visible concerns, not only the dominant one.
- Do NOT claim a definitive diagnosis and do NOT prescribe treatment.
- Be clinically conservative: flag suspected concerns rather than calling a questionable image healthy.
- If the image is not a clear teeth / mouth photo, return one finding with finding_code "unknown" and low confidence.
Locale hint: __LOCALE__.
"""


def build_prompt(locale: str) -> str:
    """Inject the locale hint into the shared screening prompt."""
    return CLINICAL_VISION_PROMPT.replace("__LOCALE__", locale or "en")


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    return text


def parse_findings(text: str) -> list[VisualFinding]:
    """Normalize provider JSON into the downstream-compatible finding list.

    Accepts the structured screening shape (``finding_code`` / ``observation`` /
    ``region`` / ``confidence``) and the legacy simple shape (``label``). Any
    unparseable output degrades to a single low-confidence ``unknown`` finding
    rather than raising - a bad model reply is not a provider outage.
    """
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, ValueError):
        logger.warning("Clinical vision returned unparseable JSON; emitting an 'unknown' finding")
        return [VisualFinding(label="unknown", confidence=0.3, region="general")]

    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        raw = data.get("findings", [])
    else:
        raw = []

    findings: list[VisualFinding] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = item.get("finding_code") or item.get("label") or "unknown"
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        findings.append(
            VisualFinding(
                label=str(code).lower().replace(" ", "_"),
                confidence=min(1.0, max(0.0, confidence)),
                region=item.get("region"),
                visibility=(
                    str(item["visibility"]).lower()
                    if isinstance(item.get("visibility"), str)
                    else None
                ),
            )
        )
    return findings or [VisualFinding(label="unknown", confidence=0.3, region="general")]


__all__ = ["CLINICAL_VISION_PROMPT", "build_prompt", "parse_findings"]
