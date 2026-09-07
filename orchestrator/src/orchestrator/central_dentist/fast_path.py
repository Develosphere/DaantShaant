"""Deterministic fast-path answer generator for DaantShaant Central Dentist.

Bypasses LLM generation for simple factual queries such as:
- Date of latest scan
- Confidence score of latest scan
- Urgency level of latest report
- Scheduled appointment date/status
- Standard greetings

Produces natural, professional responses in < 5 milliseconds.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from orchestrator.central_dentist.retrieval import AppointmentSummary, ScanSummary


def format_date_natural(dt: datetime) -> str:
    """Format datetime naturally, e.g. 'September 6, 2026'."""
    try:
        return dt.strftime("%B %d, %Y")
    except Exception:
        return str(dt)[:10]


def format_fast_path_response(
    fast_path_type: str,
    latest_scan: Optional[ScanSummary] = None,
    appointments: Optional[list[AppointmentSummary]] = None,
    user_name: Optional[str] = None,
) -> Optional[str]:
    """Return deterministic answer for structured factual questions."""
    appointments = appointments or []

    # 1. SCAN DATE
    if fast_path_type == "scan_date":
        if not latest_scan:
            return "I don't see any completed oral scans in your record yet."
        date_str = format_date_natural(latest_scan.created_at)
        verdict = latest_scan.verdict or "oral screening"
        return f"Your latest scan was recorded on {date_str}. The screening flagged {verdict}."

    # 2. CONFIDENCE
    if fast_path_type == "confidence":
        if not latest_scan:
            return "You don't have any screening scans in your record yet to review confidence."
        if latest_scan.confidence is not None:
            pct = int(round(latest_scan.confidence * 100)) if latest_scan.confidence <= 1.0 else int(round(latest_scan.confidence))
            verdict = latest_scan.verdict or "findings"
            return f"Your latest screening flagged {verdict} at {pct}% visual confidence."
        return "Your latest scan report does not have a recorded confidence score."

    # 3. URGENCY
    if fast_path_type == "urgency":
        if not latest_scan:
            return "I don't see any screening reports in your record yet to determine urgency."
        urgency = latest_scan.urgency_level or "Routine"
        timeframe = (
            "a routine dental checkup"
            if urgency.lower() == "routine"
            else "scheduling a consultation soon"
        )
        return f"Your latest screening report was marked as {urgency.capitalize()} urgency, recommending {timeframe}."

    # 4. APPOINTMENT DATE / STATUS
    if fast_path_type == "appointment_date":
        if not appointments:
            return "You don't have any appointments scheduled or requested right now."
        appt = appointments[0]
        dentist_name = appt.dentist_name
        time_pref = f" for {appt.preferred_time}" if appt.preferred_time else ""
        clinic_info = f" at {appt.clinic_name}" if appt.clinic_name else ""
        return (
            f"You have an appointment requested with {dentist_name}{clinic_info}"
            f"{time_pref}. Its current status is {appt.status}."
        )

    # 5. GREETING
    if fast_path_type == "greeting":
        greeting_target = f", {user_name}" if user_name else ""
        return f"Hello{greeting_target}! I'm DaantShaant. How can I help with your oral health, scan results, or appointments today?"

    # 6. BRUSHING ESSENTIALS FAST PATH
    if fast_path_type == "brushing_guide":
        return (
            "Brush twice a day for about two minutes with fluoride toothpaste. "
            "Use a soft-bristled brush and angle it gently toward the gumline. "
            "Clean every surface of each tooth and avoid aggressive scrubbing."
        )

    # 7. FLOSSING ESSENTIALS FAST PATH
    if fast_path_type == "flossing_guide":
        return (
            "Floss once daily, ideally before bed, to clear plaque between teeth where brush bristles cannot reach. "
            "Curve the floss in a gentle C-shape against the side of each tooth and slide carefully beneath the gumline."
        )

    return None
