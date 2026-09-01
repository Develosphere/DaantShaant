"""Multi-provider LLM failover: OpenRouter → Gemini → Deterministic fallback.

Provides a single generate() method that tries providers in order.
Failures (429, 404, timeout, malformed, empty) cascade silently.
The user never sees an error — they always get a useful dental answer.
"""

import logging
import re
from typing import Optional

import httpx
import os
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deterministic dental fallback responses (issue-aware)
# ---------------------------------------------------------------------------

DENTAL_FALLBACKS = {
    "bleeding gums": (
        "Gums often bleed because plaque irritates the gum tissue. "
        "Gentle brushing with a soft-bristled brush, daily flossing, and "
        "warm saltwater rinses usually help reduce the inflammation over time."
    ),
    "toothache": (
        "A toothache can happen because of cavities, sensitivity, gum "
        "inflammation, or even a small crack in the tooth. Over-the-counter "
        "pain relief and a warm saltwater rinse can help for now, but if it "
        "persists or worsens, a dental check-up is recommended."
    ),
    "sensitivity": (
        "Tooth sensitivity is usually caused by thinning enamel or receding "
        "gums that expose the inner layer of the tooth. Using a sensitivity "
        "toothpaste and avoiding very hot or cold foods can help. If it "
        "keeps happening, a dentist can check for cracks or decay."
    ),
    "tartar/plaque buildup": (
        "Hard yellow buildup near the gums is often tartar — hardened plaque "
        "that can't usually be removed by brushing alone. A professional "
        "dental cleaning is the best way to get rid of it and prevent gum "
        "irritation."
    ),
    "discolored teeth": (
        "Teeth can become yellow or stained from coffee, tea, smoking, or "
        "just natural aging of the enamel. Regular brushing with a whitening "
        "toothpaste helps with surface stains. For deeper discoloration, "
        "a dentist can suggest safe whitening options."
    ),
    "cavity/tooth decay": (
        "Cavities form when bacteria in your mouth produce acid that eats "
        "into the tooth enamel. Small cavities might not hurt at first, "
        "but they can grow if left untreated. A dentist can fill them before "
        "they get worse."
    ),
    "bad breath": (
        "Bad breath is often caused by bacteria on the tongue, food stuck "
        "between teeth, or gum issues. Brushing your tongue, flossing daily, "
        "and staying hydrated usually helps. If it sticks around, it could "
        "be worth a dental check-up."
    ),
    "swollen gums": (
        "Swollen gums are usually a sign of inflammation from plaque buildup "
        "or the early stages of gum disease. Gentle brushing along the gum "
        "line, flossing, and saltwater rinses can help bring the swelling "
        "down over time."
    ),
    "loose tooth": (
        "A loose tooth in adults is usually caused by gum disease that has "
        "weakened the supporting bone, or sometimes by injury. This is "
        "definitely worth seeing a dentist about as soon as possible to "
        "prevent further damage."
    ),
    "gum pain": (
        "Sore gums can happen because of irritation from plaque, brushing "
        "too hard, or the start of gum disease. Try switching to a "
        "soft-bristled brush and doing warm saltwater rinses. If it "
        "continues for more than a week, check in with a dentist."
    ),
    "wisdom tooth": (
        "Wisdom teeth can cause pain and swelling when they're coming in, "
        "especially if there isn't enough room or they're growing at an "
        "angle. Rinsing with warm saltwater helps with discomfort. A dentist "
        "can take an X-ray to see what's going on."
    ),
    "broken tooth": (
        "A broken or chipped tooth can be caused by biting something hard, "
        "an injury, or weakened enamel. Avoid chewing on that side and see "
        "a dentist as soon as you can — they can bond, cap, or fill the "
        "tooth depending on the damage."
    ),
    "jaw pain": (
        "Jaw pain can come from teeth grinding, TMJ issues, or tension in "
        "the jaw muscles. Avoiding hard or chewy foods and applying a warm "
        "compress can help. If it persists or your jaw clicks or locks, "
        "a dentist or TMJ specialist can help."
    ),
    "mouth ulcer": (
        "Mouth ulcers are usually caused by minor irritation, stress, or "
        "certain foods. They typically heal on their own within a week or "
        "two. Rinsing with warm saltwater or using an over-the-counter "
        "gel can help with the discomfort."
    ),
    "dry mouth": (
        "Dry mouth happens when your salivary glands don't produce enough "
        "saliva, which can increase the risk of cavities. Staying hydrated, "
        "chewing sugar-free gum, and avoiding caffeine and alcohol can help. "
        "If it continues, mention it to your dentist."
    ),
}

# Generic dental fallback when no specific issue is detected
GENERIC_DENTAL_FALLBACK = (
    "Good oral health starts with brushing twice a day with fluoride "
    "toothpaste, flossing daily, and visiting your dentist for regular "
    "check-ups. If you're experiencing any specific dental issue, feel "
    "free to describe it and I can give you more targeted advice."
)


