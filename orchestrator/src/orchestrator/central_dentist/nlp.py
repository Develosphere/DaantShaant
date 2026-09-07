"""Lightweight deterministic NLP engine for DaantShaant Central Dentist.

Strictly ZERO model downloads, ZERO Hugging Face dependencies, ZERO PyTorch
runtime cost. Operates purely on regex, string normalization, and rule-based
entity/intent extraction with execution time well below 50ms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class CentralDentistIntent(str, Enum):
    GREETING = "GREETING"
    SCAN_LATEST = "SCAN_LATEST"
    SCAN_HISTORY = "SCAN_HISTORY"
    SCAN_COMPARE = "SCAN_COMPARE"
    EXPLAIN_FINDING = "EXPLAIN_FINDING"
    EXPLAIN_CONFIDENCE = "EXPLAIN_CONFIDENCE"
    APPOINTMENT_STATUS = "APPOINTMENT_STATUS"
    DENTIST_INFORMATION = "DENTIST_INFORMATION"
    REPORT_QUESTION = "REPORT_QUESTION"
    GENERAL_ORAL_HEALTH = "GENERAL_ORAL_HEALTH"
    DENTAL_KNOWLEDGE = "DENTAL_KNOWLEDGE"
    SYMPTOM_QUESTION = "SYMPTOM_QUESTION"
    FOLLOW_UP_REFERENCE = "FOLLOW_UP_REFERENCE"
    UNKNOWN = "UNKNOWN"


@dataclass
class NLPResult:
    normalized_message: str
    intent: CentralDentistIntent
    entities: dict[str, Any] = field(default_factory=dict)
    temporal_references: dict[str, Any] = field(default_factory=dict)
    confidence_query: Optional[float] = None
    finding_reference: Optional[str] = None
    is_fast_path_candidate: bool = False
    fast_path_type: Optional[str] = None  # "scan_date" | "appointment_date" | "confidence" | "urgency" | "greeting"


# Known finding synonyms mapped to canonical keys
FINDING_SYNONYMS: dict[str, str] = {
    "discoloration": "discoloration",
    "discolouration": "discoloration",
    "discolored": "discoloration",
    "discoloured": "discoloration",
    "yellow": "discoloration",
    "yellowing": "discoloration",
    "yellowish": "discoloration",
    "stain": "discoloration",
    "stains": "discoloration",
    "stained": "discoloration",
    "tartar": "tartar",
    "calculus": "tartar",
    "buildup": "tartar",
    "plaque": "plaque",
    "cavity": "cavity_suspect",
    "cavities": "cavity_suspect",
    "caries": "cavity_suspect",
    "decay": "cavity_suspect",
    "hole": "cavity_suspect",
    "gingivitis": "gingivitis_signs",
    "gums are bleeding": "gingivitis_signs",
    "gum is bleeding": "gingivitis_signs",
    "bleeding gums": "gingivitis_signs",
    "bleeding gum": "gingivitis_signs",
    "gums bleed": "gingivitis_signs",
    "gum bleeds": "gingivitis_signs",
    "bleeding": "gingivitis_signs",
    "swollen gums": "gingivitis_signs",
    "gum inflammation": "gingivitis_signs",
    "ulcer": "oral_ulcer",
    "ulcers": "oral_ulcer",
    "canker": "oral_ulcer",
    "sore": "oral_ulcer",
    "sores": "oral_ulcer",
    "broken tooth": "missing_or_damaged_teeth",
    "damaged tooth": "missing_or_damaged_teeth",
    "missing tooth": "missing_or_damaged_teeth",
}


def normalize_text(text: str) -> str:
    """Normalize input text: lowercased, stripped, collapsed whitespace."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s%?.,!-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_confidence_number(text: str) -> Optional[float]:
    """Extract numeric percentage mentioned in query (e.g. '76%', '76 percent', '0.76')."""
    pct_match = re.search(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)", text)
    if pct_match:
        try:
            val = float(pct_match.group(1))
            return val / 100.0 if val > 1.0 else val
        except ValueError:
            pass

    dec_match = re.search(r"\b0\.\d+\b", text)
    if dec_match:
        try:
            return float(dec_match.group(0))
        except ValueError:
            pass

    return None


