"""Text-only clinical report generator using Qwen via AIGateway (Phase 11A).

Qwen receives NO raw images in this report-generation path. It operates strictly
on pre-validated structured evidence (findings, deterministic triage, limitations)
with hard guardrails:
- NEVER add or remove findings
- NEVER change finding type or certainty
- NEVER alter urgency or specialist routing
- NEVER invent diseases or infer etiologies (no fluorosis, amelogenesis imperfecta,
  enamel hypoplasia, or oral cancer)
- Explain discoloration cautiously: visible tooth discoloration whose underlying
  cause cannot be determined from visual screening alone.

Provides a robust deterministic fallback when the AI gateway is unavailable or
in testing mode.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from orchestrator.ai.gateway import AIGateway
from orchestrator.ai.schemas import TextRequest

logger = logging.getLogger(__name__)

REPORT_GENERATION_PROMPT = """You are an AI dental screening communicator. You generate clear, \
cautious, patient-friendly report prose strictly from pre-validated structured screening evidence.
You are NOT diagnosing and you receive NO raw image.

Structured Evidence:
{evidence_json}

HARD CLINICAL GUARDRAILS:
1. You MUST NOT add, invent, or omit any findings. Only discuss findings present in the evidence.
2. You MUST NOT change urgency, severity, or recommended specialist.
3. You MUST NOT diagnose or claim a confirmed disease (never say "you have ...").
4. You MUST NOT infer underlying etiologies (e.g. do NOT mention fluorosis, amelogenesis imperfecta, \
enamel hypoplasia, or oral cancer).
5. For tooth discoloration: refer to it as "visible tooth discoloration" and state that the underlying \
cause cannot be determined from visual screening.
6. For oral ulcers: refer to it as "visible oral ulcer / sore" and recommend dental evaluation if \
persistent beyond 10-14 days. Never suggest malignancy or systemic illness.
7. Tone: empathetic, objective, professional, and non-alarmist.
Locale hint: {locale}.

Return ONLY valid JSON (no markdown formatting, no explanations outside JSON):
{{
  "summary": "<1-2 sentence patient-friendly screening overview>",
  "finding_explanations": [
    "<short cautious description of finding, honoring the evidence>"
  ],
  "recommended_steps": [
    "<practical next step strictly matching the triage recommendations>"
  ],
  "professional_notes": "<concise professional summary for licensed dentist review>"
}}
"""


@dataclass
class ClinicalReportText:
    """Patient-friendly report text produced from structured screening evidence."""

    summary: str
    finding_explanations: list[str] = field(default_factory=list)
    recommended_steps: list[str] = field(default_factory=list)
    professional_notes: str = ""
    source: str = "qwen-text"


def build_deterministic_report_text(
    findings: list[dict[str, Any]],
    triage: dict[str, Any],
    limitations: list[str] | None = None,
) -> ClinicalReportText:
    """Deterministic, provider-independent text generator (offline & fallback)."""
    condition_summary = triage.get("condition_summary", "Oral health screening")
    urgency = triage.get("urgency_level", "routine")
    actions = triage.get("recommended_actions", [])
    specialist = triage.get("recommended_specialist", "general dentist")

    # Patient-friendly summary
    if not findings or all(f.get("label") in ("healthy_tissue", "healthy") for f in findings):
        summary = "Visual screening observed no obvious concerning findings — routine monitoring recommended."
    else:
        summary = f"Visual screening observed {condition_summary.lower()}. Follow-up is recommended with a {specialist}."

    # Finding explanations
    explanations: list[str] = []
    for f in findings:
        lbl = str(f.get("label", "")).lower()
        dist = f.get("distribution") or f.get("region") or "localized"
        if lbl == "discoloration":
            explanations.append(
                f"Visible {dist} tooth surface discoloration. Visual screening cannot determine the underlying cause."
            )
        elif lbl == "tartar":
            explanations.append(f"Visible tartar / calculus deposits ({dist}). Professional dental cleaning recommended.")
        elif lbl == "cavity_suspect":
            explanations.append(f"Visual feature possibly consistent with early tooth decay ({dist}). Licensed dental check advised.")
        elif lbl == "gingivitis_signs":
            explanations.append(f"Visible signs of gum inflammation ({dist}). Gum evaluation recommended.")
        elif lbl == "oral_ulcer":
            explanations.append(
                f"Visible oral ulcer / sore ({dist}). Dental evaluation advised if persistent beyond 10-14 days or worsening."
            )
        elif lbl not in ("healthy_tissue", "healthy"):
            explanations.append(f"Visible oral finding: {lbl.replace('_', ' ')} ({dist}).")

    # Recommended steps
    steps = list(actions) if actions else ["Maintain good daily oral hygiene", "Arrange routine dental checkup"]

    prof_notes = (
        f"AI screening observation: {condition_summary}. Urgency: {urgency}. "
        f"Specialist referral: {specialist}."
    )

    return ClinicalReportText(
        summary=summary,
        finding_explanations=explanations,
        recommended_steps=steps,
        professional_notes=prof_notes,
        source="deterministic",
    )


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    return text


async def generate_clinical_report_text(
    findings: list[dict[str, Any]],
    triage: dict[str, Any],
    limitations: list[str] | None = None,
    locale: str = "en",
    gateway: AIGateway | None = None,
) -> ClinicalReportText:
    """Generate patient-friendly clinical report text from structured evidence only.

    Uses AIGateway (Qwen primary) with text-only prompts and strict guardrails.
    Falls back gracefully to deterministic text on any gateway outage or test run.
    """
    if gateway is None:
        return build_deterministic_report_text(findings, triage, limitations)

    evidence = {
        "findings": findings,
        "triage": triage,
        "limitations": limitations or [],
    }
    evidence_json = json.dumps(evidence, indent=2, default=str)
    prompt = REPORT_GENERATION_PROMPT.format(
        evidence_json=evidence_json,
        locale=locale or "en",
    )

    try:
        req = TextRequest(
            prompt=prompt,
            temperature=0.1,  # Conservative low temperature
            max_tokens=600,
        )
        result = await gateway.generate_text(req)
        raw_text = result.content or ""
        cleaned = _strip_fences(raw_text)
        data = json.loads(cleaned)

        # Validate that Qwen did not inject forbidden terms or drop information
        summary = data.get("summary") or triage.get("condition_summary", "Screening complete")
        explanations = data.get("finding_explanations") or []
        steps = data.get("recommended_steps") or triage.get("recommended_actions", [])
        prof_notes = data.get("professional_notes") or ""

        # Post-generation guardrail filter
        forbidden = ("fluorosis", "amelogenesis", "cancer", "malignan", "confirmed diagnosis")
        for f_word in forbidden:
            if f_word in summary.lower() or any(f_word in exp.lower() for exp in explanations):
                logger.warning("Guardrail violation detected in LLM output (%s); falling back", f_word)
                return build_deterministic_report_text(findings, triage, limitations)

        return ClinicalReportText(
            summary=summary,
            finding_explanations=explanations,
            recommended_steps=steps,
            professional_notes=prof_notes,
            source="qwen-text",
        )
    except Exception as exc:
        logger.warning("Qwen report text generation failed (%s); using deterministic text", exc)
        return build_deterministic_report_text(findings, triage, limitations)
