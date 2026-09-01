"""Provider-neutral abstract interface for DaantShaant AI providers.

Concrete adapters (Qwen, Gemini, ...) implement ``AIProvider`` in later
2A.x phases. The gateway and business modules depend only on this contract,
never on a provider SDK. The interface intentionally contains no dental,
RAG, LangGraph, or FastAPI concerns.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from orchestrator.ai.schemas import (
    AIResult,
    StructuredRequest,
    TextRequest,
    VisionRequest,
)


class AIProvider(ABC):
    """Async contract every AI provider adapter must satisfy."""

    #: Short stable identifier, e.g. ``"qwen"`` / ``"gemini"``.
    name: str = "unknown"
    #: Default model id used when a request does not override it.
    default_model: str = ""

    @abstractmethod
    async def generate_text(self, request: TextRequest) -> AIResult:
        """Generate a text completion from a text request."""

    @abstractmethod
    async def generate_vision(self, request: VisionRequest) -> AIResult:
        """Generate a completion from an image plus text request."""

    @abstractmethod
    async def generate_structured(self, request: StructuredRequest) -> AIResult:
        """Generate a completion whose ``data`` field holds validated JSON.

        Implementations must populate ``AIResult.data`` with the parsed JSON
        object and raise ``StructuredOutputError`` when the provider response
        cannot be parsed or validated against ``request.json_schema``.
        """
