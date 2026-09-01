"""Normalized request and result schemas for the shared AI gateway.

These are provider-neutral: business modules build a request and receive an
``AIResult``. No provider SDK object is ever exposed to callers.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single conversation turn understood by any provider."""

    role: str = Field(..., description="'system' | 'user' | 'assistant'")
    content: str


class UsageMetadata(BaseModel):
    """Best-effort token accounting, normalized across providers."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class TextRequest(BaseModel):
    """A plain text-generation request."""

    prompt: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None
    model: str | None = None
    """Optional explicit model id; providers fall back to their configured default."""


class VisionRequest(BaseModel):
    """An image + text generation request.

    ``image_base64`` is raw base64 (no ``data:`` prefix). Providers adapt it to
    their own transport format.
    """

    prompt: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    image_base64: str
    content_type: str = "image/jpeg"
    temperature: float | None = None
    max_tokens: int | None = None
    model: str | None = None
    """Optional explicit model id; providers fall back to their configured default."""


class StructuredRequest(BaseModel):
    """A request that must yield JSON matching ``json_schema``.

    ``image_base64`` is optional so structured calls can be text-only or
    multimodal depending on the provider's capability.
    """

    prompt: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    json_schema: dict[str, Any]
    image_base64: str | None = None
    content_type: str = "image/jpeg"
    temperature: float | None = None
    max_tokens: int | None = None
    model: str | None = None
    """Optional explicit model id; providers fall back to their configured default."""


class AIResult(BaseModel):
    """Normalized provider response returned to every business module."""

    content: str
    provider: str = ""
    model: str = ""
    usage: UsageMetadata | None = None
    latency_ms: float = 0.0
    finish_reason: str | None = None
    raw_metadata: dict[str, Any] | None = None
    fallback_used: bool = False
    data: dict[str, Any] | None = None
    """Parsed JSON payload for structured requests; ``None`` otherwise."""
