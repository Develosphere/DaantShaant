"""Shared, provider-neutral DaantShaant AI Gateway core (Phase 2A.1).

Public surface: the gateway, the provider contract, normalized schemas, and
gateway exceptions. No concrete provider is wired in yet; adapters arrive in
later 2A.x phases. No live external AI calls are made from this package.
"""

from orchestrator.ai.base import AIProvider
from orchestrator.ai.exceptions import (
    AIGatewayError,
    AllProvidersFailedError,
    InvalidProviderRequestError,
    InvalidProviderResponseError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTechnicalError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    StructuredOutputError,
)
from orchestrator.ai.gateway import DEFAULT_AI_TIMEOUT_SECONDS, AIGateway
from orchestrator.ai.schemas import (
    AIResult,
    ChatMessage,
    StructuredRequest,
    TextRequest,
    UsageMetadata,
    VisionRequest,
)

__all__ = [
    "AIGateway",
    "AIProvider",
    "AIResult",
    "ChatMessage",
    "TextRequest",
    "VisionRequest",
    "StructuredRequest",
    "UsageMetadata",
    "DEFAULT_AI_TIMEOUT_SECONDS",
    "AIGatewayError",
    "ProviderTechnicalError",
    "ProviderUnavailableError",
    "ProviderTimeoutError",
    "ProviderRateLimitError",
    "ProviderServerError",
    "InvalidProviderResponseError",
    "ProviderConfigurationError",
    "InvalidProviderRequestError",
    "StructuredOutputError",
    "AllProvidersFailedError",
]
