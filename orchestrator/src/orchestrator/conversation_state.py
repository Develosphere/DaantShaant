"""Lightweight in-memory conversation state tracker.

Tracks dental issues, subjects, corrections, and conversational facts
per conversation using deterministic regex/keyword logic only.
No LLM calls, no databases, no embeddings.
"""

import logging
import re
from collections import deque
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# --- Confidence-based dental issue detection ---

# Each entry: (canonical_name, keywords, base_confidence)
# Higher confidence = more specific match
DENTAL_ISSUE_MAP = [
    ("toothache", ["tooth hurts", "tooth aches", "tooth aching", "tooth pain", "teeth hurt", "teeth pain", "teeth aching", "toothache", "daant mein drd", "daant dard", "daant pe dard", "teeths hurt", "huritng", "hruts", "hrut", "drd", "teeth paining", "tooth paining"], 0.95),
    ("toothache", ["pain in tooth", "pain in teeth", "ache in tooth", "aching tooth", "pain hai"], 0.90),
    ("bleeding gums", ["gums bleed", "gum bleeds", "gums bleeding", "bleeding gums", "blood from gums", "blood when brush", "bleed when brush", "bleed when floss", "gums blud", "khoon", "blood aa", "gums se blood", "bleed gums", "bleeding gum"], 0.95),
    ("bleeding gums", ["bleed", "bleeding", "blud"], 0.55),
    ("sensitivity", ["sensitive teeth", "tooth sensitivity", "teeth sensitivity", "sensitive tooth", "hurts when cold", "hurts when hot", "pain with cold", "pain with hot", "cold sensitivity", "hot sensitivity", "cold ones", "cold one", "thanda lagta", "garm lagta", "sensitivty"], 0.92),
    ("sensitivity", ["sensitive", "cold stuff", "hot stuff", "thanda", "garm"], 0.60),
    ("tartar/plaque buildup", ["tartar", "plaque buildup", "plaque build up", "hard yellow stuff", "yellow stuff near gum", "yellow stuff on teeth", "yellow buildup", "calculus on teeth", "hardened plaque", "daant pe yellow", "peela stuff", "yellow stuff", "yellow stuf"], 0.93),
    ("discolored teeth", ["yellow teeth", "teeth are yellow", "teeth yellow", "stained teeth", "teeth stain", "teeth discolored", "discolored teeth", "brown teeth", "dark teeth", "teeths yellow", "teeth are brown"], 0.88),
    ("discolored teeth", ["yellow", "stain", "peela"], 0.40),
    ("cavity/tooth decay", ["cavity", "cavities", "tooth decay", "decayed tooth", "hole in tooth", "hole in teeth", "rotten tooth", "keeda", "cavits"], 0.93),
    ("bad breath", ["bad breath", "breath smells", "mouth smells", "halitosis", "stinky breath", "smelly mouth"], 0.92),
    ("swollen gums", ["swollen gum", "gum swelling", "gums swollen", "inflamed gum", "gum inflammation", "puffy gums", "swoln gums", "swollen gums"], 0.92),
    ("loose tooth", ["loose tooth", "wobbly tooth", "tooth moving", "tooth wiggle", "tooth loose", "teeth loose"], 0.93),
    ("gum pain", ["gum hurts", "gums hurt", "gum pain", "gums pain", "sore gums", "gum sore"], 0.90),
    ("wisdom tooth", ["wisdom tooth", "wisdom teeth", "third molar"], 0.93),
    ("broken tooth", ["broken tooth", "chipped tooth", "cracked tooth", "tooth broke", "tooth cracked", "tooth chipped"], 0.95),
    ("jaw pain", ["jaw hurts", "jaw pain", "jaw ache", "tmj", "jaw clicking", "jaw lock"], 0.90),
    ("mouth ulcer", ["mouth ulcer", "canker sore", "mouth sore", "ulcer in mouth", "sore in mouth"], 0.92),
    ("dry mouth", ["dry mouth", "mouth feels dry", "no saliva", "less saliva"], 0.88),
]

# Minimum confidence to persist an issue
ISSUE_CONFIDENCE_THRESHOLD = 0.55

# --- Subject detection ---

