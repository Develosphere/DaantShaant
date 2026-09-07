"""Central Dentist system prompt and grounded context builder.

Implements the professional, natural, and concise clinical persona of the
DaantShaant Central Dentist.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from orchestrator.central_dentist.fast_path import format_date_natural
from orchestrator.central_dentist.retrieval import (
    AppointmentSummary,
    ScanSummary,
)

CENTRAL_DENTIST_SYSTEM_PROMPT = """You are DaantShaant, the central oral-health assistant for the DaantShaant platform.
You communicate as the central dental intelligence inside DaantShaant, helping patients understand screening findings, reports, urgency levels, appointments, and general oral care.

Essential rules:
1. Answer directly in the very first sentence with calm, professional clarity. Never begin with conversational filler or preamble.
2. Ground all patient-specific statements strictly in the provided patient records. Distinguish AI visual screening from clinical diagnoses (e.g. "flagged possible cavity" rather than "you have a cavity"). Never fabricate missing records.
3. Keep answers concise (2 to 4 sentences).
4. Output clean plain text without asterisks (**), markdown headers (#), bullet points, or robotic AI phrases ("As an AI...", "Based on the provided information...").
"""

BANNED_SLOP_PATTERNS = [
    r"as an ai (language model|assistant|system)",
    r"based on the (information|data|context) provided",
    r"it is important to (note|remember|keep in mind) that",
    r"i understand your concern",
    r"please note that",
    r"according to the provided",
    r"how may i assist you today",
    r"what can i help you with today",
    r"feel free to ask",
    r"don't hesitate to reach out",
]


def clean_response(text: str) -> str:
    """Post-process response to remove markdown markers, banned slop phrases, and trailing cutoffs."""
    if not text:
        return ""

    cleaned = text.strip()

    # Strip markdown formatting
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"^#+\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*[-*•]\s+", "", cleaned, flags=re.MULTILINE)

    # Remove banned generic slop patterns
    for pattern in BANNED_SLOP_PATTERNS:
        cleaned = re.sub(pattern + r"[,.:;]?", "", cleaned, flags=re.IGNORECASE)

    # Collapse repeated whitespace and double spaces
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    # Fix initial punctuation if leading phrase was stripped
    cleaned = re.sub(r"^[,\s.:;]+", "", cleaned)
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]

    return cleaned


def build_grounded_context(
    latest_scan: Optional[ScanSummary] = None,
    previous_scan: Optional[ScanSummary] = None,
    scan_history: Optional[list[ScanSummary]] = None,
    appointments: Optional[list[AppointmentSummary]] = None,
    dentist_info: Optional[dict[str, Any]] = None,
    knowledge_snippet: Optional[str] = None,
    recent_turns: Optional[list[dict[str, str]]] = None,
) -> str:
    """Build a compact, structured text prompt for Qwen, omitting empty sections."""
    parts = []

    # 1. Patient clinical context (only if present)
    has_patient_data = bool(latest_scan or previous_scan or appointments or dentist_info)
    if has_patient_data:
        parts.append("=== PATIENT RECORD ===")

        if latest_scan:
            date_str = format_date_natural(latest_scan.created_at)
            confidence_str = (
                f"{int(round(latest_scan.confidence * 100))}%"
                if latest_scan.confidence is not None
                else "Not recorded"
            )
            verdict_str = (latest_scan.verdict or "Completed").replace("_", " ")
            parts.append(f"Latest Scan ({date_str}): {verdict_str} [Urgency: {latest_scan.urgency_level or 'Routine'}, Confidence: {confidence_str}]")
            if latest_scan.recommended_specialist:
                parts.append(f"Recommended Specialist: {latest_scan.recommended_specialist}")
            if latest_scan.summary:
                parts.append(f"Report Summary: {latest_scan.summary}")

            if latest_scan.findings:
                findings_summary = ", ".join(
                    f"{f.observation} ({int(round(f.confidence * 100))}%)"
                    for f in latest_scan.findings
                )
                parts.append(f"Visible Findings: {findings_summary}")

        if previous_scan:
            prev_date = format_date_natural(previous_scan.created_at)
            prev_conf = (
                f"{int(round(previous_scan.confidence * 100))}%"
                if previous_scan.confidence is not None
                else "Not recorded"
            )
            parts.append(f"Previous Scan ({prev_date}): {previous_scan.verdict or 'Completed'} [Urgency: {previous_scan.urgency_level or 'Routine'}, Confidence: {prev_conf}]")
            if previous_scan.findings:
                prev_findings = ", ".join(
                    f"{f.observation} ({int(round(f.confidence * 100))}%)"
                    for f in previous_scan.findings
                )
                parts.append(f"Previous Findings: {prev_findings}")

        if scan_history and len(scan_history) > 1:
            parts.append(f"Total Completed Scans Recorded: {len(scan_history)}")

        if appointments:
            next_appt = appointments[0]
            appt_time = f" for {next_appt.preferred_time}" if next_appt.preferred_time else ""
            clinic_info = f" at {next_appt.clinic_name}" if next_appt.clinic_name else ""
            parts.append(f"Appointment: {next_appt.dentist_name}{clinic_info}{appt_time} (Status: {next_appt.status})")

        if dentist_info:
            parts.append(f"Selected Platform Dentist: {dentist_info.get('name')}")
            if dentist_info.get("clinic_name"):
                parts.append(f"Clinic: {dentist_info.get('clinic_name')}")

    # 2. Curated oral health knowledge
    if knowledge_snippet:
        parts.append(f"\n=== REFERENCE GUIDELINE ===\n{knowledge_snippet.strip()}")

    # 3. Recent conversation turns (last 4 turns for low latency)
    if recent_turns:
        parts.append("\n=== RECENT TURNS ===")
        for turn in recent_turns[-4:]:
            role = turn.get("role", "user").capitalize()
            content = turn.get("content", "").strip()
            if content:
                parts.append(f"{role}: {content}")

    return "\n".join(parts)
