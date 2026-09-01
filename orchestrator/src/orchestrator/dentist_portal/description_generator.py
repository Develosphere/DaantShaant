"""AI description generator for dental products.

Uses the shared DaantShaant AI gateway (Phase 2A.5a): Qwen primary with a
Gemini technical fallback. This module never imports a provider adapter
directly or talks to OpenRouter.
"""

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps runtime import cheap
    from orchestrator.ai.gateway import AIGateway

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

# Module-level gateway handle; injected for tests, resolved lazily for prod.
_gateway: "AIGateway | None" = None


def _get_gateway() -> "AIGateway":
    """Return the shared gateway, composing it on first use (never at import)."""
    global _gateway
    if _gateway is None:
        from orchestrator.ai.factory import get_ai_gateway

        _gateway = get_ai_gateway()
    return _gateway


async def generate_product_description(
    name: str,
    raw_desc: str,
    category: str,
    *,
    gateway: "AIGateway | None" = None,
) -> dict:
    """Generate AI description and problems_solved list for a product.

    The model is intentionally not set on the request: each provider resolves
    its own configured model (``QWEN_CHAT_MODEL`` primary, ``GEMINI_MODEL``
    fallback), keeping this caller provider-neutral.

    Configuration and programming errors propagate untouched. A full
    double-provider technical failure degrades to the existing deterministic
    fallback so the dentist still gets a usable description.
    """
    from orchestrator.ai.exceptions import AllProvidersFailedError
    from orchestrator.ai.schemas import ChatMessage, TextRequest

    gw = gateway or _get_gateway()
    user_content = f"Product: {name}\nCategory: {category}\nDentist note: {raw_desc}"

    request = TextRequest(
        messages=[
            ChatMessage(role="system", content=DESCRIPTION_SYSTEM),
            ChatMessage(role="user", content=user_content),
        ],
        temperature=0.3,
        max_tokens=400,
    )

    try:
        result = await gw.generate_text(request)
    except AllProvidersFailedError as exc:
        logger.warning(
            "[PORTAL] status=all_providers_failed reason=%s",
            type(exc).__name__,
        )
        return {
            "ai_description": f"{name} helps address common dental issues. {raw_desc}",
            "problems_solved": [category],
        }

    text = (result.content or "").strip()
    logger.info(
        "[PORTAL] status=%s provider=%s model=%s latency_ms=%s fallback_used=%s",
        "ok" if text else "empty",
        result.provider,
        result.model,
        result.latency_ms,
        result.fallback_used,
    )

    if not text:
        return {
            "ai_description": f"{name} helps address common dental issues. {raw_desc}",
            "problems_solved": [category],
        }

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("[PORTAL] AI description JSON parse failed: %s — using fallback", exc)
        return {
            "ai_description": f"{name} helps address common dental issues. {raw_desc}",
            "problems_solved": [category],
        }
