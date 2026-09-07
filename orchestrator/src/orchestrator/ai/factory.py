"""Production composition of the shared DaantShaant AI Gateway (Phase 2A.4).

This is the single place where the locked provider policy is turned into a
concrete :class:`~orchestrator.ai.gateway.AIGateway` instance:

```text
create_ai_gateway(settings)
    -> PRIMARY  = QwenProvider   (PRIMARY_AI_PROVIDER=qwen)
    -> FALLBACK = GeminiProvider (FALLBACK_AI_PROVIDER=gemini)
```

Design rules:

- **No network at import time.** Importing this module performs no HTTP call
  and constructs no provider. Even the adapter modules themselves are imported
  lazily *inside* the builder functions, so cold-start cost stays where it
  belongs (first real gateway use) instead of application import.
- **No hidden provider substitution.** An unknown or missing
  ``PRIMARY_AI_PROVIDER`` / ``FALLBACK_AI_PROVIDER`` value raises
  :class:`ProviderConfigurationError`; the factory never quietly picks a
  different provider.
- **Callers stay provider-neutral.** Business modules depend only on
  :class:`AIGateway` and the normalized request/result schemas.

:meth:`create_ai_gateway` builds a fresh gateway (used by tests and any caller
that wants explicit composition); :func:`get_ai_gateway` returns the lazily
built process-wide instance used by application code.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from orchestrator.ai.base import AIProvider
from orchestrator.ai.exceptions import ProviderConfigurationError
from orchestrator.ai.gateway import DEFAULT_AI_TIMEOUT_SECONDS, AIGateway

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps runtime import light
    from orchestrator.config import AISettings

logger = logging.getLogger(__name__)

#: Provider names supported for production composition in Phase 2A.4.
SUPPORTED_AI_PROVIDERS: tuple[str, ...] = ("qwen", "gemini")

_EMPTY_FALLBACKS = {"", "none", "null", "off"}


def _build_qwen(settings: "AISettings") -> AIProvider:
    # Local import: keeps `import orchestrator.ai.factory` free of httpx /
    # jsonschema import cost until a gateway is actually composed.
    from orchestrator.ai.qwen import QwenProvider

    return QwenProvider(settings=settings)


def _build_gemini(settings: "AISettings") -> AIProvider:
    from orchestrator.ai.gemini import GeminiProvider

    return GeminiProvider(settings=settings)


_PROVIDER_BUILDERS: dict[str, Callable[["AISettings"], AIProvider]] = {
    "qwen": _build_qwen,
    "gemini": _build_gemini,
}


def _normalize_provider_name(raw: object, env_var: str, *, allow_empty: bool) -> str | None:
    """Validate a configured provider name without substituting anything."""
    name = (str(raw).strip().lower() if raw is not None else "")
    if not name or name in _EMPTY_FALLBACKS:
        if allow_empty:
            return None
        raise ProviderConfigurationError(
            f"{env_var} is required. Supported providers: {', '.join(SUPPORTED_AI_PROVIDERS)}."
        )
    if name not in _PROVIDER_BUILDERS:
        raise ProviderConfigurationError(
            f"{env_var}={name!r} is not a supported AI provider. "
            f"Supported providers: {', '.join(SUPPORTED_AI_PROVIDERS)}."
        )
    return name


def _build(name: str, settings: "AISettings") -> AIProvider:
    provider = _PROVIDER_BUILDERS[name](settings)
    logger.info("AI gateway provider composed: %s (default_model=%s)", provider.name, provider.default_model)
    return provider


def create_ai_gateway(settings: "AISettings | None" = None) -> AIGateway:
    """Compose the production gateway: Qwen primary + Gemini technical fallback.

    Reads ``PRIMARY_AI_PROVIDER`` / ``FALLBACK_AI_PROVIDER`` /
    ``AI_REQUEST_TIMEOUT_SECONDS`` from :class:`AISettings` (or the passed
    settings object). Raises :class:`ProviderConfigurationError` on unknown
    provider names or on a provider whose own required configuration is
    missing; it never silently substitutes another provider.
    """
    # Imported lazily so this module stays cheap to import.
    from orchestrator.config import settings as app_settings

    cfg: "AISettings" = settings if settings is not None else app_settings

    primary_name = _normalize_provider_name(
        getattr(cfg, "primary_ai_provider", ""), "PRIMARY_AI_PROVIDER", allow_empty=False
    )
    fallback_name = _normalize_provider_name(
        getattr(cfg, "fallback_ai_provider", ""), "FALLBACK_AI_PROVIDER", allow_empty=True
    )
    if fallback_name == primary_name:
        raise ProviderConfigurationError(
            "PRIMARY_AI_PROVIDER and FALLBACK_AI_PROVIDER must differ "
            f"(both are {primary_name!r}). Leave FALLBACK_AI_PROVIDER empty to run without fallback."
        )

    primary = _build(primary_name, cfg)  # type: ignore[arg-type]
    fallback = _build(fallback_name, cfg) if fallback_name else None
    timeout = getattr(cfg, "ai_request_timeout_seconds", None) or DEFAULT_AI_TIMEOUT_SECONDS

    gateway = AIGateway(primary=primary, fallback=fallback, timeout_seconds=timeout)
    logger.info(
        "AI gateway ready: primary=%s fallback=%s timeout_s=%s",
        primary.name,
        fallback.name if fallback else "none",
        gateway.timeout_seconds,
    )
    return gateway


# ---------------------------------------------------------------------------
# Chat-Specific AI Gateway (Phase 12D)
# ---------------------------------------------------------------------------

def _build_chat_qwen(settings: "AISettings") -> AIProvider:
    from orchestrator.ai.qwen import QwenProvider

    chat_model = getattr(settings, "chat_qwen_model", "qwen3.7-flash")
    enable_thinking = getattr(settings, "chat_qwen_enable_thinking", False)
    return QwenProvider(
        settings=settings,
        chat_model=chat_model,
        default_model=chat_model,
        enable_thinking=enable_thinking,
    )


def _build_chat_gemini(settings: "AISettings") -> AIProvider:
    from orchestrator.ai.gemini import GeminiProvider

    chat_model = getattr(settings, "chat_gemini_model", "gemini-flash-lite-latest")
    return GeminiProvider(settings=settings, default_model=chat_model)


_CHAT_PROVIDER_BUILDERS: dict[str, Callable[["AISettings"], AIProvider]] = {
    "qwen": _build_chat_qwen,
    "gemini": _build_chat_gemini,
}


def create_chat_ai_gateway(settings: "AISettings | None" = None) -> AIGateway:
    """Compose the chat-specific AI gateway (Phase 12D).

    Reads ``CHAT_LLM_PROVIDER`` / ``CHAT_FALLBACK_PROVIDER`` from settings.
    Configures Qwen with ``CHAT_QWEN_MODEL`` and ``CHAT_QWEN_ENABLE_THINKING``.
    Configures Gemini with ``CHAT_GEMINI_MODEL``.
    Enforces chat latency timeouts.
    """
    from orchestrator.config import settings as app_settings

    cfg: "AISettings" = settings if settings is not None else app_settings

    primary_name = _normalize_provider_name(
        getattr(cfg, "chat_llm_provider", "qwen"), "CHAT_LLM_PROVIDER", allow_empty=False
    )
    fallback_name = _normalize_provider_name(
        getattr(cfg, "chat_fallback_provider", "gemini"), "CHAT_FALLBACK_PROVIDER", allow_empty=True
    )
    if fallback_name == primary_name:
        raise ProviderConfigurationError(
            "CHAT_LLM_PROVIDER and CHAT_FALLBACK_PROVIDER must differ "
            f"(both are {primary_name!r}). Leave CHAT_FALLBACK_PROVIDER empty to run without fallback."
        )

    primary = _CHAT_PROVIDER_BUILDERS[primary_name](cfg)
    fallback = _CHAT_PROVIDER_BUILDERS[fallback_name](cfg) if fallback_name else None
    timeout = getattr(cfg, "chat_qwen_timeout_seconds", 12.0)

    gateway = AIGateway(primary=primary, fallback=fallback, timeout_seconds=timeout)
    logger.info(
        "Chat AI gateway ready: primary=%s (%s) fallback=%s timeout_s=%s",
        primary.name,
        primary.default_model,
        f"{fallback.name} ({fallback.default_model})" if fallback else "none",
        gateway.timeout_seconds,
    )
    return gateway


# ---------------------------------------------------------------------------
# Lazy process-wide instances
# ---------------------------------------------------------------------------
_gateway: AIGateway | None = None
_chat_gateway: AIGateway | None = None


def get_ai_gateway() -> AIGateway:
    """Return the shared gateway, composing it on first use (never at import)."""
    global _gateway
    if _gateway is None:
        _gateway = create_ai_gateway()
    return _gateway


def get_chat_ai_gateway() -> AIGateway:
    """Return the shared chat gateway, composing it on first use."""
    global _chat_gateway
    if _chat_gateway is None:
        _chat_gateway = create_chat_ai_gateway()
    return _chat_gateway


async def close_ai_gateway() -> None:
    """Cleanly close persistent provider resources on shutdown."""
    global _gateway, _chat_gateway
    if _gateway is not None:
        await _gateway.aclose()
        _gateway = None
    if _chat_gateway is not None:
        await _chat_gateway.aclose()
        _chat_gateway = None


__all__ = [
    "SUPPORTED_AI_PROVIDERS",
    "create_ai_gateway",
    "get_ai_gateway",
    "create_chat_ai_gateway",
    "get_chat_ai_gateway",
    "close_ai_gateway",
]
