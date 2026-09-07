#!/usr/bin/env python3
"""DaantShaant Qwen Connectivity & Response Diagnostic Tool.

Compares Working Scan/Report Qwen Path vs Failing Central Dentist Chat Qwen Path.
Performs non-destructive diagnostics: DNS resolution, TCP/TLS/HTTP connectivity,
minimal raw API call, latency over connection reuse, project provider execution,
and timeout/budget hierarchy audits.

NEVER PRINTS: API keys, Authorization headers, patient data, or secrets.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

# Ensure orchestrator package is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "orchestrator" / "src"))

from orchestrator.ai.exceptions import (  # noqa: E402
    AIGatewayError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from orchestrator.ai.qwen import QwenProvider  # noqa: E402
from orchestrator.ai.schemas import ChatMessage, TextRequest  # noqa: E402
from orchestrator.central_dentist.prompts import (  # noqa: E402
    CENTRAL_DENTIST_SYSTEM_PROMPT,
    audit_chat_prompt_size,
    build_grounded_context,
)
from orchestrator.config import AISettings, settings as app_settings  # noqa: E402

logger = logging.getLogger("diagnose_qwen")


@dataclass
class DiagnosticResult:
    """Structured container for all diagnostic test outcomes."""

    # Config
    base_url_host: str = ""
    base_url_path: str = ""
    default_model: str = ""
    chat_model: str = ""
    vision_model: str = ""
    relevance_model: str = ""
    ai_request_timeout: float = 60.0
    chat_qwen_timeout: float = 12.0
    chat_request_timeout: float = 15.0
    fallback_provider: str = ""
    api_key_configured: bool = False

    # DNS
    dns_status: str = "PENDING"
    dns_ms: float = 0.0
    resolved_ips: list[str] = field(default_factory=list)
    dns_error: str = ""

    # HTTP Connectivity (GET /models or safe lightweight probe)
    http_status: str = "PENDING"
    http_code: Optional[int] = None
    http_ms: float = 0.0
    http_error: str = ""

    # Raw Minimal Call
    raw_status: str = "PENDING"
    raw_model: str = ""
    raw_ms: float = 0.0
    raw_response: str = ""
    raw_error: str = ""

    # Reused Connection Latency
    reused_calls: list[float] = field(default_factory=list)
    reused_min_ms: float = 0.0
    reused_max_ms: float = 0.0
    reused_avg_ms: float = 0.0
    reused_status: str = "PENDING"

    # Project Provider Call
    provider_status: str = "PENDING"
    provider_model: str = ""
    provider_ms: float = 0.0
    provider_response: str = ""
    provider_error: str = ""

    # Scan Config Test
    scan_status: str = "PENDING"
    scan_model: str = ""
    scan_timeout: float = 60.0
    scan_ms: float = 0.0
    scan_error: str = ""

    # Chat Config Test
    chat_status: str = "PENDING"
    chat_test_model: str = ""
    chat_timeout: float = 8.0
    chat_ms: float = 0.0
    chat_error: str = ""

    # Payload Audit
    payload_audit: dict[str, int] = field(default_factory=dict)

    # Root Cause Summary
    likely_root_causes: list[str] = field(default_factory=list)


def classify_http_error(status_code: int, detail: str = "") -> str:
    """Classify HTTP status codes into actionable categories without leaking secrets."""
    if status_code == 401:
        return f"HTTP 401 (Authentication Rejected) — check DASHSCOPE_API_KEY. {detail}".strip()
    if status_code == 403:
        return f"HTTP 403 (Quota/Permission Denied) — check Alibaba Model Studio model access and quota. {detail}".strip()
    if status_code == 404:
        return f"HTTP 404 (Endpoint or Model Not Found) — check QWEN_BASE_URL and model name. {detail}".strip()
    if status_code == 429:
        return f"HTTP 429 (Rate Limit Exceeded) — requests throttled by Alibaba Model Studio. {detail}".strip()
    if 500 <= status_code <= 599:
        return f"HTTP {status_code} (Provider Server Error) — Alibaba Model Studio upstream failure. {detail}".strip()
    return f"HTTP {status_code} ({detail})".strip()


# ---------------------------------------------------------------------------
# Diagnostic Test A: Config
# ---------------------------------------------------------------------------
def run_test_a_config(settings: AISettings) -> DiagnosticResult:
    """Extract and sanitize configuration parameters."""
    res = DiagnosticResult()
    parsed = urlparse(settings.qwen_base_url)
    res.base_url_host = parsed.netloc or settings.qwen_base_url
    res.base_url_path = parsed.path
    res.default_model = settings.qwen_default_model
    res.chat_model = settings.qwen_chat_model
    res.vision_model = settings.qwen_vision_model
    res.relevance_model = settings.qwen_relevance_model
    res.ai_request_timeout = settings.ai_request_timeout_seconds
    res.chat_qwen_timeout = app_settings.chat_qwen_timeout_seconds
    res.chat_request_timeout = app_settings.chat_request_timeout_seconds
    res.fallback_provider = settings.fallback_ai_provider
    res.api_key_configured = bool(settings.dashscope_api_key and settings.dashscope_api_key.strip())
    return res


# ---------------------------------------------------------------------------
# Diagnostic Test B: DNS Resolution
# ---------------------------------------------------------------------------
def run_test_b_dns(hostname: str) -> tuple[str, float, list[str], str]:
    """Resolve Qwen endpoint hostname and measure resolution latency."""
    if not hostname:
        return "FAIL", 0.0, [], "Hostname is empty; check QWEN_BASE_URL"

    clean_host = hostname.split(":")[0]
    t0 = time.perf_counter()
    try:
        addr_info = socket.getaddrinfo(clean_host, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        ips = sorted(list({entry[4][0] for entry in addr_info if entry and len(entry) >= 5}))
        return "PASS", round(elapsed_ms, 2), ips, ""
    except socket.gaierror as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", round(elapsed_ms, 2), [], f"DNS resolution failed: {exc}"
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", round(elapsed_ms, 2), [], f"Unexpected DNS error: {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Diagnostic Test C: TCP/TLS/HTTP Connectivity
# ---------------------------------------------------------------------------
async def run_test_c_http(
    base_url: str,
    api_key: str,
    *,
    timeout: float = 10.0,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> tuple[str, Optional[int], float, str]:
    """Probe the OpenAI-compatible endpoint with a safe, lightweight GET /models."""
    models_url = base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    t0 = time.perf_counter()
    try:
        kwargs: dict[str, Any] = {"timeout": httpx.Timeout(timeout, connect=5.0)}
        if transport is not None:
            kwargs["transport"] = transport

        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.get(models_url, headers=headers)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            if 200 <= resp.status_code < 300:
                return "PASS", resp.status_code, round(elapsed_ms, 2), ""
            elif resp.status_code == 404:
                # Some compatible-mode proxies do not implement GET /models, but TCP/TLS passed
                return (
                    "PASS",
                    resp.status_code,
                    round(elapsed_ms, 2),
                    "HTTP/TLS connected (GET /models returned 404 — endpoint reachable)",
                )
            else:
                err = classify_http_error(resp.status_code)
                return "FAIL", resp.status_code, round(elapsed_ms, 2), err

    except httpx.ConnectTimeout as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", None, round(elapsed_ms, 2), f"Connection timeout after {timeout}s ({exc})"
    except httpx.ReadTimeout as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", None, round(elapsed_ms, 2), f"Read timeout after {timeout}s ({exc})"
    except httpx.TransportError as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", None, round(elapsed_ms, 2), f"Transport/TLS error: {type(exc).__name__}: {exc}"
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", None, round(elapsed_ms, 2), f"Unexpected HTTP error: {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Diagnostic Test D: Minimal Raw Qwen Call
# ---------------------------------------------------------------------------
async def run_test_d_raw_qwen(
    base_url: str,
    api_key: str,
    model: str,
    *,
    timeout: float = 30.0,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> tuple[str, str, float, str, str]:
    """Issue a minimal direct POST /chat/completions with QWEN_OK prompt."""
    endpoint = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a concise assistant."},
            {"role": "user", "content": "Reply with exactly: QWEN_OK"},
        ],
        "temperature": 0.0,
        "max_tokens": 20,
    }

    t0 = time.perf_counter()
    try:
        kwargs: dict[str, Any] = {"timeout": httpx.Timeout(timeout, connect=10.0)}
        if transport is not None:
            kwargs["transport"] = transport

        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            if 200 <= resp.status_code < 300:
                data = resp.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                status = "PASS" if "QWEN_OK" in content else "PASS (UNEXPECTED TEXT)"
                return status, model, round(elapsed_ms, 2), content, ""
            else:
                err = classify_http_error(resp.status_code)
                return "FAIL", model, round(elapsed_ms, 2), "", err

    except httpx.ConnectTimeout as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", model, round(elapsed_ms, 2), "", f"Connect timeout ({timeout}s): {exc}"
    except httpx.ReadTimeout as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", model, round(elapsed_ms, 2), "", f"Read/Generation timeout ({timeout}s): {exc}"
    except httpx.TransportError as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", model, round(elapsed_ms, 2), "", f"Transport/TLS error: {type(exc).__name__}: {exc}"
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", model, round(elapsed_ms, 2), "", f"Unexpected error: {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Diagnostic Test E: Reused Connection Latency
# ---------------------------------------------------------------------------
async def run_test_e_reused_latency(
    base_url: str,
    api_key: str,
    model: str,
    repeat_count: int = 3,
    timeout: float = 30.0,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> tuple[str, list[float], float, float, float]:
    """Perform sequential minimal calls using a SINGLE persistent AsyncClient."""
    endpoint = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a concise assistant."},
            {"role": "user", "content": "Reply with exactly: QWEN_OK"},
        ],
        "temperature": 0.0,
        "max_tokens": 20,
    }

    latencies: list[float] = []
    kwargs: dict[str, Any] = {
        "timeout": httpx.Timeout(timeout, connect=10.0),
        "limits": httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=30.0),
    }
    if transport is not None:
        kwargs["transport"] = transport

    async with httpx.AsyncClient(**kwargs) as client:
        for _ in range(repeat_count):
            t0 = time.perf_counter()
            try:
                resp = await client.post(endpoint, headers=headers, json=payload)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                if 200 <= resp.status_code < 300:
                    latencies.append(round(elapsed_ms, 2))
                else:
                    latencies.append(-float(resp.status_code))
            except Exception:
                latencies.append(-1.0)

    valid = [lat for lat in latencies if lat > 0]
    if not valid:
        return "FAIL", latencies, 0.0, 0.0, 0.0

    min_lat = min(valid)
    max_lat = max(valid)
    avg_lat = round(sum(valid) / len(valid), 2)
    status = "PASS" if len(valid) == repeat_count else "PARTIAL"
    return status, latencies, min_lat, max_lat, avg_lat


# ---------------------------------------------------------------------------
# Diagnostic Test F: Existing Project Provider Implementation
# ---------------------------------------------------------------------------
async def run_test_f_project_provider(
    settings: AISettings,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> tuple[str, str, float, str, str]:
    """Call Qwen using the actual orchestrator QwenProvider implementation."""
    try:
        provider = QwenProvider(settings=settings, transport=transport)
    except ProviderConfigurationError as exc:
        return "FAIL", "", 0.0, "", f"Provider configuration rejected: {exc}"

    t0 = time.perf_counter()
    try:
        req = TextRequest(
            prompt="Reply with exactly: QWEN_PROVIDER_OK",
            max_tokens=20,
            temperature=0.0,
        )
        res = await provider.generate_text(req)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        text = res.content.strip()
        status = "PASS" if "QWEN_PROVIDER_OK" in text else "PASS (UNEXPECTED TEXT)"
        return status, res.model, round(elapsed_ms, 2), text, ""
    except ProviderTimeoutError as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", provider.default_model, round(elapsed_ms, 2), "", f"ProviderTimeoutError: {exc}"
    except ProviderUnavailableError as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", provider.default_model, round(elapsed_ms, 2), "", f"ProviderUnavailableError: {exc}"
    except AIGatewayError as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", provider.default_model, round(elapsed_ms, 2), "", f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", provider.default_model, round(elapsed_ms, 2), "", f"Unexpected: {type(exc).__name__}: {exc}"
    finally:
        await provider.aclose()


# ---------------------------------------------------------------------------
# Diagnostic Test G: Scan Report Generation Style
# ---------------------------------------------------------------------------
async def run_test_g_scan_config(
    settings: AISettings,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> tuple[str, str, float, float, str]:
    """Test Qwen using the Scan Report configuration style (timeout=60s, temp=0.1)."""
    scan_timeout = settings.ai_request_timeout_seconds  # 60.0s
    try:
        provider = QwenProvider(
            settings=settings,
            timeout_seconds=scan_timeout,
            transport=transport,
        )
    except Exception as exc:
        return "FAIL", "", scan_timeout, 0.0, f"Setup failed: {exc}"

    t0 = time.perf_counter()
    try:
        req = TextRequest(
            prompt="Reply with exactly: QWEN_SCAN_OK",
            max_tokens=600,
            temperature=0.1,
        )
        res = await provider.generate_text(req)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "PASS", res.model, scan_timeout, round(elapsed_ms, 2), ""
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", provider.default_model, scan_timeout, round(elapsed_ms, 2), f"{type(exc).__name__}: {exc}"
    finally:
        await provider.aclose()


# ---------------------------------------------------------------------------
# Diagnostic Test H: Central Dentist Chat Style
# ---------------------------------------------------------------------------
async def run_test_h_chat_config(
    settings: AISettings,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> tuple[str, str, float, float, str]:
    """Test Qwen using the Central Dentist chat configuration (timeout=12.0s, temp=0.25, max_tokens=200)."""
    chat_timeout = app_settings.chat_qwen_timeout_seconds  # 12.0s
    try:
        provider = QwenProvider(
            settings=settings,
            timeout_seconds=chat_timeout,
            transport=transport,
        )
    except Exception as exc:
        return "FAIL", "", chat_timeout, 0.0, f"Setup failed: {exc}"

    t0 = time.perf_counter()
    try:
        async with asyncio.timeout(chat_timeout):
            req = TextRequest(
                messages=[
                    ChatMessage(role="system", content=CENTRAL_DENTIST_SYSTEM_PROMPT),
                    ChatMessage(role="user", content="Reply with exactly: QWEN_CHAT_OK"),
                ],
                max_tokens=200,
                temperature=0.25,
            )
            res = await provider.generate_text(req)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return "PASS", res.model, chat_timeout, round(elapsed_ms, 2), ""
    except (TimeoutError, ProviderTimeoutError) as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return (
            "FAIL (TIMEOUT)",
            provider.default_model,
            chat_timeout,
            round(elapsed_ms, 2),
            f"Timed out after {chat_timeout}s budget ({exc})",
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return "FAIL", provider.default_model, chat_timeout, round(elapsed_ms, 2), f"{type(exc).__name__}: {exc}"
    finally:
        await provider.aclose()


# ---------------------------------------------------------------------------
# Diagnostic Runner & Report Generator
# ---------------------------------------------------------------------------
async def run_all_diagnostics(
    *,
    timeout: float = 30.0,
    repeat: int = 3,
    verbose: bool = False,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> DiagnosticResult:
    """Execute all diagnostic steps sequentially and produce a structured summary."""
    cfg = AISettings()
    res = run_test_a_config(cfg)

    # 1. DNS
    res.dns_status, res.dns_ms, res.resolved_ips, res.dns_error = run_test_b_dns(res.base_url_host)

    # 2. HTTP Connectivity (Light probe)
    res.http_status, res.http_code, res.http_ms, res.http_error = await run_test_c_http(
        cfg.qwen_base_url, cfg.dashscope_api_key, timeout=min(timeout, 10.0), transport=transport
    )

    # 3. Raw Minimal Call
    res.raw_status, res.raw_model, res.raw_ms, res.raw_response, res.raw_error = await run_test_d_raw_qwen(
        cfg.qwen_base_url, cfg.dashscope_api_key, cfg.qwen_chat_model, timeout=timeout, transport=transport
    )

    # 4. Reused Connection Latency
    (
        res.reused_status,
        res.reused_calls,
        res.reused_min_ms,
        res.reused_max_ms,
        res.reused_avg_ms,
    ) = await run_test_e_reused_latency(
        cfg.qwen_base_url, cfg.dashscope_api_key, cfg.qwen_chat_model, repeat_count=repeat, timeout=timeout, transport=transport
    )

    # 5. Project Provider Call
    res.provider_status, res.provider_model, res.provider_ms, res.provider_response, res.provider_error = (
        await run_test_f_project_provider(cfg, transport=transport)
    )

    # 6. Scan Config
    res.scan_status, res.scan_model, res.scan_timeout, res.scan_ms, res.scan_error = (
        await run_test_g_scan_config(cfg, transport=transport)
    )

    # 7. Chat Config (8.0s budget)
    res.chat_status, res.chat_test_model, res.chat_timeout, res.chat_ms, res.chat_error = (
        await run_test_h_chat_config(cfg, transport=transport)
    )

    # 8. Payload size audit sample
    mock_context = build_grounded_context()
    res.payload_audit = audit_chat_prompt_size(
        system_prompt=CENTRAL_DENTIST_SYSTEM_PROMPT,
        grounded_context=mock_context,
        user_message="What should I do about toothache?",
    )

    # 9. Analyze Root Cause
    if res.chat_status.startswith("FAIL") and (res.scan_status == "PASS" or res.raw_status == "PASS"):
        if res.raw_ms > res.chat_timeout * 1000.0 or (res.reused_calls and res.reused_calls[0] > res.chat_timeout * 1000.0):
            res.likely_root_causes.append(
                f"LATENCY BUDGET MISMATCH: Qwen model ({cfg.qwen_chat_model}) response latency "
                f"({res.raw_ms:.0f}ms) exceeds Central Dentist chat budget ({res.chat_timeout:.1f}s). "
                f"Scan report succeeds because its timeout budget is {res.scan_timeout:.1f}s."
            )
        else:
            res.likely_root_causes.append(
                f"CHAT TIMEOUT THRESHOLD: Chat budget ({res.chat_timeout:.1f}s) triggered before "
                f"remote inference completed. Scan budget ({res.scan_timeout:.1f}s) tolerates slower turns."
            )

    if res.reused_calls and len(res.reused_calls) >= 2:
        cold_ms = res.reused_calls[0]
        warm_ms = res.reused_calls[1]
        if cold_ms > warm_ms * 2.0 and cold_ms > 4000.0:
            res.likely_root_causes.append(
                f"COLD-START TLS PENALTY: Initial connection took {cold_ms:.0f}ms vs warm {warm_ms:.0f}ms. "
                "Client connection reuse reduces turn latency significantly."
            )

    if not res.api_key_configured:
        res.likely_root_causes.append("MISSING API KEY: DASHSCOPE_API_KEY is not configured in .env.")

    if res.dns_status == "FAIL":
        res.likely_root_causes.append(f"DNS RESOLUTION FAILURE: Host {res.base_url_host} cannot be resolved.")

    if res.http_code in (401, 403):
        res.likely_root_causes.append(f"MODEL STUDIO PERMISSION/QUOTA: Upstream returned HTTP {res.http_code}.")

    if not res.likely_root_causes:
        if res.raw_status == "PASS" and res.chat_status == "PASS":
            res.likely_root_causes.append(
                "CONNECTIVITY HEALTHY: Qwen is responding within latency budgets. "
                "Any intermittent timeouts in chat were likely caused by cross-region network spikes or upstream load."
            )
        else:
            res.likely_root_causes.append("INCONCLUSIVE: Review detailed error outputs above.")

    return res


def print_report(res: DiagnosticResult, verbose: bool = False) -> None:
    """Print the human-readable diagnostic report formatted as requested."""
    print()
    print("=" * 48)
    print("DAANTSHAANT QWEN DIAGNOSTIC")
    print("=" * 48)
    print()
    print("CONFIG")
    print(f"base_url=https://{res.base_url_host}{res.base_url_path}")
    print(f"model={res.default_model}")
    print(f"chat_model={res.chat_model}")
    print(f"vision_model={res.vision_model}")
    print(f"production_timeout={res.chat_qwen_timeout}s (chat) / {res.scan_timeout}s (scan)")
    print(f"api_key_status={'CONFIGURED' if res.api_key_configured else 'MISSING'}")
    print(f"fallback_provider={res.fallback_provider or 'none'}")
    print()
    print("DNS")
    print(f"{res.dns_status}")
    print(f"{res.dns_ms:.0f}ms")
    if res.resolved_ips:
        print(f"ips={', '.join(res.resolved_ips)}")
    if res.dns_error:
        print(f"error={res.dns_error}")
    print()
    print("HTTP")
    print(f"{res.http_status}")
    print(f"code={res.http_code if res.http_code is not None else 'N/A'}")
    print(f"{res.http_ms:.0f}ms")
    if res.http_error:
        print(f"detail={res.http_error}")
    print()
    print("RAW MINIMAL QWEN")
    print(f"{res.raw_status}")
    print(f"response={res.raw_response or 'NONE'}")
    print(f"{res.raw_ms:.0f}ms")
    if res.raw_error:
        print(f"error={res.raw_error}")
    print()
    print("REUSED CONNECTION CALLS")
    for idx, call_ms in enumerate(res.reused_calls, start=1):
        if call_ms >= 0:
            print(f"{idx}: {call_ms:.0f}ms")
        else:
            print(f"{idx}: ERROR ({call_ms:.0f})")
    print(f"avg: {res.reused_avg_ms:.0f}ms (min: {res.reused_min_ms:.0f}ms, max: {res.reused_max_ms:.0f}ms)")
    print()
    print("PROJECT PROVIDER")
    print(f"{res.provider_status}")
    print(f"elapsed={res.provider_ms:.0f}ms")
    if res.provider_error:
        print(f"error={res.provider_error}")
    print()
    print("SCAN CONFIG")
    print(f"{res.scan_status}")
    print(f"model={res.scan_model}")
    print(f"timeout={res.scan_timeout}s")
    print(f"elapsed={res.scan_ms:.0f}ms")
    if res.scan_error:
        print(f"error={res.scan_error}")
    print()
    print("CHAT CONFIG")
    print(f"{res.chat_status}")
    print(f"model={res.chat_test_model}")
    print(f"timeout={res.chat_timeout}s")
    print(f"elapsed={res.chat_ms:.0f}ms")
    if res.chat_error:
        print(f"error={res.chat_error}")
    print()
    print("TIMEOUT STACK")
    print("  HTTP connect          : 5.0s (httpx connection timeout)")
    print("  HTTP read / provider  : 60.0s (QwenProvider internal timeout)")
    print("  AI Gateway            : 60.0s (fallback skipped if primary >= 10.0s)")
    print(f"  Graph Qwen Deadline   : {res.chat_qwen_timeout}s (Central Dentist node budget)")
    print(f"  Global Chat Deadline  : {res.chat_request_timeout}s (chat_service overall budget)")
    print("  Subtasks (DB/Auth)    : 2.0s auth, 2.0s retrieval, 2.0s persistence")
    print()
    print("PROMPT SIZE (SAMPLE AUDIT)")
    print(f"  messages              : {res.payload_audit.get('messages', 0)}")
    print(f"  system_chars          : {res.payload_audit.get('system_chars', 0)}")
    print(f"  context_chars         : {res.payload_audit.get('context_chars', 0)}")
    print(f"  conversation_chars    : {res.payload_audit.get('conversation_chars', 0)}")
    print(f"  total_chars           : {res.payload_audit.get('total_chars', 0)}")
    print()
    print("LIKELY ROOT CAUSE")
    for cause in res.likely_root_causes:
        print(f"  * {cause}")
    print("=" * 48)
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DaantShaant Qwen Connectivity & Response Diagnostic Tool"
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="Diagnostic timeout in seconds (default: 30)")
    parser.add_argument("--repeat", type=int, default=3, help="Number of repeated sequential calls (default: 3)")
    parser.add_argument("--verbose", action="store_true", help="Print verbose debug logs")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="[%(levelname)s] %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    res = asyncio.run(run_all_diagnostics(timeout=args.timeout, repeat=args.repeat, verbose=args.verbose))
    print_report(res, verbose=args.verbose)
    return 0 if (res.dns_status == "PASS" and res.http_status == "PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