# Possessive patterns that indicate talking about someone else
THIRD_PARTY_PATTERNS = [
    (r'\bmy\s+(brother|sister|mom|mother|dad|father|son|daughter|wife|husband|friend|kid|child|uncle|aunt|cousin)\b.*\b(has|had|is|was|got|gets|feels|feel|said|told|complain|hurts?|aches?|bleeds?|pain)', "other"),
    (r'\b(brother|sister|mom|mother|dad|father|son|daughter|wife|husband|friend|kid|child|uncle|aunt|cousin)\s*\'?s?\s+(tooth|teeth|gum|gums|mouth|jaw)\b', "other"),
    (r'\b(his|her|their)\s+(tooth|teeth|gum|gums|mouth|jaw)\b', "other"),
]

# Casual slang — these are addressed TO the assistant, NOT about a third party
CASUAL_SLANG = {"bro", "brother", "bhai", "dude", "man", "buddy", "mate", "friend", "yaar", "bhai sahab"}

# --- Correction detection ---

CORRECTION_PATTERNS = [
    r'\bno\s*,?\s*i\s+mean\s+me\b',
    r'\bi\s+was\s+talking\s+about\s+(myself|me)\b',
    r'\bnot\s+my\s+(brother|sister|mom|dad|father|mother|friend|son|daughter|wife|husband)\b',
    r'\bno\s*,?\s*(i|me|my)\b.*\bnot\s+(him|her|them|brother|sister)\b',
    r'\bi\s+meant\s+(myself|me|my)\b',
    r'\bfor\s+me\s*,?\s*not\b',
    r'\bno\s*,?\s*it\'?s?\s+(me|mine|my)\b',
    r"\bno\s*,?\s*i'm\s+the\s+one\b",
]

# --- Off-domain detection ---
# Only triggers for actual physical medical symptoms + non-dental body areas

NON_DENTAL_BODY_PARTS = [
    "stomach", "belly", "tummy", "chest", "heart", "lung", "back",
    "knee", "ankle", "foot", "feet", "leg", "arm", "elbow", "wrist",
    "shoulder", "hip", "neck", "spine", "eye", "ear",
    "nose", "skin", "hand", "finger", "toe",
]

# Standalone symptoms that are off-domain even without a body part
# (e.g., "i have a fever" is clearly non-dental)
STANDALONE_OFF_DOMAIN = [
    "fever", "headache", "migraine", "nausea", "vomit",
    "diarrhea", "rash", "dizzy", "dizziness", "faint",
]

MEDICAL_SYMPTOM_WORDS = [
    "hurts", "pain", "ache", "aching", "sore", "burning", "burn",
    "swollen", "swelling", "injury", "injured", "broken", "fracture",
    "fever", "nausea", "vomit", "dizzy", "dizziness", "rash",
    "infection", "bleeding", "sprain",
]

# Things that LOOK medical but are just casual chat / small talk
SMALL_TALK_INDICATORS = [
    "dying from", "killing me", "gonna die", "dead from",
    "exam", "exams", "test", "work", "homework", "assignment",
    "stress", "bored", "tired", "sleepy", "hungry",
    "lol", "lmao", "haha", "😭", "💀",
]

# --- Follow-up resolution ---

FOLLOW_UP_PHRASES = [
    r'\bwill\s+(brushing|flossing|mouthwash|rinsing|salt\s*water)\s+help\b',
    r'\bwhat\s+should\s+i\s+do\b',
    r'\bis\s+(that|it|this)\s+(dangerous|serious|bad|normal|okay|ok)\b',
    r'\bcan\s+(it|this|that)\s+(heal|go\s+away|fix|recover|get\s+better)\b',
    r'\bshould\s+i\s+(see|go\s+to|visit)\s+(a\s+)?dentist\b',
    r'\bhow\s+(long|much)\s+(will|does|do)\b',
    r'\bwhat\s+causes?\s+(this|that|it)\b',
    r'\bwhy\s+(does|is)\s+(this|that|it)\b',
    r'\bwhat\s+(do|can)\s+i\s+do\b',
    r'\bhow\s+to\s+(fix|treat|cure|stop|prevent)\s+(this|that|it)\b',
    r'\bis\s+it\s+(ok|okay|fine|normal|safe)\b',
]

# Max turns before issue starts decaying
ISSUE_TTL_TURNS = 8
# After this many turns with no dental mention, clear active issue
ISSUE_EXPIRE_TURNS = 12


