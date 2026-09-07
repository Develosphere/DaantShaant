"""Unit tests for scripts/diagnose_qwen.py offline validation (Phase 12C/D).

Verifies offline behavior with MockTransport:
- API key is never printed or echoed
- HTTP 401 classified correctly
- HTTP 403 classified correctly
- Timeout classified correctly
- Successful QWEN_OK parsed
- Timing summary (min/max/avg) calculated correctly
- Zero real external network calls.
"""

from __future__ import annotations

import asyncio
import io
from contextlib import redirect_stdout
from pathlib import Path

import httpx
import pytest

# Ensure scripts directory is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from diagnose_qwen import (  # noqa: E402
    DiagnosticResult,
    classify_http_error,
    print_report,
    run_all_diagnostics,
    run_test_a_config,
    run_test_b_dns,
    run_test_c_http,
    run_test_d_raw_qwen,
    run_test_e_reused_latency,
    run_test_f_project_provider,
    run_test_g_scan_config,
    run_test_h_chat_config,
)
from orchestrator.central_dentist.prompts import audit_chat_prompt_size  # noqa: E402
from orchestrator.config import AISettings  # noqa: E402


SECRET_KEY = "sk-super-secret-test-dashscope-key-12345"


def test_classify_http_errors():
    """Verify clean classification of HTTP status codes without leaking secrets."""
    e401 = classify_http_error(401, "Invalid token")
    assert "401" in e401
    assert "Authentication Rejected" in e401
    assert "DASHSCOPE_API_KEY" in e401

    e403 = classify_http_error(403, "Quota exhausted")
    assert "403" in e403
    assert "Quota/Permission Denied" in e403

    e404 = classify_http_error(404, "Not found")
    assert "404" in e404

    e429 = classify_http_error(429, "Too many requests")
    assert "429" in e429
    assert "Rate Limit" in e429

    e500 = classify_http_error(500, "Internal Server Error")
    assert "500" in e500
    assert "Server Error" in e500


def test_test_a_config_sanitization():
    """Verify that config parsing extracts host/model without leaking secrets."""
    cfg = AISettings(
        dashscope_api_key=SECRET_KEY,
        qwen_base_url="https://test-workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        qwen_chat_model="qwen3.7-plus",
    )
    res = run_test_a_config(cfg)
    assert res.base_url_host == "test-workspace.ap-southeast-1.maas.aliyuncs.com"
    assert res.chat_model == "qwen3.7-plus"
    assert res.api_key_configured is True
    # Crucial: the raw secret is never stored on the result object
    for attr, val in res.__dict__.items():
        assert SECRET_KEY not in str(val), f"Secret found in attribute {attr}"


def test_test_b_dns():
    """Verify DNS resolution reporting."""
    status, elapsed, ips, err = run_test_b_dns("localhost")
    assert status == "PASS"
    assert elapsed >= 0.0
    assert len(ips) > 0
    assert err == ""

    # Test failure case
    status_fail, _, _, err_fail = run_test_b_dns("invalid-nonexistent-domain-xyz-12345.test")
    assert status_fail == "FAIL"
    assert "failed" in err_fail.lower() or "error" in err_fail.lower()


def test_test_c_http_success_and_failures():
    """Verify HTTP connectivity probe classification with MockTransport."""
    async def _test():
        # 200 OK
        transport_200 = httpx.MockTransport(lambda req: httpx.Response(200, json={"data": []}))
        status, code, elapsed, err = await run_test_c_http(
            "https://example.com/v1", SECRET_KEY, transport=transport_200
        )
        assert status == "PASS"
        assert code == 200
        assert err == ""

        # 401 Unauthorized
        transport_401 = httpx.MockTransport(lambda req: httpx.Response(401, json={"error": "unauthorized"}))
        status, code, elapsed, err = await run_test_c_http(
            "https://example.com/v1", SECRET_KEY, transport=transport_401
        )
        assert status == "FAIL"
        assert code == 401
        assert "Authentication Rejected" in err

        # 403 Forbidden / Quota
        transport_403 = httpx.MockTransport(lambda req: httpx.Response(403, json={"error": "quota"}))
        status, code, elapsed, err = await run_test_c_http(
            "https://example.com/v1", SECRET_KEY, transport=transport_403
        )
        assert status == "FAIL"
        assert code == 403
        assert "Quota/Permission Denied" in err

        # 404 Endpoint probe
        transport_404 = httpx.MockTransport(lambda req: httpx.Response(404, json={"error": "not found"}))
        status, code, elapsed, err = await run_test_c_http(
            "https://example.com/v1", SECRET_KEY, transport=transport_404
        )
        assert status == "PASS"  # Probe passed connectivity check
        assert code == 404

    asyncio.run(_test())


def test_test_d_raw_qwen_success_and_timeout():
    """Verify minimal raw call parses QWEN_OK and handles timeout."""
    async def _test():
        # Success
        payload = {
            "choices": [{"message": {"content": "QWEN_OK", "role": "assistant"}}],
            "model": "qwen3.7-plus",
        }
        transport_ok = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
        status, model, elapsed, text, err = await run_test_d_raw_qwen(
            "https://example.com/v1", SECRET_KEY, "qwen3.7-plus", transport=transport_ok
        )
        assert status == "PASS"
        assert text == "QWEN_OK"
        assert model == "qwen3.7-plus"
        assert err == ""

        # Timeout
        def timeout_handler(req):
            raise httpx.ReadTimeout("Mock read timeout")

        transport_timeout = httpx.MockTransport(timeout_handler)
        status_to, _, _, _, err_to = await run_test_d_raw_qwen(
            "https://example.com/v1", SECRET_KEY, "qwen3.7-plus", transport=transport_timeout
        )
        assert status_to == "FAIL"
        assert "timeout" in err_to.lower()

    asyncio.run(_test())


