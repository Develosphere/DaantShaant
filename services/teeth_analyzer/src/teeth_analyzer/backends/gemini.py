"""Gemini clinical-vision backend - TECHNICAL FALLBACK (Phase 2C).

Google ``v1beta`` ``generateContent`` REST call over plain async httpx. No
Google SDK is used (the previous ``google.generativeai`` dependency is removed).
This mirrors the Qwen backend so both return the SAME internal shape and the
downstream never sees a provider-specific envelope.

The API key is sent in the ``x-goog-api-key`` header (never the URL). Only
technical failures are surfaced as fallback-eligible typed errors; Google reports
invalid/missing keys as HTTP 400/401/403, which are configuration errors and are
NOT fallback-eligible. Image base64 and the API key never leak into errors/logs.
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

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_MAX_ERROR_BODY_CHARS = 300


async def analyze_with_gemini(
    jpeg_bytes: bytes,
    locale: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[list[VisualFinding], str, float]:
    """Run Gemini clinical vision. Returns ``(findings, model, latency_ms)``."""
    api_key = settings.gemini_api_key
    model = settings.gemini_model
    base = (settings.gemini_base_url or DEFAULT_GEMINI_BASE_URL).rstrip("/")
    if not api_key:
        raise ProviderConfigurationError("GEMINI_API_KEY is required for Gemini clinical vision")
    if not model:
        raise ProviderConfigurationError("GEMINI_MODEL is required for Gemini clinical vision")

    endpoint = f"{base}/{model}:generateContent"
    image_b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
    payload: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": build_prompt(locale)},
                    {"inlineData": {"mimeType": "image/jpeg", "data": image_b64}},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
        },
    }
    headers = {
        "x-goog-api-key": api_key,
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
        raise ProviderTimeoutError("Gemini clinical vision request timed out") from exc
    except httpx.TransportError as exc:
        raise ProviderUnavailableError(f"Gemini endpoint unreachable ({type(exc).__name__})") from exc
    latency_ms = round((time.perf_counter() - started) * 1000.0, 3)

    _raise_for_status(response, api_key)
    return parse_findings(_extract_text(response)), model, latency_ms


def _raise_for_status(response: httpx.Response, api_key: str) -> None:
    """Map HTTP failures to the correct fallback class. Never echoes secrets."""
    status = response.status_code
    if 200 <= status < 300:
        return
    detail = _safe_detail(response, api_key)
    if status in (400, 401, 403):
        raise ProviderConfigurationError(
            f"Gemini authentication/config rejected (HTTP {status}) - check GEMINI_API_KEY; {detail}"
        )
    if status == 429:
        raise ProviderRateLimitError(f"Gemini rate limited (HTTP {status}); {detail}")
    if 500 <= status <= 599:
        raise ProviderServerError(f"Gemini server error (HTTP {status}); {detail}")
    raise InvalidProviderResponseError(f"Gemini returned unexpected HTTP {status}; {detail}")


def _safe_detail(response: httpx.Response, api_key: str) -> str:
    """Short body excerpt; the API key is redacted if it were ever echoed."""
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
        raise InvalidProviderResponseError("Gemini returned a non-JSON body") from exc
    if not isinstance(payload, dict):
        raise InvalidProviderResponseError("Gemini returned a non-object JSON body")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise InvalidProviderResponseError("Gemini response is missing 'candidates'")
    first = candidates[0]
    content = first.get("content") if isinstance(first, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        raise InvalidProviderResponseError("Gemini candidate content is missing 'parts'")
    text = "".join(
        part.get("text", "")
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    )
    if not text:
        raise InvalidProviderResponseError("Gemini response contained no text")
    return text


__all__ = ["analyze_with_gemini", "DEFAULT_GEMINI_BASE_URL"]