class ConversationState:
    """Per-conversation state."""

    __slots__ = (
        "current_subject", "active_dental_issue", "active_issue_confidence",
        "secondary_issues", "last_confirmed_issue", "last_user_intent",
        "facts", "correction_flag", "turns_since_dental_mention",
    )

    def __init__(self):
        self.current_subject: str = "user"
        self.active_dental_issue: Optional[str] = None
        self.active_issue_confidence: float = 0.0
        self.secondary_issues: list = []  # max 3
        self.last_confirmed_issue: Optional[str] = None
        self.last_user_intent: Optional[str] = None
        self.facts: deque = deque(maxlen=5)
        self.correction_flag: bool = False
        self.turns_since_dental_mention: int = 0


# Global state store: conversation_id -> ConversationState
_conversation_states: Dict[str, ConversationState] = {}


def _get_state(conversation_id: str) -> ConversationState:
    """Get or create state for a conversation."""
    cid = str(conversation_id)
    if cid not in _conversation_states:
        _conversation_states[cid] = ConversationState()
    return _conversation_states[cid]


def detect_dental_issue(text: str) -> Tuple[Optional[str], float]:
    """Detect dental issue from text with confidence score.

    Returns (issue_name, confidence) or (None, 0.0).
    Uses deterministic keyword scoring only.
    """
    text_lower = text.lower()
    best_issue = None
    best_confidence = 0.0

    for canonical_name, keywords, base_confidence in DENTAL_ISSUE_MAP:
        for keyword in keywords:
            if keyword in text_lower:
                # Boost confidence for longer/more specific matches
                specificity_boost = min(len(keyword.split()) * 0.02, 0.05)
                confidence = min(base_confidence + specificity_boost, 1.0)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_issue = canonical_name
                    break  # found match in this group, move on

    return best_issue, best_confidence


def detect_subject(text: str) -> str:
    """Detect who the user is talking about.

    Returns 'user' or 'other'.
    Treats casual slang (bro, dude, bhai) as addressing the assistant.
    Only returns 'other' for explicit possessive third-party references.
    """
    text_lower = text.lower()

    # Check third-party possessive patterns
    for pattern, subject in THIRD_PARTY_PATTERNS:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            matched_text = match.group()
            words = text_lower.split()

            # Check if there's a standalone slang word BEFORE the match
            # that is NOT part of the matched possessive phrase.
            # e.g., "bro my tooth hurts" — "bro" is before and separate
            # vs.  "my brother has tooth pain" — "brother" IS the possessive subject
            is_slang_address = False
            for slang in CASUAL_SLANG:
                if slang in words:
                    slang_pos = text_lower.find(slang)
                    # Slang must appear BEFORE the possessive pattern
                    # AND must NOT be the same word used in the possessive match
                    if slang_pos < match.start() and slang not in matched_text:
                        is_slang_address = True
                        break

            if is_slang_address:
                # Slang address came first, possessive match is incidental
                return "user"
            return "other"

    return "user"


def detect_correction(text: str) -> bool:
    """Detect if user is correcting a subject misunderstanding."""
    text_lower = text.lower()
    for pattern in CORRECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False


def is_off_domain(text: str) -> bool:
    """Check if message is about non-dental medical topics.

    Only triggers for actual physical symptoms + non-dental body areas.
    Does NOT trigger on small talk, casual expressions, or hyperbole.
    """
    text_lower = text.lower()

    # Check for dental content — if message mentions teeth/gums, never off-domain
    dental_words = ["tooth", "teeth", "gum", "gums", "dental", "oral", "mouth",
                    "jaw", "molar", "cavity", "brush", "floss"]
    for word in dental_words:
        if word in text_lower:
            return False

    # Check for small talk / casual indicators first — never off-domain
    for indicator in SMALL_TALK_INDICATORS:
        if indicator in text_lower:
            return False

    # Check standalone off-domain symptoms (fever, headache, etc.)
    # These are clearly non-dental even without a body part
    for symptom in STANDALONE_OFF_DOMAIN:
        if re.search(r'\b' + re.escape(symptom) + r'\b', text_lower):
            return True

    # Must have BOTH a non-dental body part AND a medical symptom
    has_non_dental_body = False
    for part in NON_DENTAL_BODY_PARTS:
        if re.search(r'\b' + re.escape(part) + r'\b', text_lower):
            has_non_dental_body = True
            break

    if not has_non_dental_body:
        return False

    has_medical_symptom = False
    for symptom in MEDICAL_SYMPTOM_WORDS:
        if re.search(r'\b' + re.escape(symptom) + r'\b', text_lower):
            has_medical_symptom = True
            break

    return has_non_dental_body and has_medical_symptom