def extract_finding_reference(text: str) -> Optional[str]:
    """Match mentions of dental findings."""
    for keyword in sorted(FINDING_SYNONYMS.keys(), key=len, reverse=True):
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, text):
            return FINDING_SYNONYMS[keyword]
    return None


def classify_intent(
    text: str,
    active_finding: Optional[str] = None,
    has_recent_scan_context: bool = False,
    is_first_message: bool = False,
) -> tuple[CentralDentistIntent, dict[str, Any]]:
    """Determine the intent and relevant entities using lightweight rules."""
    norm = normalize_text(text)
    entities: dict[str, Any] = {}
    temporal: dict[str, Any] = {}

    confidence_val = extract_confidence_number(norm)
    if confidence_val is not None:
        entities["confidence_val"] = confidence_val

    finding_ref = extract_finding_reference(norm)
    if finding_ref:
        entities["finding"] = finding_ref

    # Check temporal references
    if re.search(r"\b(last|latest|recent|most recent)\b", norm):
        temporal["target"] = "latest"
    elif re.search(r"\b(compare|comparison|difference|between)\b", norm) and re.search(r"\b(two|both|scans|screenings)\b", norm):
        temporal["target"] = "compare"
    elif re.search(r"\b(previous|before|earlier|history|past)\b", norm):
        temporal["target"] = "history"
    elif re.search(r"\b(next|upcoming|scheduled)\b", norm):
        temporal["target"] = "next"

    entities["temporal"] = temporal

    # 1. GREETING
    greeting_patterns = [
        r"^(hi|hello|hey|salam|assalam|aoa|good morning|good afternoon|good evening)\b",
        r"^howdy\b",
        r"^greetings\b",
    ]
    if any(re.search(p, norm) for p in greeting_patterns) and len(norm.split()) <= 4:
        return CentralDentistIntent.GREETING, entities

    # 2. SCAN COMPARE
    compare_patterns = [
        r"\bcompare\b.*\b(scan|scans|screening|screenings|reports|results)\b",
        r"\b(difference|changes?)\b.*\b(between|since)\b.*\b(scan|scans|last)\b",
        r"\bcompare\b.*\b(last two|last 2|previous)\b",
        r"\bis it (better|worse|different)\b.*\b(than|from)\b.*\b(last|previous)\b",
    ]
    if any(re.search(p, norm) for p in compare_patterns):
        return CentralDentistIntent.SCAN_COMPARE, entities

    # 3. EXPLAIN CONFIDENCE
    confidence_patterns = [
        r"\bwhat does\b.*(?:\bpercent\b|%|\bconfidence\b).*\bmean\b",
        r"\bwhat (is|was) (the|my) confidence\b",
        r"\bhow confident\b",
        r"\bexplain\b.*\bconfidence\b",
        r"\bconfidence level\b",
        r"\bwhy (is it|does it say)\b.*(\d{1,3}\s*%|\d{1,3}\s*percent)",
    ]
    if any(re.search(p, norm) for p in confidence_patterns) or (confidence_val is not None and "mean" in norm):
        return CentralDentistIntent.EXPLAIN_CONFIDENCE, entities

    # 4. APPOINTMENT STATUS
    appointment_patterns = [
        r"\b(when|what time|status|any update)\b.*\bappointment\b",
        r"\b(my|next|scheduled|upcoming|do i have an?)\b.*\bappointment\b",
        r"\bappointment\b.*\b(when|scheduled|status|booked|confirmed)\b",
        r"\bcheck\b.*\bappointment\b",
    ]
    if any(re.search(p, norm) for p in appointment_patterns):
        return CentralDentistIntent.APPOINTMENT_STATUS, entities

    # 5. DENTIST INFORMATION
    dentist_patterns = [
        r"\bwho is my (dentist|doctor)\b",
        r"\b(which|what) dentist\b",
        r"\bdetails of my dentist\b",
        r"\bdentist\b.*\b(contact|clinic|address|number|phone|name)\b",
        r"\bmy assigned dentist\b",
    ]
    if any(re.search(p, norm) for p in dentist_patterns):
        return CentralDentistIntent.DENTIST_INFORMATION, entities

    # 6. SCAN LATEST / WHAT DID MY LAST SCAN SAY
    scan_latest_patterns = [
        r"\bwhat did my (last|latest|recent) scan (say|show|find|flag)\b",
        r"\bwhat (was|is) in my (last|latest|recent) scan\b",
        r"\bmy (latest|last|recent) scan\b",
        r"\bresults? of my (last|latest|recent) scan\b",
        r"\bwhat does my (scan|report) say\b",
        r"\bwhen was my (last|latest) scan\b",
        r"\bwhat urgency\b",
        r"\bwhat is my (urgency|verdict)\b",
    ]
    if any(re.search(p, norm) for p in scan_latest_patterns):
        return CentralDentistIntent.SCAN_LATEST, entities

    # 7. SCAN HISTORY
    scan_history_patterns = [
        r"\b(previous|past|history of|all my)\b.*\b(scans?|screenings?|reports?)\b",
        r"\bwhat happened in my (previous|past) report\b",
        r"\bhow many scans\b",
        r"\bscan history\b",
    ]
    if any(re.search(p, norm) for p in scan_history_patterns):
        return CentralDentistIntent.SCAN_HISTORY, entities

    # 8. EXPLAIN FINDING
    explain_finding_patterns = [
        r"\bwhy does it say\b",
        r"\bwhat is\b.*\b(discoloration|tartar|calculus|caries|decay|cavity|gingivitis|ulcer)\b",
        r"\bexplain\b.*\b(discoloration|tartar|calculus|caries|decay|cavity|gingivitis|ulcer)\b",
        r"\bwhy (do i have|did you find)\b.*\b(discoloration|tartar|calculus|caries|decay|cavity|gingivitis|ulcer)\b",
        r"\bwhat does (discoloration|tartar|calculus|caries|decay|cavity|gingivitis|ulcer) mean\b",
    ]
    if any(re.search(p, norm) for p in explain_finding_patterns) or (finding_ref and any(w in norm for w in ["why", "explain", "what is", "mean"])):
        return CentralDentistIntent.EXPLAIN_FINDING, entities

    # 9. REPORT QUESTION
    report_patterns = [
        r"\b(screening|clinical)?\s*report\b",
        r"\bwhat (does|did) the report say\b",
        r"\breport summary\b",
        r"\bwhat should i do (next|according to my report)\b",
        r"\brecommended specialist\b",
    ]
    if any(re.search(p, norm) for p in report_patterns):
        return CentralDentistIntent.REPORT_QUESTION, entities

    # 10. FOLLOW-UP REFERENCE (e.g. "Why did it flag that?", "What does that mean?", "Is that serious?")
    follow_up_patterns = [
        r"^(is|will|does|can)\s+(that|it|this)\s+",
        r"\b(is that|is it|is this)\s+(serious|bad|dangerous|normal|urgent|harmful|permanent|curable)\b",
        r"\bwhat should i do about (it|that|this)\b",
        r"\bwhy (is that|is it|is this)\b",
        r"\bwhy did (it|my scan|you|the scan|they)\s+flag\s+(that|this|it)?\b",
        r"\bwhy (was|is)\s+(that|this|it)\s+flagged\b",
        r"\bwhat does (that|this|it)\s+mean\b",
        r"\bwhat did (it|that|the scan)\s+mean\b",
        r"\bwhy does it say (that|this|it)\b",
        r"\bhow do i fix (it|that|this)\b",
        r"\bdoes (it|that) hurt\b",
    ]
    if any(re.search(p, norm) for p in follow_up_patterns):
        scan_referenced = bool(re.search(r"\b(scan|flag|report)\b", norm))
        if active_finding or has_recent_scan_context or scan_referenced:
            if active_finding and "finding" not in entities:
                entities["finding"] = active_finding
            return CentralDentistIntent.FOLLOW_UP_REFERENCE, entities

    # 11. DENTAL KNOWLEDGE & SCIENCE (standalone topics: implants, materials, biomechanics, endodontics, etc.)
    dental_science_patterns = [
        r"\b(implant|implants|zirconia|titanium|osseointegration|abutment|prosthesis|prosthetic|crown|bridge|denture|dentures|veneer|veneers)\b",
        r"\b(bruxism|teeth grinding|grinding teeth|clenching|occlusal|occlusion|tmj|temporomandibular|jaw joint|masticat|micro-motion|micromotion|fatigue limit|elastic modulus|tetragonal|monoclinic|phase transformation|low-temperature degradation)\b",
        r"\b(root canal|endodontic|pulpectomy|pulpitis|tooth pulp|infected pulp|periapical|dental pulp)\b",
        r"\b(enamel|dentin|cementum|periodont|periodontium|alveolar bone|osteoclast|osteoclastogenesis|macrophage|osteoblast|bone resorption|collagen synthesis)\b",
        r"\b(intrinsic|extrinsic|discoloration|staining|teeth stain|tooth stain|teeth whitening|bleaching)\b",
        r"\b(diabetes|glycemic|systemic)\b.*\b(gum|periodont|teeth|oral|dental)\b",
        r"\b(gum|periodont|teeth|oral|dental)\b.*\b(diabetes|glycemic|systemic)\b",
        r"\b(orthodontic|braces|aligner|aligners|invisalign|malocclusion|crowding)\b",
        r"\b(fluoride|remineraliz|demineraliz|saliva|xerostomia|oral microbiome)\b",
    ]
    if any(re.search(p, norm) for p in dental_science_patterns):
        return CentralDentistIntent.DENTAL_KNOWLEDGE, entities

    # 12. SYMPTOM QUESTION (personal current symptoms)
    symptom_patterns = [
        r"\b(pain|hurts?|aching|sore|sensitive|sensitivity|bleeding|bleed|swollen|swelling|throbbing)\b",
        r"\b(toothache|jaw pain|cold water|hot drinks?|sweet foods?)\b",
        r"\bbad breath\b",
        r"\bgums bleed\b",
    ]
    if any(re.search(p, norm) for p in symptom_patterns):
        return CentralDentistIntent.SYMPTOM_QUESTION, entities

    # 13. GENERAL ORAL HEALTH (hygiene routines, brushing, flossing)
    oral_health_patterns = [
        r"\b(how (to|should i|can i|do i)|when to|best way to)\b.*\b(brush|floss|clean|take care of|care for|maintain|protect)\b",
        r"\b(take care of|care for|protect|clean|maintain)\s+(my\s+)?(teeth|mouth|gums|oral)\b",
        r"\b(keep|make)\s+(my\s+)?teeth\s+(healthy|clean|white)\b",
        r"\bwhich (toothpaste|toothbrush|brush)\b",
        r"\bprevent\b.*\b(cavities|plaque|decay)\b",
        r"\bwhitening\b",
        r"\b(oral|dental)\s+(health|hygiene|care|tips)\b",
    ]
    if any(re.search(p, norm) for p in oral_health_patterns):
        return CentralDentistIntent.GENERAL_ORAL_HEALTH, entities

    # Fallback to general finding explanation if a finding was detected
    if finding_ref:
        return CentralDentistIntent.EXPLAIN_FINDING, entities

    return CentralDentistIntent.UNKNOWN, entities


