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

CENTRAL_DENTIST_SYSTEM_PROMPT = """You are DaantShaant, a professional oral-health assistant.
Answer the user's current question directly in calm, concise natural sentences (2-3 sentences max). Output clean plain text without markdown headers, asterisks, bullet points, or filler.
Prioritize the current user message over stale conversational context. Do not reinterpret the user's question as an unrelated dental topic.
Supplied patient records are ground truth only when relevant to the question. Never invent patient history.
Distinguish AI visual screening from confirmed clinical diagnoses. For general dental questions, answer directly with accurate dental science and practical guidance."""


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


def get_context_sources(
    latest_scan: Optional[ScanSummary] = None,
    previous_scan: Optional[ScanSummary] = None,
    scan_history: Optional[list[ScanSummary]] = None,
    appointments: Optional[list[AppointmentSummary]] = None,
    dentist_info: Optional[dict[str, Any]] = None,
    knowledge_snippet: Optional[str] = None,
    recent_turns: Optional[list[dict[str, str]]] = None,
) -> list[str]:
    """Return sanitized list of context source identifiers used in prompt."""
    sources: list[str] = []
    if latest_scan:
        sources.append("latest_scan")
    if previous_scan or (scan_history and len(scan_history) > 1):
        sources.append("scan_history")
    if appointments:
        sources.append("appointments")
    if dentist_info:
        sources.append("dentist_info")
    if knowledge_snippet:
        sources.append("knowledge_guideline")
    if recent_turns:
        sources.append("conversation_history")
    return sources


def audit_chat_prompt_size(
    *,
    system_prompt: str,
    grounded_context: str,
    user_message: str,
    recent_turns: Optional[list[dict[str, str]]] = None,
    knowledge_snippet: Optional[str] = None,
    has_patient_context: bool = False,
) -> dict[str, int]:
    """Calculate sanitized character and message metrics for Central Dentist prompts.

    Never echoes or logs raw text, patient records, or sensitive conversation data.
    """
    system_chars = len(system_prompt)
    context_chars = len(grounded_context)
    history_chars = sum(len(t.get("content", "")) for t in (recent_turns or []))
    knowledge_chars = len(knowledge_snippet) if knowledge_snippet else 0
    patient_chars = max(0, context_chars - history_chars - knowledge_chars) if has_patient_context else 0
    conv_chars = len(user_message) + history_chars
    total_chars = system_chars + context_chars + len(user_message)
    messages_count = 1 + len(recent_turns or []) + 1

    return {
        "messages": messages_count,
        "system_chars": system_chars,
        "context_chars": context_chars,
        "history_chars": history_chars,
        "patient_context_chars": patient_chars,
        "knowledge_context_chars": knowledge_chars,
        "conversation_chars": conv_chars,
        "total_chars": total_chars,
    }
