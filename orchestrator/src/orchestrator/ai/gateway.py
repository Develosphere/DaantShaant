"""The shared, provider-neutral DaantShaant AI gateway.

``AIGateway`` is the single seam between business/agent modules and concrete
AI provider adapters. It:

- accepts a primary provider and an optional fallback provider,
- routes text / vision / structured requests to the matching adapter method,
- enforces a request timeout,
- normalizes every response into :class:`AIResult` (provider, model,
  latency, ``fallback_used``), and
- performs *controlled* fallback only for technical provider failures.

It contains **no** provider SDK logic, dental rules, RAG, LangGraph, or
FastAPI concerns. Provider adapters are added in later 2A.x phases.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from orchestrator.ai.base import AIProvider
from orchestrator.ai.exceptions import (
    AIGatewayError,
    AllProvidersFailedError,
    ProviderConfigurationError,
    ProviderInternalError,
    ProviderTimeoutError,
)
from orchestrator.ai.schemas import AIResult, StructuredRequest, TextRequest, VisionRequest

logger = logging.getLogger(__name__)

DEFAULT_AI_TIMEOUT_SECONDS = 60.0


class AIGateway:
    """Route AI requests through a primary provider with optional fallback."""

    def __init__(
        self,
        primary: AIProvider,
        fallback: AIProvider | None = None,
        *,
        timeout_seconds: float = DEFAULT_AI_TIMEOUT_SECONDS,
    ) -> None:
        if primary is None:
            raise ProviderConfigurationError("A primary AI provider is required")
        if timeout_seconds is None or timeout_seconds <= 0:
            raise ProviderConfigurationError("timeout_seconds must be a positive number")
        self.primary = primary
        self.fallback = fallback
        self.timeout_seconds = float(timeout_seconds)

    # ------------------------------------------------------------------
    # Public routing API
    # ------------------------------------------------------------------
    async def generate_text(self, request: TextRequest) -> AIResult:
        return await self._run("generate_text", request)

    async def generate_vision(self, request: VisionRequest) -> AIResult:
        return await self._run("generate_vision", request)

    async def generate_structured(self, request: StructuredRequest) -> AIResult:
        return await self._run("generate_structured", request)

    # ------------------------------------------------------------------
    # Routing + fallback policy
    # ------------------------------------------------------------------
    async def _run(self, method: str, request: TextRequest | VisionRequest | StructuredRequest) -> AIResult:
        started = time.perf_counter()
        try:
            result = await self._call(self.primary, method, request)
            return self._normalize(result, self.primary, started, fallback_used=False)
        except AIGatewayError as exc:
            # Configuration, request-construction, and schema/programming
            # errors must NEVER be masked by a silent fallback.
            if not exc.fallback_eligible:
                raise
            if self.fallback is None:
                raise
            primary_error = exc
            logger.warning(
                "Primary AI provider %s failed (%s); trying fallback %s",
                self.primary.name,
                type(exc).__name__,
                self.fallback.name,
            )

        # Fallback attempt.
        started = time.perf_counter()
        try:
            result = await self._call(self.fallback, method, request)
            return self._normalize(result, self.fallback, started, fallback_used=True)
        except AIGatewayError as exc:
            if not exc.fallback_eligible:
                raise
            raise AllProvidersFailedError(
                f"Both AI providers failed: primary={self.primary.name} "
                f"({type(primary_error).__name__}), fallback={self.fallback.name} "
                f"({type(exc).__name__})",
                provider_errors={
                    self.primary.name: primary_error,
                    self.fallback.name: exc,
                },
            ) from exc

    async def _call(self, provider: AIProvider, method: str, request) -> AIResult:
        """Invoke one adapter method, converting timeouts to typed errors.

        Adapters are expected to raise :class:`AIGatewayError` subclasses for
        known conditions.  Unexpected exceptions (``TypeError``, ``ValueError``,
        etc.) are wrapped in a NON-fallback-eligible
        :class:`ProviderInternalError` so programming bugs are never silently
        masked by a provider switch.
        """
        handler: Callable[[object], Awaitable[AIResult]] = getattr(provider, method)
        try:
            return await asyncio.wait_for(handler(request), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise ProviderTimeoutError(
                f"{provider.name} timed out after {self.timeout_seconds}s"
            ) from exc
        except AIGatewayError:
            raise
        except Exception as exc:  # noqa: BLE001 - safety net around adapters
            raise ProviderInternalError(
                f"{provider.name} raised unexpected {type(exc).__name__}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Result normalization
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(
        result: AIResult,
        provider: AIProvider,
        started: float,
        *,
        fallback_used: bool,
    ) -> AIResult:
        latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        model = result.model or provider.default_model
        return result.model_copy(
            update={
                "provider": provider.name,
                "model": model,
                "latency_ms": latency_ms,
                "fallback_used": fallback_used,
            }
        )
