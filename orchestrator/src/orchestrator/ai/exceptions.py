"""Gateway-level exceptions for the shared DaantShaant AI Gateway.

Small hierarchy split by fallback policy:

- ``ProviderTechnicalError`` subclasses are TECHNICAL runtime failures
  (timeout, connection, 429, 5xx, malformed provider responses) and are
  eligible for fallback to a secondary provider.
- ``ProviderConfigurationError`` / ``InvalidProviderRequestError`` /
  ``StructuredOutputError`` are local or programming errors and must NEVER
  trigger silent fallback.

Provider adapters raise these exceptions; the gateway interprets them.
"""

from __future__ import annotations


class AIGatewayError(Exception):
    """Base class for all shared AI gateway errors."""

    fallback_eligible = False


class ProviderConfigurationError(AIGatewayError):
    """Provider is misconfigured locally (missing key, base URL, model)."""


class InvalidProviderRequestError(AIGatewayError):
    """The caller built an invalid gateway request (programming error)."""


class ProviderTechnicalError(AIGatewayError):
    """Runtime provider failure that is eligible for fallback."""

    fallback_eligible = True


class ProviderUnavailableError(ProviderTechnicalError):
    """Provider unreachable or temporarily unavailable (connection failure)."""


class ProviderTimeoutError(ProviderTechnicalError):
    """Provider did not respond within the configured timeout."""


class ProviderRateLimitError(ProviderTechnicalError):
    """Provider rejected the request due to rate limiting (HTTP 429)."""


class ProviderServerError(ProviderTechnicalError):
    """Provider failed on its side (HTTP 5xx)."""


class InvalidProviderResponseError(ProviderTechnicalError):
    """Provider returned a malformed or unusable response."""


class ProviderInternalError(AIGatewayError):
    """Unexpected internal / programming error.  NOT fallback-eligible."""


class StructuredOutputError(AIGatewayError):
    """Structured JSON output could not be parsed or validated."""


class AllProvidersFailedError(AIGatewayError):
    """Primary and configured fallback provider both failed technically."""

    def __init__(
        self,
        message: str,
        provider_errors: dict[str, Exception] | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_errors: dict[str, Exception] = provider_errors or {}