def has_personal_record_reference(text: str) -> bool:
    """Check if message explicitly references personal scans, reports, or appointments."""
    norm = normalize_text(text)
    patterns = [
        r"\b(my|our)\s+(scan|scans|screening|screenings|report|reports|result|results|photo|photos|image|images|appointment|appointments|dentist|doctor|booking)\b",
        r"\b(did|does|was)\s+(my|the)\s+(scan|report|screening)\b",
        r"\bwhat did (you|the scan|it|my scan)\s+(flag|find|show|say)\b",
        r"\bfrom my (last|latest|previous|recent) scan\b",
        r"\bmy (records?|findings?|teeth in the (photo|scan|image))\b",
        r"\bwhy did (it|you|the scan)\s+flag\b",
    ]
    return any(re.search(p, norm) for p in patterns)


def is_conversational_follow_up(text: str) -> bool:
    """Check if message is an anaphoric or contextual follow-up to previous turns."""
    norm = normalize_text(text)
    follow_up_patterns = [
        r"^(is|will|does|can|what about|how about|and|why is|why does)\s+(that|it|this)\b",
        r"\b(is that|is it|is this|about that|about it|about this)\b",
        r"\bwhat did you mean by\b",
        r"\byou (mentioned|said|told me)\b",
        r"\b(what about|how about) (the|my|that|this)\b",
        r"\bwhat should i do about (it|that|this)\b",
        r"\bwhy (is that|is it|is this|was that flagged|does it say)\b",
        r"\bwhy did (it|my scan|you|the scan|they)\s+flag\b",
    ]
    if any(re.search(p, norm) for p in follow_up_patterns):
        return True
    if len(norm.split()) <= 4 and any(w in norm for w in ("why", "serious", "bad", "normal", "urgent", "fix", "hurt")):
        return True
    return False


