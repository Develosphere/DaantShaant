"""Alibaba Model Studio / Qwen provider adapter (Phase 2A.2).

Implements :class:`~orchestrator.ai.base.AIProvider` on top of the
OpenAI-compatible ``/chat/completions`` endpoint exposed by Alibaba Model
Studio (``QWEN_BASE_URL`` ends in ``/compatible-mode/v1``).

Design rules:

- plain ``httpx`` only — no Alibaba SDK, no OpenAI SDK;
- the base URL is a *base*: ``/chat/completions`` is appended here and the
  developer never repeats it in configuration;
- provider/network failures are mapped to the gateway exception hierarchy so
  the :class:`~orchestrator.ai.gateway.AIGateway` fallback policy stays
  intact: technical errors (timeout, transport, 429, 5xx, malformed payload)
  are fallback-eligible; authentication/config problems are not;
- arbitrary Python exceptions are NOT caught here — the gateway wraps them in
  the non-fallback-eligible :class:`ProviderInternalError`;
- the API key never appears in exception messages, logs, or reprs; image
  base64 is never echoed into errors;
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

_MAX_ERROR_BODY_CHARS = 300


class QwenProvider(AIProvider):
    """Async Qwen adapter using the OpenAI-compatible chat API."""

    name = "qwen"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        chat_model: str | None = None,
        vision_model: str | None = None,
        timeout_seconds: float | None = None,
        settings: AISettings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Build the adapter from explicit values or :class:`AISettings` (env).

        ``transport`` allows injecting an ``httpx`` transport for tests; no
        automated path should ever hit the real network when it is provided.
        """
        cfg = settings if settings is not None else AISettings()
        self._api_key = api_key if api_key is not None else cfg.dashscope_api_key
        self._base_url = base_url if base_url is not None else cfg.qwen_base_url
        self._default_model = default_model or cfg.qwen_default_model
        self._chat_model = chat_model or cfg.qwen_chat_model
        self._vision_model = vision_model or cfg.qwen_vision_model
        self._timeout = (
            timeout_seconds if timeout_seconds is not None else cfg.ai_request_timeout_seconds
        )
        self._transport = transport
        self.default_model = self._default_model

        if not self._api_key:
            raise ProviderConfigurationError("DASHSCOPE_API_KEY is required for the Qwen provider")
        if not self._base_url:
            raise ProviderConfigurationError("QWEN_BASE_URL is required for the Qwen provider")
        if not self._default_model:
            raise ProviderConfigurationError("QWEN_DEFAULT_MODEL is required for the Qwen provider")
        if self._timeout is None or self._timeout <= 0:
            raise ProviderConfigurationError("AI_REQUEST_TIMEOUT_SECONDS must be a positive number")

        self._endpoint = self._base_url.rstrip("/") + "/chat/completions"

    # ------------------------------------------------------------------
    # AIProvider implementation
    # ------------------------------------------------------------------
    async def generate_text(self, request: TextRequest) -> AIResult:
        messages = self._plain_messages(request.messages, request.prompt)
        return await self._chat(
            messages,
            # Plain text generation is conversational generation: it defaults to
            # QWEN_CHAT_MODEL, overridable per request. Vision/structured keep
            # their own configured models.
            model=request.model or self._chat_model or self._default_model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

    async def generate_vision(self, request: VisionRequest) -> AIResult:
        prompt = request.prompt or self._last_user_text(request.messages)
        user_content: list[dict[str, Any]] = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{request.content_type};base64,{request.image_base64}"
                },
            },
        ]
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]
        return await self._chat(
            messages,
            model=request.model or self._vision_model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

    async def generate_structured(self, request: StructuredRequest) -> AIResult:
        prompt = request.prompt or self._last_user_text(request.messages)
        instruction = self._structured_instruction(prompt, request.json_schema)
        if request.image_base64:
            user_content: list[dict[str, Any]] | str = [
                {"type": "text", "text": instruction},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{request.content_type};base64,{request.image_base64}"
                    },
                },
            ]
        else:
            user_content = instruction
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]
        result = await self._chat(
            messages,
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
    async def _chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        temperature: float | None,
        max_tokens: int | None,
        json_mode: bool = False,
    ) -> AIResult:
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if json_mode:
            # Conservative JSON mode: object-level enforcement only.
            payload["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        request_headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            kwargs: dict[str, Any] = {"timeout": self._timeout}
            if self._transport is not None:
                kwargs["transport"] = self._transport
            async with httpx.AsyncClient(**kwargs) as client:
                response = await client.post(self._endpoint, headers=request_headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"Qwen request exceeded its {self._timeout}s HTTP timeout"
            ) from exc
        except httpx.TransportError as exc:
            # Connect failures, DNS errors, and other transport-level problems.
            raise ProviderUnavailableError(
                f"Qwen endpoint unreachable ({type(exc).__name__})"
            ) from exc
        latency_ms = round((time.perf_counter() - started) * 1000.0, 3)

        self._raise_for_status(response)
        return self._parse_completion(response, latency_ms=latency_ms)

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map HTTP failures to the correct fallback class. Never echoes secrets."""
        status = response.status_code
        if 200 <= status < 300:
            return
        detail = self._safe_error_detail(response)
        if status in (401, 403):
            raise ProviderConfigurationError(
                f"Qwen authentication rejected (HTTP {status}) — check DASHSCOPE_API_KEY; {detail}"
            )
        if status == 429:
            raise ProviderRateLimitError(f"Qwen rate limited (HTTP {status}); {detail}")
        if 500 <= status <= 599:
            raise ProviderServerError(f"Qwen server error (HTTP {status}); {detail}")
        raise InvalidProviderResponseError(
            f"Qwen returned unexpected HTTP {status}; {detail}"
        )

    @staticmethod
    def _safe_error_detail(response: httpx.Response) -> str:
        """Short sanitized body excerpt; image data and oversized payloads are dropped."""
        try:
            body = response.text[:_MAX_ERROR_BODY_CHARS]
        except Exception:  # noqa: BLE001 - unreadable body must not mask the status
            body = "<unreadable response body>"
        return f"body: {body}"

    def _parse_completion(self, response: httpx.Response, *, latency_ms: float) -> AIResult:
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise InvalidProviderResponseError("Qwen returned a non-JSON body") from exc
        if not isinstance(payload, dict):
            raise InvalidProviderResponseError("Qwen returned a non-object JSON body")

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise InvalidProviderResponseError("Qwen response is missing 'choices'")
        first = choices[0]
        if not isinstance(first, dict):
            raise InvalidProviderResponseError("Qwen choice is not an object")
        message = first.get("message")
        if not isinstance(message, dict):
            raise InvalidProviderResponseError("Qwen choice is missing 'message'")
        content = message.get("content")
        if not isinstance(content, str):
            raise InvalidProviderResponseError("Qwen message content is missing or not a string")

        usage: UsageMetadata | None = None
        raw_usage = payload.get("usage")
        if isinstance(raw_usage, dict):
            usage = UsageMetadata(
                prompt_tokens=raw_usage.get("prompt_tokens"),
                completion_tokens=raw_usage.get("completion_tokens"),
                total_tokens=raw_usage.get("total_tokens"),
            )

        raw_metadata: dict[str, Any] | None = None
        response_id = payload.get("id")
        if isinstance(response_id, str) and response_id:
            raw_metadata = {"response_id": response_id}

        return AIResult(
            content=content,
            provider=self.name,
            model=payload.get("model") or self.default_model,
            usage=usage,
            latency_ms=latency_ms,
            finish_reason=first.get("finish_reason")
            if isinstance(first.get("finish_reason"), str)
            else None,
            raw_metadata=raw_metadata,
        )

    # ------------------------------------------------------------------
    # Request building helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _plain_messages(
        messages: list[ChatMessage], prompt: str | None
    ) -> list[dict[str, Any]]:
        if messages:
            return [{"role": m.role, "content": m.content} for m in messages]
        if prompt:
            return [{"role": "user", "content": prompt}]
        raise ProviderConfigurationError(
            "Qwen text request requires a prompt or messages"
        )

    @staticmethod
    def _last_user_text(messages: list[ChatMessage]) -> str:
        for message in reversed(messages):
            if message.role == "user":
                return message.content
        return "Describe the provided dental image."

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
                "Qwen structured response is not valid JSON"
            ) from exc
        if not isinstance(data, dict):
            raise StructuredOutputError(
                "Qwen structured response must be a JSON object"
            )
        return data

    @staticmethod
    def _validate_against_schema(
        data: dict[str, Any], json_schema: dict[str, Any]
    ) -> None:
        """Validate parsed JSON data against the request's JSON Schema.

        Raises :class:`StructuredOutputError` on validation failure so the
        gateway treats it as a non-fallback-eligible programming error.
        """
        try:
            jsonschema.validate(instance=data, schema=json_schema)
        except jsonschema.ValidationError as exc:
            raise StructuredOutputError(
                f"Qwen structured response does not match the requested schema: {exc.message}"
            ) from exc