def test_test_e_reused_latency_math():
    """Verify repeated latency collects all turns and calculates min/max/avg."""
    async def _test():
        call_count = 0

        def mock_latency(req):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"choices": [{"message": {"content": "QWEN_OK"}}]})

        transport = httpx.MockTransport(mock_latency)
        status, calls, min_ms, max_ms, avg_ms = await run_test_e_reused_latency(
            "https://example.com/v1", SECRET_KEY, "qwen3.7-plus", repeat_count=3, transport=transport
        )
        assert status == "PASS"
        assert len(calls) == 3
        assert call_count == 3
        assert min_ms <= avg_ms <= max_ms

    asyncio.run(_test())


def test_test_f_project_provider():
    """Verify project provider execution with MockTransport."""
    async def _test():
        payload = {
            "choices": [{"message": {"content": "QWEN_PROVIDER_OK", "role": "assistant"}}],
            "model": "qwen3.7-plus",
        }
        transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
        cfg = AISettings(
            dashscope_api_key=SECRET_KEY,
            qwen_base_url="https://example.com/v1",
            qwen_chat_model="qwen3.7-plus",
        )
        status, model, elapsed, text, err = await run_test_f_project_provider(cfg, transport=transport)
        assert status == "PASS"
        assert text == "QWEN_PROVIDER_OK"
        assert err == ""

    asyncio.run(_test())


def test_test_g_scan_and_h_chat_configs():
    """Verify scan and chat provider configuration runners."""
    async def _test():
        payload_scan = {
            "choices": [{"message": {"content": "QWEN_SCAN_OK", "role": "assistant"}}],
            "model": "qwen3.7-plus",
        }
        transport_scan = httpx.MockTransport(lambda req: httpx.Response(200, json=payload_scan))
        cfg = AISettings(
            dashscope_api_key=SECRET_KEY,
            qwen_base_url="https://example.com/v1",
            qwen_chat_model="qwen3.7-plus",
        )
        status_g, model_g, to_g, ms_g, err_g = await run_test_g_scan_config(cfg, transport=transport_scan)
        assert status_g == "PASS"
        assert to_g == 60.0

        payload_chat = {
            "choices": [{"message": {"content": "QWEN_CHAT_OK", "role": "assistant"}}],
            "model": "qwen3.7-plus",
        }
        transport_chat = httpx.MockTransport(lambda req: httpx.Response(200, json=payload_chat))
        status_h, model_h, to_h, ms_h, err_h = await run_test_h_chat_config(cfg, transport=transport_chat)
        assert status_h == "PASS"
        assert to_h == 12.0

    asyncio.run(_test())


def test_audit_chat_prompt_size():
    """Verify prompt audit calculates character and message metrics."""
    res = audit_chat_prompt_size(
        system_prompt="Short system prompt",
        grounded_context="Patient has tartar and cavity",
        user_message="What should I do?",
        recent_turns=[{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}],
    )
    assert res["messages"] == 4  # system + 2 turns + user
    assert res["system_chars"] == len("Short system prompt")
    assert res["context_chars"] == len("Patient has tartar and cavity")
    assert res["conversation_chars"] > 0
    assert res["total_chars"] == res["system_chars"] + res["context_chars"] + len("What should I do?")


def test_print_report_never_leaks_secrets():
    """Verify the formatted stdout report NEVER contains API keys or secrets."""
    res = DiagnosticResult(
        base_url_host="test.aliyuncs.com",
        base_url_path="/compatible-mode/v1",
        default_model="qwen3.7-plus",
        chat_model="qwen3.7-plus",
        vision_model="qwen3.7-plus",
        api_key_configured=True,
        dns_status="PASS",
        dns_ms=12.5,
        http_status="PASS",
        http_code=200,
        http_ms=150.0,
        raw_status="PASS",
        raw_response="QWEN_OK",
        raw_ms=850.0,
        reused_calls=[1200.0, 450.0, 430.0],
        reused_min_ms=430.0,
        reused_max_ms=1200.0,
        reused_avg_ms=693.33,
        provider_status="PASS",
        provider_ms=450.0,
        scan_status="PASS",
        scan_model="qwen3.7-plus",
        scan_timeout=60.0,
        scan_ms=460.0,
        chat_status="PASS",
        chat_test_model="qwen3.7-plus",
        chat_timeout=8.0,
        chat_ms=470.0,
        payload_audit={"messages": 4, "total_chars": 1200},
        likely_root_causes=["CONNECTIVITY HEALTHY"],
    )

    buf = io.StringIO()
    with redirect_stdout(buf):
        print_report(res)
    output = buf.getvalue()

    assert "DAANTSHAANT QWEN DIAGNOSTIC" in output
    assert "QWEN_OK" in output
    assert "test.aliyuncs.com" in output
    assert SECRET_KEY not in output
    assert "Bearer" not in output
    assert "Authorization" not in output
