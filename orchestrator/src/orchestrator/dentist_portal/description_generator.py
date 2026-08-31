"""AI description generator for dental products using OpenRouter (consistent with existing stack)."""

import json
import logging
from orchestrator.openrouter_client import openrouter_client

logger = logging.getLogger(__name__)

DESCRIPTION_SYSTEM = """You are a dental product description expert.
Given a product name, category, and a dentist's short note, generate:
1. A patient-friendly description (2-3 sentences) explaining what dental problems this product solves
2. A JSON list of specific dental problems/issues this product addresses

Return ONLY valid JSON — no markdown, no extra text:
{
  "ai_description": "...",
  "problems_solved": ["issue1", "issue2"]
}"""


async def generate_product_description(name: str, raw_desc: str, category: str) -> dict:
    """Generate AI description and problems_solved list for a product."""
    user_content = f"Product: {name}\nCategory: {category}\nDentist note: {raw_desc}"
    try:
        response = await openrouter_client.generate_chat_response(
            system_prompt=DESCRIPTION_SYSTEM,
            user_message=user_content,
            temperature=0.3,
            max_tokens=400,
        )
        text = response.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as exc:
        logger.warning("[PORTAL] AI description failed: %s — using fallback", exc)
        return {
            "ai_description": f"{name} helps address common dental issues. {raw_desc}",
            "problems_solved": [category],
        }