def get_deterministic_fallback(user_message: str, active_issue: Optional[str] = None) -> str:
    """Return a deterministic, issue-aware dental response.
    
    Tries to match the active conversation issue first, then scans
    the user message for keywords.
    """
    # 1. Use active issue from conversation state if available
    if active_issue and active_issue in DENTAL_FALLBACKS:
        return DENTAL_FALLBACKS[active_issue]

    # 2. Scan user message for issue keywords
    text_lower = user_message.lower()
    keyword_map = {
        "bleed": "bleeding gums",
        "bleeding": "bleeding gums",
        "blood": "bleeding gums",
        "toothache": "toothache",
        "tooth hurt": "toothache",
        "tooth pain": "toothache",
        "teeth hurt": "toothache",
        "teeth pain": "toothache",
        "sensitive": "sensitivity",
        "sensitivity": "sensitivity",
        "tartar": "tartar/plaque buildup",
        "plaque": "tartar/plaque buildup",
        "yellow stuff": "tartar/plaque buildup",
        "yellow teeth": "discolored teeth",
        "stain": "discolored teeth",
        "cavity": "cavity/tooth decay",
        "decay": "cavity/tooth decay",
        "bad breath": "bad breath",
        "swollen gum": "swollen gums",
        "gum swell": "swollen gums",
        "loose tooth": "loose tooth",
        "gum hurt": "gum pain",
        "gum pain": "gum pain",
        "sore gum": "gum pain",
        "wisdom": "wisdom tooth",
        "broken tooth": "broken tooth",
        "chipped": "broken tooth",
        "cracked tooth": "broken tooth",
        "jaw": "jaw pain",
        "tmj": "jaw pain",
        "ulcer": "mouth ulcer",
        "canker": "mouth ulcer",
        "dry mouth": "dry mouth",
    }

    for keyword, issue_key in keyword_map.items():
        if keyword in text_lower:
            return DENTAL_FALLBACKS[issue_key]

    return GENERIC_DENTAL_FALLBACK


# ---------------------------------------------------------------------------
# Helper to load env vars
# ---------------------------------------------------------------------------

def _load_env_var(key: str, default: Optional[str] = None) -> Optional[str]:
    """Load environment variable, checking .env file if not in os.environ."""
    value = os.getenv(key)
    if value:
        return value

    try:
        env_file = Path(__file__).parent.parent.parent.parent / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        env_key, env_value = line.split('=', 1)
                        if env_key.strip() == key:
                            return env_value.strip()
    except Exception as e:
        logger.warning(f"Failed to load {key} from .env: {e}")

    return default


# ---------------------------------------------------------------------------
# Gemini Flash Lite client (secondary provider)
# ---------------------------------------------------------------------------

class _GeminiClient:
    """Minimal Gemini Flash Lite client for failover."""

    def __init__(self):
        self.api_key = _load_env_var("TEETH_ANALYZER_GEMINI_API_KEY")
        self.model = _load_env_var("TEETH_ANALYZER_GEMINI_MODEL", "gemini-flash-lite-latest")
        # Use Gemini v1beta generateContent endpoint
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        if not self.api_key:
            logger.warning("[GEMINI] No API key found — Gemini failover disabled")

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = 600,
    ) -> str:
        """Generate a response via Gemini Flash Lite.
        
        Raises RuntimeError on any failure.
        """
        if not self.api_key:
            raise RuntimeError("Gemini API key not configured")

        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\n{user_message}"}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(url, json=payload)

                if resp.status_code != 200:
                    raise RuntimeError(
                        f"Gemini API error: {resp.status_code} - {resp.text[:200]}"
                    )

                data = resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    raise RuntimeError("Gemini returned no candidates")

                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    raise RuntimeError("Gemini returned empty parts")

                text = parts[0].get("text", "").strip()
                if not text:
                    raise RuntimeError("Gemini returned empty text")

                logger.info(f"[GEMINI] Response generated successfully ({len(text)} chars)")
                return text

        except httpx.TimeoutException as e:
            raise RuntimeError(f"Gemini timeout: {e}") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"Gemini request error: {e}") from e


# ---------------------------------------------------------------------------
# Multi-provider LLM client
# ---------------------------------------------------------------------------

class LLMProvider:
    """Failover chain: OpenRouter → Gemini Flash Lite → Deterministic.
    
    Every generate() call is guaranteed to return a non-empty string.
    The user never sees an error or empty response.
    """

    def __init__(self):
        # Import here to avoid circular deps — OpenRouterClient is already instantiated globally
        from orchestrator.openrouter_client import openrouter_client
        self.openrouter = openrouter_client
        self.gemini = _GeminiClient()

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = 600,
        conversation_context: Optional[list[dict]] = None,
        # Context for deterministic fallback
        user_raw_message: str = "",
        active_issue: Optional[str] = None,
    ) -> str:
        """Try providers in order; always return a useful response.
        
        Args:
            system_prompt: System instructions.
            user_message: The prompt to send (may be enhanced with RAG).
            temperature: Sampling temperature.
            max_tokens: Max response tokens.
            conversation_context: Optional message history for OpenRouter.
            user_raw_message: The original user text (for keyword fallback).
            active_issue: Current dental issue from conversation state.
            
        Returns:
            Non-empty response string.  Never raises to the caller.
        """
        # --- Provider 1: OpenRouter ---
        try:
            response = await self.openrouter.generate_chat_response(
                system_prompt=system_prompt,
                user_message=user_message,
                conversation_context=conversation_context,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if response and response.strip():
                logger.info("[LLM_PROVIDER] OpenRouter succeeded")
                return response.strip()
            else:
                logger.warning("[LLM_PROVIDER] OpenRouter returned empty — trying Gemini")
        except Exception as e:
            logger.warning(f"[LLM_PROVIDER] OpenRouter failed: {e} — trying Gemini")

        # --- Provider 2: Gemini Flash Lite ---
        try:
            response = await self.gemini.generate(
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if response and response.strip():
                logger.info("[LLM_PROVIDER] Gemini succeeded")
                return response.strip()
            else:
                logger.warning("[LLM_PROVIDER] Gemini returned empty — using fallback")
        except Exception as e:
            logger.warning(f"[LLM_PROVIDER] Gemini failed: {e} — using deterministic fallback")

        # --- Provider 3: Deterministic dental fallback ---
        logger.info("[LLM_PROVIDER] Using deterministic dental fallback")
        return get_deterministic_fallback(user_raw_message or user_message, active_issue)


# Global instance
llm_provider = LLMProvider()