def is_follow_up(text: str) -> bool:
    """Check if message is a contextual follow-up."""
    text_lower = text.lower().strip()
    for pattern in FOLLOW_UP_PHRASES:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    # Also catch very short messages that are clearly follow-ups
    if len(text_lower.split()) <= 6:
        short_followups = [
            "what should i do", "what do i do", "what can i do",
            "is that bad", "is that normal", "should i worry",
            "will it go away", "can it heal", "how to fix",
            "what causes it", "why is that", "and then",
        ]
        for phrase in short_followups:
            if phrase in text_lower:
                return True
    return False


def resolve_follow_up(text: str, state: ConversationState) -> Optional[str]:
    """Resolve what a follow-up message refers to.

    Returns the active issue context string, or None if no context.
    """
    if state.active_dental_issue:
        return state.active_dental_issue
    if state.last_confirmed_issue:
        return state.last_confirmed_issue
    if state.secondary_issues:
        return state.secondary_issues[0]
    return None


def update_from_message(conversation_id: str, user_text: str, intent: str) -> Dict[str, Any]:
    """Update conversation state from a user message.

    Called BEFORE LLM generation. All logic is deterministic.

    Returns dict with state changes for logging/debugging.
    """
    state = _get_state(conversation_id)
    changes = {}

    # ── OFF-DOMAIN GUARD ──────────────────────────────────────────────
    # If the message is off-domain, do NOT store anything in state.
    # The conversation memory must never contain non-dental information.
    if intent == "off_domain" or is_off_domain(user_text):
        logger.info(f"[STATE] Off-domain message — skipping all state updates")
        state.last_user_intent = intent
        changes["intent"] = intent
        changes["off_domain_blocked"] = True
        return changes
    # ──────────────────────────────────────────────────────────────────

    # Reset correction flag from previous turn
    prev_correction = state.correction_flag
    state.correction_flag = False

    # 1. Check for correction FIRST (highest priority)
    if detect_correction(user_text):
        state.correction_flag = True
        state.current_subject = "user"
        changes["correction"] = True
        changes["subject_corrected_to"] = "user"
        logger.info(f"[STATE] Correction detected, subject → user")

        # Re-extract dental issue from correction context
        issue, confidence = detect_dental_issue(user_text)
        if issue and confidence >= ISSUE_CONFIDENCE_THRESHOLD:
            _set_active_issue(state, issue, confidence)
            changes["issue_reaffirmed"] = issue
    else:
        # 2. Detect subject
        subject = detect_subject(user_text)
        if subject != state.current_subject:
            state.current_subject = subject
            changes["subject_changed"] = subject
            logger.info(f"[STATE] Subject → {subject}")

    # 3. Detect dental issue with confidence
    issue, confidence = detect_dental_issue(user_text)
    if issue and confidence >= ISSUE_CONFIDENCE_THRESHOLD:
        _set_active_issue(state, issue, confidence)
        state.turns_since_dental_mention = 0
        changes["issue_detected"] = issue
        changes["issue_confidence"] = confidence
        logger.info(f"[STATE] Issue detected: {issue} (confidence={confidence:.2f})")
    else:
        # No dental issue in this message — increment TTL counter
        state.turns_since_dental_mention += 1

    # 4. TTL decay
    if state.turns_since_dental_mention >= ISSUE_EXPIRE_TURNS:
        if state.active_dental_issue:
            logger.info(f"[STATE] Issue expired after {state.turns_since_dental_mention} turns: {state.active_dental_issue}")
            state.active_dental_issue = None
            state.active_issue_confidence = 0.0
            state.secondary_issues.clear()
            changes["issue_expired"] = True
    elif state.turns_since_dental_mention >= ISSUE_TTL_TURNS:
        # Decay secondary issues first
        if state.secondary_issues:
            removed = state.secondary_issues.pop()
            changes["secondary_decayed"] = removed
            logger.info(f"[STATE] Secondary issue decayed: {removed}")

    # 5. Store conversational fact (only dental content)
    fact = _extract_fact(user_text, issue)
    if fact:
        state.facts.append(fact)
        changes["fact_stored"] = fact

    # 6. Update last intent
    state.last_user_intent = intent
    changes["intent"] = intent

    logger.info(f"[STATE] State for {str(conversation_id)[:8]}: "
                f"subject={state.current_subject}, "
                f"issue={state.active_dental_issue}, "
                f"secondary={state.secondary_issues}, "
                f"turns_no_dental={state.turns_since_dental_mention}")

    return changes


