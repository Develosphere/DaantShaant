"""Intent classification for conversational routing."""

import logging
import re
from enum import Enum
from typing import Optional, Tuple

from orchestrator.conversation_state import (
    is_off_domain,
    detect_correction,
    is_follow_up,
)

logger = logging.getLogger(__name__)


class UserIntent(str, Enum):
    """User message intent categories."""
    GREETING = "greeting"
    GENERAL_ORAL_QUESTION = "general_oral_question"
    IMAGE_ANALYSIS = "image_analysis"
    SYMPTOM_DISCUSSION = "symptom_discussion"
    FOLLOW_UP = "follow_up"
    COMPARE_HISTORY = "compare_history"
    OFF_DOMAIN = "off_domain"
    CORRECTION = "correction"
    UNKNOWN = "unknown"


class IntentClassifier:
    """Rule-based intent classifier for user messages."""
    
    # Conversational address patterns (casual references to assistant)
    CASUAL_ADDRESS_PATTERNS = [
        r'\b(bro|brother|bhai|buddy|dude|mate|friend|man)\b(?!\s+(has|had|is|was|got|gets|feels|said|told|asked))',
        r'^(hey|hi|yo)\s+(bro|brother|bhai|buddy|dude|mate)',
    ]
    
    # Greeting patterns (only pure greetings without medical content)
    GREETING_PATTERNS = [
        r'^(hi|hello|hey|greetings|good\s+(morning|afternoon|evening))[\s!.]*$',
        r'^(hi|hello|hey)\s+(there|bro|brother|bhai|buddy)[\s!.]*$',
        r'^(what\'s\s+up|wassup|sup)[\s!.]*$',
    ]
    
    # General oral health question patterns
    GENERAL_ORAL_PATTERNS = [
        r'\b(how\s+(often|many\s+times)|should\s+i)\s+(brush|floss|clean)',
        r'\b(what|which)\s+(toothpaste|mouthwash|brush|floss)',
        r'\b(best\s+way|how\s+to)\s+(brush|floss|clean|maintain)',
        r'\b(prevent|avoid)\s+(cavit|decay|plaque|tartar|gum\s+disease)',
        r'\b(recommend|suggest|advice)\s+(for|about)',
        r'\bwhat\s+(causes|is)\s+(cavit|plaque|tartar|gingivitis|sensitivity)',
        r'\b(dental|oral)\s+(care|health|hygiene)',
        r'\b(whitening|whiten)\s+teeth',
    ]
    
    # Symptom discussion patterns
    SYMPTOM_PATTERNS = [
        r'\b(pain|hurt|ache|aching|painful|sore)',
        r'\b(bleed|bleeding|blood)',
        r'\b(sensitive|sensitivity)',
        r'\b(swollen|swelling|inflamed)',
        r'\b(loose|wobbly)\s+tooth',
        r'\b(bad\s+breath|halitosis)',
        r'\b(tooth|teeth)\s+(hurt|pain|ache)',
        r'\b(gum|gums)\s+(hurt|pain|bleed|sore)',
        r'\bwhen\s+i\s+(eat|drink|bite|chew)',
        r'\bwhy\s+(do|does|are|is)\s+(my|gums|teeth)',
        r'\b(yellow|brown|dark)\s+(stuff|buildup|teeth|thing)',
        r'\b(teeth|tooth|gums?)\s+(are|is|look|looks|feel|feels)\s+(yellow|brown|dark|stained|discolored|swollen|sore|painful|sensitive)',
        r'\b(yellow|stained|discolored)\s+(teeth|tooth)',
        r'\b(tartar|plaque|cavity|cavities|decay)',
        r'\b(dry\s+mouth|mouth\s+ulcer|canker\s+sore)',
        r'\b(broken|chipped|cracked)\s+(tooth|teeth)',
        r'\b(wisdom\s+tooth|wisdom\s+teeth)',
    ]
    
    # Follow-up patterns
    FOLLOW_UP_PATTERNS = [
        r'^(yes|yeah|yep|no|nope|okay|ok|sure|thanks|thank\s+you)[\s!.]*$',
        r'\b(what\s+about|how\s+about)\b',
        r'\b(also|additionally|furthermore)\b',
        r'\b(and\s+what|what\s+else)\b',
    ]
    
    # History comparison patterns
    COMPARE_HISTORY_PATTERNS = [
        r'\b(compare|comparison|difference|changed|improve|worse)',
        r'\b(last\s+time|previous|before|earlier)',
        r'\b(better|worse)\s+than',
        r'\b(progress|improvement|deteriorat)',
    ]
    
    def classify(self, text: str, has_image: bool = False, is_first_message: bool = False) -> Tuple[UserIntent, dict]:
        """
        Classify user message intent with context.
        
        Args:
            text: User message text
            has_image: Whether message includes an image
            is_first_message: Whether this is the first message in conversation
            
        Returns:
            Tuple of (classified intent, context info)
        """
        context_info = {
            "has_casual_address": False,
            "cleaned_text": text,
            "is_pure_greeting": False,
            "has_medical_content": False
        }
        
        if not text or not text.strip():
            if has_image:
                logger.info(f"[INTENT] IMAGE_ANALYSIS (image present)")
                return UserIntent.IMAGE_ANALYSIS, context_info
            return UserIntent.UNKNOWN, context_info
        
        text_lower = text.lower().strip()
        logger.info(f"[INTENT] Classifying: '{text}' (first_message={is_first_message})")
        
        # --- Priority 1: Correction detection (highest priority) ---
        if detect_correction(text):
            logger.info(f"[INTENT] CORRECTION detected")
            context_info["is_correction"] = True
            return UserIntent.CORRECTION, context_info
        
        # --- Priority 2: Off-domain detection ---
        # Only for actual physical medical symptoms + non-dental body areas
        # Does NOT trigger on small talk or casual expressions
        if is_off_domain(text):
            logger.info(f"[INTENT] OFF_DOMAIN (non-dental medical)")
            return UserIntent.OFF_DOMAIN, context_info
        
        # Detect casual address to assistant
        if self._matches_patterns(text_lower, self.CASUAL_ADDRESS_PATTERNS):
            context_info["has_casual_address"] = True
            # Clean the text by removing casual address for better intent detection
            cleaned_text = self._remove_casual_address(text_lower)
            context_info["cleaned_text"] = cleaned_text
            logger.info(f"[INTENT] Detected casual address, cleaned text: '{cleaned_text}'")
        else:
            cleaned_text = text_lower
        
        # Check for medical/dental content
        has_medical = (
            self._matches_patterns(cleaned_text, self.SYMPTOM_PATTERNS) or
            self._matches_patterns(cleaned_text, self.GENERAL_ORAL_PATTERNS) or
            any(word in cleaned_text for word in ['teeth', 'tooth', 'gum', 'gums', 'dental', 'oral', 'brush', 'floss'])
        )
        context_info["has_medical_content"] = has_medical
        logger.info(f"[INTENT] Medical content detected: {has_medical}")
        
        # Image analysis takes priority if image is present
        if has_image:
            logger.info(f"[INTENT] IMAGE_ANALYSIS (image present)")
            return UserIntent.IMAGE_ANALYSIS, context_info
        
        # Check for pure greeting (only if first message OR no medical content)
        is_pure_greeting = self._matches_patterns(text_lower, self.GREETING_PATTERNS)
        context_info["is_pure_greeting"] = is_pure_greeting
        
        if is_pure_greeting and (is_first_message or not has_medical):
            logger.info(f"[INTENT] GREETING (pure greeting, first_message={is_first_message}, has_medical={has_medical})")
            return UserIntent.GREETING, context_info
        
        # Check symptom discussion (high priority)
        if self._matches_patterns(cleaned_text, self.SYMPTOM_PATTERNS):
            logger.info(f"[INTENT] SYMPTOM_DISCUSSION")
            return UserIntent.SYMPTOM_DISCUSSION, context_info
        
        # Check history comparison
        if self._matches_patterns(cleaned_text, self.COMPARE_HISTORY_PATTERNS):
            logger.info(f"[INTENT] COMPARE_HISTORY")
            return UserIntent.COMPARE_HISTORY, context_info
        
        # Check general oral health questions
        if self._matches_patterns(cleaned_text, self.GENERAL_ORAL_PATTERNS):
            logger.info(f"[INTENT] GENERAL_ORAL_QUESTION")
            return UserIntent.GENERAL_ORAL_QUESTION, context_info
        
        # Check contextual follow-up (uses conversation_state detection)
        if is_follow_up(text):
            logger.info(f"[INTENT] FOLLOW_UP (contextual)")
            return UserIntent.FOLLOW_UP, context_info
        
        # Check simple follow-up patterns (short messages)
        if len(cleaned_text.split()) <= 5 and self._matches_patterns(cleaned_text, self.FOLLOW_UP_PATTERNS):
            logger.info(f"[INTENT] FOLLOW_UP")
            return UserIntent.FOLLOW_UP, context_info
        
        # Default to general question if it's a question
        if '?' in cleaned_text or cleaned_text.startswith(('what', 'how', 'why', 'when', 'where', 'can', 'should', 'is', 'are', 'do', 'does')):
            logger.info(f"[INTENT] GENERAL_ORAL_QUESTION (question detected)")
            return UserIntent.GENERAL_ORAL_QUESTION, context_info
        
        # Short messages with existing context → treat as follow-up
        if len(cleaned_text.split()) <= 8:
            logger.info(f"[INTENT] FOLLOW_UP (short message, possible contextual)")
            return UserIntent.FOLLOW_UP, context_info
        
        logger.info(f"[INTENT] UNKNOWN")
        return UserIntent.UNKNOWN, context_info
    
    def _matches_patterns(self, text: str, patterns: list[str]) -> bool:
        """Check if text matches any of the given regex patterns."""
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _remove_casual_address(self, text: str) -> str:
        """Remove casual address terms from text for better intent detection."""
        # Remove casual address at the beginning
        text = re.sub(r'^(hey|hi|yo)\s+(bro|brother|bhai|buddy|dude|mate)\s*,?\s*', '', text, flags=re.IGNORECASE)
        # Remove standalone casual address
        text = re.sub(r'\b(bro|brother|bhai|buddy|dude|mate)\b(?!\s+(has|had|is|was|got|gets|feels|said|told|asked))', '', text, flags=re.IGNORECASE)
        # Clean up extra spaces
        text = re.sub(r'\s+', ' ', text).strip()
        return text


# Global classifier instance
intent_classifier = IntentClassifier()
