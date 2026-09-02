"""Qwen (Alibaba Model Studio) clinical-vision backend - PRIMARY (Phase 2C).

OpenAI-compatible ``/chat/completions`` multimodal call over plain async httpx.
No Alibaba SDK and no OpenAI SDK are used. ``QWEN_BASE_URL`` is a base ending in
``/compatible-mode/v1``; ``/chat/completions`` is appended here.

Provider/network failures are mapped to the local typed error hierarchy so the
policy layer decides fallback: technical errors (timeout, transport, 429, 5xx,
malformed envelope) are fallback-eligible; auth/config problems are not. The API
key and image base64 never appear in logs or exception messages.
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

import httpx

from dantshaant_common.schemas import VisualFinding

from teeth_analyzer.backends.errors import (
    InvalidProviderResponseError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from teeth_analyzer.backends.vision_common import build_prompt, parse_findings
from teeth_analyzer.config import settings

logger = logging.getLogger(__name__)

_MAX_ERROR_BODY_CHARS = 300


async def analyze_with_qwen(
    jpeg_bytes: bytes,
    locale: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[list[VisualFinding], str, float]:
    """Run Qwen clinical vision. Returns ``(findings, model, latency_ms)``."""
    api_key = settings.dashscope_api_key
    base_url = settings.qwen_base_url
    model = settings.qwen_vision_model
    if not api_key:
        raise ProviderConfigurationError("DASHSCOPE_API_KEY is required for Qwen clinical vision")
    if not base_url:
        raise ProviderConfigurationError("QWEN_BASE_URL is required for Qwen clinical vision")
    if not model:
        raise ProviderConfigurationError("QWEN_VISION_MODEL is required for Qwen clinical vision")

    endpoint = base_url.rstrip("/") + "/chat/completions"
    image_b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_prompt(locale)},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    started = time.perf_counter()
    try:
        kwargs: dict[str, Any] = {"timeout": settings.ai_request_timeout_seconds}
        if transport is not None:
            kwargs["transport"] = transport
        async with httpx.AsyncClient(**kwargs) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError("Qwen clinical vision request timed out") from exc
    except httpx.TransportError as exc:
        raise ProviderUnavailableError(f"Qwen endpoint unreachable ({type(exc).__name__})") from exc
    latency_ms = round((time.perf_counter() - started) * 1000.0, 3)

    _raise_for_status(response, api_key)
    return parse_findings(_extract_text(response)), model, latency_ms


def _raise_for_status(response: httpx.Response, api_key: str) -> None:
    """Map HTTP failures to the correct fallback class. Never echoes secrets."""
    status = response.status_code
    if 200 <= status < 300:
        return
    detail = _safe_detail(response, api_key)
    if status in (401, 403):
        raise ProviderConfigurationError(
            f"Qwen authentication rejected (HTTP {status}) - check DASHSCOPE_API_KEY; {detail}"
        )
    if status == 429:
        raise ProviderRateLimitError(f"Qwen rate limited (HTTP {status}); {detail}")
    if 500 <= status <= 599:
        raise ProviderServerError(f"Qwen server error (HTTP {status}); {detail}")
    raise InvalidProviderResponseError(f"Qwen returned unexpected HTTP {status}; {detail}")


def _safe_detail(response: httpx.Response, api_key: str) -> str:
    """Short sanitized body excerpt; the API key is redacted if ever echoed."""
    try:
        body = response.text[:_MAX_ERROR_BODY_CHARS]
    except Exception:  # noqa: BLE001 - unreadable body must not mask the status
        body = "<unreadable response body>"
    if api_key:
        body = body.replace(api_key, "***")
    return f"body: {body}"


def _extract_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError as exc:
        raise InvalidProviderResponseError("Qwen returned a non-JSON body") from exc
    if not isinstance(payload, dict):
        raise InvalidProviderResponseError("Qwen returned a non-object JSON body")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise InvalidProviderResponseError("Qwen response is missing 'choices'")
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise InvalidProviderResponseError("Qwen message content is missing or not a string")
    return content


__all__ = ["analyze_with_qwen"]