def _set_active_issue(state: ConversationState, new_issue: str, confidence: float):
    """Set active issue, pushing previous to secondary if different."""
    if state.active_dental_issue and state.active_dental_issue != new_issue:
        # Push current active to secondary (max 3)
        if state.active_dental_issue not in state.secondary_issues:
            state.secondary_issues.insert(0, state.active_dental_issue)
            if len(state.secondary_issues) > 3:
                state.secondary_issues.pop()

    state.active_dental_issue = new_issue
    state.active_issue_confidence = confidence
    state.last_confirmed_issue = new_issue


def _extract_fact(text: str, issue: Optional[str]) -> Optional[str]:
    """Extract a short conversational fact from user message.
    
    Only stores dental-related facts.  Non-dental medical content
    is explicitly filtered out so it never leaks into dental memory.
    """
    text_lower = text.lower().strip()
    # Skip very short or empty
    if len(text_lower) < 5:
        return None

    # ── OFF-DOMAIN FILTER ─────────────────────────────────────────
    # Never store non-dental medical facts
    off_domain_blocklist = [
        "stomach", "belly", "tummy", "chest", "heart", "lung", "back pain",
        "knee", "ankle", "foot", "feet", "leg", "arm", "elbow", "wrist",
        "shoulder", "hip", "spine", "eye", "ear", "skin", "hand",
        "finger", "toe", "fever", "headache", "migraine", "nausea",
        "vomit", "diarrhea", "rash", "dizzy", "faint",
    ]
    for blocked in off_domain_blocklist:
        if blocked in text_lower:
            # Only block if there's no dental context in the same message
            dental_words = ["tooth", "teeth", "gum", "gums", "dental",
                            "oral", "mouth", "jaw", "molar", "brush", "floss"]
            if not any(dw in text_lower for dw in dental_words):
                logger.info(f"[STATE] Blocked off-domain fact: '{text[:40]}...'")
                return None
    # ──────────────────────────────────────────────────────────────

    # Truncate to keep facts compact
    fact = text[:80]
    if issue:
        fact = f"{issue}: {fact}"
    return fact


def get_context_summary(conversation_id: str) -> str:
    """Get compact context string for prompt injection.

    Keeps token usage minimal. Returns a short human-readable summary.
    """
    state = _get_state(conversation_id)

    parts = []

    if state.correction_flag:
        parts.append(f"CORRECTION: User clarified they meant themselves (not a third party)")

    if state.active_dental_issue:
        parts.append(f"Current issue: {state.active_dental_issue}")
        if state.current_subject != "user":
            parts.append(f"Subject: {state.current_subject}'s issue")

    if state.secondary_issues:
        parts.append(f"Also mentioned: {', '.join(state.secondary_issues)}")

    if state.facts:
        # Only include last 2-3 most recent facts for compactness
        recent = list(state.facts)[-3:]
        parts.append(f"Recent context: {' | '.join(recent)}")

    if not parts:
        return ""

    return "Conversation state:\n" + "\n".join(parts)


