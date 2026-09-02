"""Clinical-vision provider error hierarchy for the Teeth Analyzer (Phase 2C).

This is a small, SERVICE-LOCAL mirror of the orchestrator AI gateway policy. It
is deliberately self-contained: the Teeth Analyzer never imports the
orchestrator and never calls it over HTTP (that would create a circular
dependency), so the same locked fallback policy is expressed here.

Fallback policy:

- ``ProviderTechnicalError`` subclasses are TECHNICAL runtime failures
  (timeout, connection, 429, 5xx, malformed provider response) and ARE
  eligible for fallback from Qwen (primary) to Gemini (fallback).
- ``ProviderConfigurationError`` / ``ProviderInternalError`` are local or
  programming errors and must NEVER trigger silent fallback.

Neither the API key nor the image base64 ever appears in these messages.
"""

from __future__ import annotations


class ClinicalVisionError(Exception):
    """Base class for all clinical-vision provider errors."""

    fallback_eligible = False


class ProviderConfigurationError(ClinicalVisionError):
    """Provider is misconfigured locally (missing key/base URL/model) or auth
    was rejected (HTTP 400/401/403). NOT fallback-eligible."""


class ProviderInternalError(ClinicalVisionError):
    """Unexpected internal / programming error. NOT fallback-eligible."""


class ProviderTechnicalError(ClinicalVisionError):
    """Runtime provider failure that IS eligible for fallback."""

    fallback_eligible = True


class ProviderUnavailableError(ProviderTechnicalError):
    """Provider unreachable (connection/DNS/transport failure)."""


class ProviderTimeoutError(ProviderTechnicalError):
    """Provider did not respond within the configured timeout."""


class ProviderRateLimitError(ProviderTechnicalError):
    """Provider rejected the request due to rate limiting (HTTP 429)."""


class ProviderServerError(ProviderTechnicalError):
    """Provider failed on its side (HTTP 5xx)."""


class InvalidProviderResponseError(ProviderTechnicalError):
    """Provider returned a malformed or unusable HTTP response envelope."""


class AllProvidersFailedError(ClinicalVisionError):
    """Qwen (primary) and Gemini (fallback) both failed technically."""

    def __init__(
        self,
        message: str,
        provider_errors: dict[str, Exception] | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_errors: dict[str, Exception] = provider_errors or {}


__all__ = [
    "ClinicalVisionError",
    "ProviderConfigurationError",
    "ProviderInternalError",
    "ProviderTechnicalError",
    "ProviderUnavailableError",
    "ProviderTimeoutError",
    "ProviderRateLimitError",
    "ProviderServerError",
    "InvalidProviderResponseError",
    "AllProvidersFailedError",
]