def detect_fast_path(
    intent: CentralDentistIntent,
    norm: str,
) -> tuple[bool, Optional[str]]:
    """Determine if a query is a direct factual question that bypasses Qwen."""
    clean_norm = norm.rstrip("?.! ")

    # Fast path 1: scan date, confidence, urgency
    if intent in (CentralDentistIntent.SCAN_LATEST, CentralDentistIntent.REPORT_QUESTION, CentralDentistIntent.EXPLAIN_CONFIDENCE):
        if re.search(r"\bwhen was my (latest|last|recent) scan\b", clean_norm) or re.search(r"\bdate of my (last|latest) scan\b", clean_norm):
            return True, "scan_date"
        if re.search(r"\bwhat (is|was) (the|my) (latest )?confidence\b", clean_norm) or clean_norm in ("what was the confidence", "what is the confidence"):
            return True, "confidence"
        if re.search(r"\bwhat (is|was) (the|my) urgency\b", clean_norm) or re.search(r"\burgency level\b", clean_norm) or clean_norm in ("what is my urgency", "what was my urgency"):
            return True, "urgency"

    # Fast path 2: appointment date/time
    if intent == CentralDentistIntent.APPOINTMENT_STATUS:
        if re.search(r"\bwhen is my (next )?appointment\b", clean_norm) or clean_norm in ("when is my appointment", "when is my next appointment", "do i have an appointment"):
            return True, "appointment_date"

    # Fast path 3: simple greetings
    if intent == CentralDentistIntent.GREETING and len(norm.split()) <= 2:
        return True, "greeting"

    # Fast path 4: unambiguous oral hygiene essentials (instant response)
    if intent == CentralDentistIntent.GENERAL_ORAL_HEALTH or "brush" in clean_norm or "floss" in clean_norm:
        if re.search(r"\b(what is the (best|proper|correct) way to brush|how (should i|to|do i) brush)\b", clean_norm):
            return True, "brushing_guide"
        if re.search(r"\b(how often (should i|to) floss|how (should i|to|do i) floss|when (should i|to) floss)\b", clean_norm):
            return True, "flossing_guide"

    return False, None


def analyze_message(
    raw_message: str,
    active_finding: Optional[str] = None,
    has_recent_scan_context: bool = False,
) -> NLPResult:
    """Run full deterministic NLP pipeline on a user message."""
    norm = normalize_text(raw_message)
    intent, entities = classify_intent(
        raw_message,
        active_finding=active_finding,
        has_recent_scan_context=has_recent_scan_context,
    )
    is_fast_path, fast_type = detect_fast_path(intent, norm)

    return NLPResult(
        normalized_message=norm,
        intent=intent,
        entities=entities,
        temporal_references=entities.get("temporal", {}),
        confidence_query=entities.get("confidence_val"),
        finding_reference=entities.get("finding"),
        is_fast_path_candidate=is_fast_path,
        fast_path_type=fast_type,
    )
