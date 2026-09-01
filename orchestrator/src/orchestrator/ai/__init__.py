"""Shared, provider-neutral DaantShaant AI Gateway core (Phases 2A.1-2A.4).

Public surface: the gateway, the production composition factory, the provider
contract, normalized schemas, and gateway exceptions. Composing providers is
always explicit/lazy - importing this package never performs an AI call.
"""

from orchestrator.ai.base import AIProvider
from orchestrator.ai.exceptions import (
    AIGatewayError,
    AllProvidersFailedError,
    InvalidProviderRequestError,
    InvalidProviderResponseError,
    ProviderConfigurationError,
    ProviderInternalError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTechnicalError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    StructuredOutputError,
)
from orchestrator.ai.gateway import DEFAULT_AI_TIMEOUT_SECONDS, AIGateway
from orchestrator.ai.gemini import GeminiProvider
from orchestrator.ai.qwen import QwenProvider
from orchestrator.ai.factory import SUPPORTED_AI_PROVIDERS, create_ai_gateway, get_ai_gateway
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
    "ProviderInternalError",
    "StructuredOutputError",
    "AllProvidersFailedError",
    "QwenProvider",
    "GeminiProvider",
    "SUPPORTED_AI_PROVIDERS",
    "create_ai_gateway",
    "get_ai_gateway",
]
