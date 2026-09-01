"""Google Gemini provider adapter (Phase 2A.3) — technical fallback role.

Implements :class:`~orchestrator.ai.base.AIProvider` on top of the Gemini
``v1beta`` ``generateContent`` REST endpoint. This is the FALLBACK adapter
that mirrors the Qwen (primary) adapter so both behave identically from the
:class:`~orchestrator.ai.gateway.AIGateway` caller's perspective.

Design rules (identical policy to the Qwen adapter):

- plain ``httpx`` only — no Google SDK is installed and none is introduced;
  this reuses the same REST transport shape the legacy ``_GeminiClient`` uses;
- the API key is sent in the ``x-goog-api-key`` header, never in the URL, so
  it cannot leak through request-line logging;
- provider/network failures are mapped to the gateway exception hierarchy:
  technical errors (timeout, transport, 429, 5xx, malformed payload) are
  fallback-eligible; authentication/config problems are not;
- arbitrary Python exceptions are NOT caught here — the gateway wraps them in
  the non-fallback-eligible :class:`ProviderInternalError`;
- the API key and image base64 never appear in exception messages or logs;
- no retries, no backoff, no provider switching — that is the gateway's job.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
import jsonschema

from orchestrator.ai.base import AIProvider
from orchestrator.ai.exceptions import (
    InvalidProviderResponseError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    StructuredOutputError,
)
from orchestrator.ai.schemas import (
    AIResult,
    ChatMessage,
    StructuredRequest,
    TextRequest,
    UsageMetadata,
    VisionRequest,
)
from orchestrator.config import AISettings

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_MAX_ERROR_BODY_CHARS = 300


class GeminiProvider(AIProvider):
    """Async Gemini adapter using the ``generateContent`` REST API."""

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout_seconds: float | None = None,
        settings: AISettings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Build the adapter from explicit values or :class:`AISettings` (env).

        ``transport`` allows injecting an ``httpx`` transport for tests; no
        automated path should ever hit the real network when it is provided.
        """
        cfg = settings if settings is not None else AISettings()
        self._api_key = api_key if api_key is not None else cfg.gemini_api_key
        base = base_url if base_url is not None else cfg.gemini_base_url
        self._base_url = (base or DEFAULT_GEMINI_BASE_URL).rstrip("/")
        self._default_model = default_model or cfg.gemini_model
        self._timeout = (
            timeout_seconds if timeout_seconds is not None else cfg.ai_request_timeout_seconds
        )
        self._transport = transport
        self.default_model = self._default_model

        if not self._api_key:
            raise ProviderConfigurationError("GEMINI_API_KEY is required for the Gemini provider")
        if not self._default_model:
            raise ProviderConfigurationError("GEMINI_MODEL is required for the Gemini provider")
        if self._timeout is None or self._timeout <= 0:
            raise ProviderConfigurationError("AI_REQUEST_TIMEOUT_SECONDS must be a positive number")

    # ------------------------------------------------------------------
    # AIProvider implementation
    # ------------------------------------------------------------------
    async def generate_text(self, request: TextRequest) -> AIResult:
        system_text, contents = self._build_text_contents(request.messages, request.prompt)
        return await self._generate(
            contents,
            model=request.model or self._default_model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            system_text=system_text,
        )

    async def generate_vision(self, request: VisionRequest) -> AIResult:
        prompt = request.prompt or self._last_user_text(request.messages)
        contents = [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": request.content_type,
                            "data": request.image_base64,
                        }
                    },
                ],
            }
        ]
        return await self._generate(
            contents,
            model=request.model or self._default_model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

    async def generate_structured(self, request: StructuredRequest) -> AIResult:
        prompt = request.prompt or self._last_user_text(request.messages)
        instruction = self._structured_instruction(prompt, request.json_schema)
        parts: list[dict[str, Any]] = [{"text": instruction}]
        if request.image_base64:
            parts.append(
                {
                    "inlineData": {
                        "mimeType": request.content_type,
                        "data": request.image_base64,
                    }
                }
            )
        contents = [{"role": "user", "parts": parts}]
        result = await self._generate(
            contents,
            model=request.model or self._default_model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            json_mode=True,
        )
        result.data = self._parse_json_object(result.content)
        self._validate_against_schema(result.data, request.json_schema)
        return result

    # ------------------------------------------------------------------
    # HTTP transport + response normalization
    # ------------------------------------------------------------------
    async def _generate(
        self,
        contents: list[dict[str, Any]],
        *,
        model: str,
        temperature: float | None,
        max_tokens: int | None,
        json_mode: bool = False,
        system_text: str | None = None,
    ) -> AIResult:
        payload: dict[str, Any] = {"contents": contents}
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        generation_config: dict[str, Any] = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens
        if json_mode:
            # Conservative JSON mode: object-level enforcement only, matching
            # the Qwen adapter so structured behavior is caller-consistent.
            generation_config["responseMimeType"] = "application/json"
        if generation_config:
            payload["generationConfig"] = generation_config

        endpoint = f"{self._base_url}/{model}:generateContent"
        started = time.perf_counter()
        request_headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        try:
            kwargs: dict[str, Any] = {"timeout": self._timeout}
            if self._transport is not None:
                kwargs["transport"] = self._transport
            async with httpx.AsyncClient(**kwargs) as client:
                response = await client.post(endpoint, headers=request_headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"Gemini request exceeded its {self._timeout}s HTTP timeout"
            ) from exc
        except httpx.TransportError as exc:
            # Connect failures, DNS errors, and other transport-level problems.
            raise ProviderUnavailableError(
                f"Gemini endpoint unreachable ({type(exc).__name__})"
            ) from exc
        latency_ms = round((time.perf_counter() - started) * 1000.0, 3)

        self._raise_for_status(response)
        return self._parse_completion(response, latency_ms=latency_ms, model=model)

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map HTTP failures to the correct fallback class. Never echoes secrets.

        Google reports invalid/missing API keys as HTTP 400/401/403, so all
        three are treated as configuration/auth failures (NOT fallback).
        """
        status = response.status_code
        if 200 <= status < 300:
            return
        detail = self._safe_error_detail(response)
        if status in (400, 401, 403):
            raise ProviderConfigurationError(
                f"Gemini authentication/config rejected (HTTP {status}) — check GEMINI_API_KEY; {detail}"
            )
        if status == 429:
            raise ProviderRateLimitError(f"Gemini rate limited (HTTP {status}); {detail}")
        if 500 <= status <= 599:
            raise ProviderServerError(f"Gemini server error (HTTP {status}); {detail}")
        raise InvalidProviderResponseError(
            f"Gemini returned unexpected HTTP {status}; {detail}"
        )

    def _safe_error_detail(self, response: httpx.Response) -> str:
        """Short body excerpt; oversized payloads are truncated and the API key
        (if it were ever echoed) is redacted so it never leaks into errors."""
        try:
            body = response.text[:_MAX_ERROR_BODY_CHARS]
        except Exception:  # noqa: BLE001 - unreadable body must not mask the status
            body = "<unreadable response body>"
        if self._api_key:
            body = body.replace(self._api_key, "***")
        return f"body: {body}"

    def _parse_completion(
        self, response: httpx.Response, *, latency_ms: float, model: str
    ) -> AIResult:
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise InvalidProviderResponseError("Gemini returned a non-JSON body") from exc
        if not isinstance(payload, dict):
            raise InvalidProviderResponseError("Gemini returned a non-object JSON body")

        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise InvalidProviderResponseError("Gemini response is missing 'candidates'")
        first = candidates[0]
        if not isinstance(first, dict):
            raise InvalidProviderResponseError("Gemini candidate is not an object")
        candidate_content = first.get("content")
        if not isinstance(candidate_content, dict):
            raise InvalidProviderResponseError("Gemini candidate is missing 'content'")
        parts = candidate_content.get("parts")
        if not isinstance(parts, list):
            raise InvalidProviderResponseError("Gemini content is missing 'parts'")

        text = "".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )

        usage: UsageMetadata | None = None
        raw_usage = payload.get("usageMetadata")
        if isinstance(raw_usage, dict):
            usage = UsageMetadata(
                prompt_tokens=raw_usage.get("promptTokenCount"),
                completion_tokens=raw_usage.get("candidatesTokenCount"),
                total_tokens=raw_usage.get("totalTokenCount"),
            )

        raw_metadata: dict[str, Any] | None = None
        response_id = payload.get("responseId")
        if isinstance(response_id, str) and response_id:
            raw_metadata = {"response_id": response_id}

        finish_reason = first.get("finishReason")
        return AIResult(
            content=text,
            provider=self.name,
            model=payload.get("modelVersion") or model or self.default_model,
            usage=usage,
            latency_ms=latency_ms,
            finish_reason=finish_reason.lower() if isinstance(finish_reason, str) else None,
            raw_metadata=raw_metadata,
        )

    # ------------------------------------------------------------------
    # Request building helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_text_contents(
        messages: list[ChatMessage], prompt: str | None
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Split system turns into a single instruction and preserve chat order.

        Gemini expects ``user``/``model`` roles; our neutral ``assistant``
        role maps to ``model``. Returns ``(system_text, contents)``.
        """
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "system":
                system_parts.append(message.content)
                continue
            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})

        if not contents and not system_parts:
            if not prompt:
                raise ProviderConfigurationError(
                    "Gemini text request requires a prompt or messages"
                )
            contents.append({"role": "user", "parts": [{"text": prompt}]})

        system_text = "\n\n".join(system_parts) if system_parts else None
        return system_text, contents

    @staticmethod
    def _last_user_text(messages: list[ChatMessage]) -> str:
        for message in reversed(messages):
            if message.role == "user":
                return message.content
        return "Describe the provided image."

    @staticmethod
    def _structured_instruction(prompt: str, json_schema: dict[str, Any]) -> str:
        schema_text = json.dumps(json_schema, ensure_ascii=False)
        return (
            f"{prompt.strip()}\n\n"
            f"Respond with ONLY a single JSON object that validates against this "
            f"JSON schema (no prose, no markdown fences):\n{schema_text}"
        )

    @staticmethod
    def _parse_json_object(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            # Strip simple markdown fences without attempting repairs.
            lines = text.splitlines()
            lines = [line for line in lines if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise StructuredOutputError(
                "Gemini structured response is not valid JSON"
            ) from exc
        if not isinstance(data, dict):
            raise StructuredOutputError(
                "Gemini structured response must be a JSON object"
            )
        return data

    @staticmethod
    def _validate_against_schema(
        data: dict[str, Any], json_schema: dict[str, Any]
    ) -> None:
        """Validate parsed JSON data against the request's JSON Schema.

        Raises :class:`StructuredOutputError` on validation failure so the
        gateway treats it as a non-fallback-eligible programming error,
        consistent with the Qwen adapter.
        """
        try:
            jsonschema.validate(instance=data, schema=json_schema)
        except jsonschema.ValidationError as exc:
            raise StructuredOutputError(
                f"Gemini structured response does not match the requested schema: {exc.message}"
            ) from exc