def get_contextual_recovery(conversation_id: str) -> str:
    """Generate issue-aware deterministic dental answer.

    Used when all LLM providers fail.  Always returns an informative
    answer — NEVER a follow-up question, NEVER a generic fallback.
    """
    state = _get_state(conversation_id)

    if state.active_dental_issue:
        issue = state.active_dental_issue
        # Informative answers, NOT follow-up questions
        recoveries = {
            "toothache": (
                "A toothache can happen because of cavities, sensitivity, "
                "gum inflammation, or even a small crack. Over-the-counter "
                "pain relief and warm saltwater rinses can help for now, but "
                "if it persists or gets worse a dental check-up is a good idea."
            ),
            "bleeding gums": (
                "Gums often bleed because plaque irritates the gum tissue. "
                "Gentle brushing with a soft-bristled brush, daily flossing, "
                "and warm saltwater rinses usually help reduce the inflammation "
                "over time."
            ),
            "sensitivity": (
                "Tooth sensitivity is usually caused by thinning enamel or "
                "receding gums that expose the inner layer of the tooth. Using "
                "a sensitivity toothpaste and avoiding very hot or cold foods "
                "can help. If it keeps happening, a dentist can check for "
                "cracks or decay."
            ),
            "tartar/plaque buildup": (
                "Hard yellow buildup near the gums is often tartar — hardened "
                "plaque that can't usually be removed by brushing alone. A "
                "professional dental cleaning is the best way to get rid of "
                "it and prevent gum irritation."
            ),
            "discolored teeth": (
                "Teeth can become yellow or stained from coffee, tea, smoking, "
                "or natural enamel aging. Regular brushing with a whitening "
                "toothpaste helps with surface stains. For deeper discoloration "
                "a dentist can suggest safe whitening options."
            ),
            "cavity/tooth decay": (
                "Cavities form when bacteria produce acid that eats into the "
                "enamel. Small ones might not hurt at first, but they can grow "
                "if left untreated. A dentist can fill them before they get worse."
            ),
            "swollen gums": (
                "Swollen gums are usually a sign of inflammation from plaque "
                "buildup or early gum disease. Gentle brushing along the gum "
                "line, flossing, and saltwater rinses can help bring the "
                "swelling down."
            ),
            "gum pain": (
                "Sore gums can happen from irritation, brushing too hard, or "
                "the start of gum disease. Switching to a soft-bristled brush "
                "and doing warm saltwater rinses usually helps. If it continues "
                "for more than a week, checking with a dentist is a good idea."
            ),
            "bad breath": (
                "Bad breath is often caused by bacteria on the tongue, food "
                "stuck between teeth, or gum issues. Brushing your tongue, "
                "flossing daily, and staying hydrated usually helps."
            ),
            "loose tooth": (
                "A loose tooth in adults is usually caused by gum disease "
                "weakening the supporting bone, or sometimes by injury. This "
                "is definitely worth seeing a dentist about as soon as possible."
            ),
            "wisdom tooth": (
                "Wisdom teeth can cause pain and swelling when coming in, "
                "especially if there isn't enough room. Warm saltwater rinses "
                "help with discomfort. A dentist can take an X-ray to check "
                "what's going on."
            ),
            "broken tooth": (
                "A broken or chipped tooth can come from biting something hard, "
                "injury, or weakened enamel. Avoid chewing on that side and see "
                "a dentist as soon as you can."
            ),
            "jaw pain": (
                "Jaw pain can come from teeth grinding, TMJ issues, or muscle "
                "tension. Avoiding hard or chewy foods and using a warm compress "
                "can help. If it persists or your jaw clicks, a dentist can help."
            ),
            "mouth ulcer": (
                "Mouth ulcers are usually from minor irritation, stress, or "
                "certain foods. They typically heal on their own within a week "
                "or two. Warm saltwater rinses can help with discomfort."
            ),
            "dry mouth": (
                "Dry mouth happens when salivary glands don't produce enough "
                "saliva, which can increase cavity risk. Staying hydrated and "
                "chewing sugar-free gum can help."
            ),
        }
        return recoveries.get(
            issue,
            f"{issue.capitalize()} can have several causes. Good oral hygiene "
            f"with regular brushing, flossing, and dental check-ups is the best "
            f"way to manage it."
        )

    # No context — give general useful dental advice (NOT a question)
    return (
        "Good oral health starts with brushing twice a day with fluoride "
        "toothpaste, flossing daily, and visiting your dentist for regular "
        "check-ups. If you have a specific dental concern, describe it and "
        "I can give you more targeted advice."
    )


def get_state(conversation_id: str) -> ConversationState:
    """Get state for external read access."""
    return _get_state(conversation_id)


def clear_state(conversation_id: str):
    """Clear state for a conversation (for testing)."""
    cid = str(conversation_id)
    if cid in _conversation_states:
        del _conversation_states[cid]
