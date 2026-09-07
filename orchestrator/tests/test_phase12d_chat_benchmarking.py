"""Unit and integration tests for Phase 12D Chat LLM Benchmarking & Provider Separation.

Validates:
1. CHAT_LLM_PROVIDER=qwen -> Qwen used
2. CHAT_LLM_PROVIDER=gemini -> Gemini used
3. Qwen chat thinking false -> request payload contains enable_thinking=false
4. Clinical report Qwen request -> unaffected (no enable_thinking in payload)
5. qwen3.7-flash -> accepted as chat model
6. gemini-flash-lite-latest -> accepted as Gemini chat model
7. Fallback ordering configurable (qwen->gemini, gemini->qwen, qwen->none)
8. Qwen reasoning metadata detection (reasoning_content & reasoning_tokens)
9. Follow-up reference resolution ("Why did it flag that?", "What does that mean?", "Is that serious?")
10. General dental questions remain LLM-driven (sensitivity, bleeding, bad breath never fast-pathed)
11. Zero Hugging Face regression

Strictly mocked HTTP transports. ZERO external network or provider calls.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from orchestrator.ai.exceptions import ProviderConfigurationError
from orchestrator.ai.factory import (
    create_ai_gateway,
    create_chat_ai_gateway,
)
from orchestrator.ai.gemini import GeminiProvider
from orchestrator.ai.qwen import QwenProvider
from orchestrator.ai.schemas import ChatMessage, TextRequest
from orchestrator.central_dentist import CentralDentistIntent, analyze_message
from orchestrator.central_dentist.graph import (
    CentralDentistState,
    retrieve_conversation_context,
)
from orchestrator.central_dentist.retrieval import FindingItem, ScanSummary
from orchestrator.clinical.report_generator import generate_clinical_report_text
from orchestrator.config import AISettings

FAKE_KEY = "sk-fake-test-key-12345"
FAKE_BASE_URL = "https://mock-workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
FAKE_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"


def _make_settings(**overrides) -> AISettings:
    base = {
        "primary_ai_provider": "qwen",
        "fallback_ai_provider": "gemini",
        "dashscope_api_key": FAKE_KEY,
        "qwen_base_url": FAKE_BASE_URL,
        "qwen_default_model": "qwen3.7-plus",
        "qwen_chat_model": "qwen3.7-plus",
        "gemini_api_key": FAKE_KEY,
        "gemini_model": "gemini-flash-lite-latest",
        "chat_llm_provider": "qwen",
        "chat_fallback_provider": "gemini",
        "chat_qwen_model": "qwen3.7-flash",
        "chat_qwen_enable_thinking": False,
        "chat_gemini_model": "gemini-flash-lite-latest",
    }
    base.update(overrides)
    return AISettings(_env_file=None, **base)


# ---------------------------------------------------------------------------
# 1. Provider Selection: Qwen vs Gemini
# ---------------------------------------------------------------------------

def test_chat_llm_provider_qwen_uses_qwen():
    cfg = _make_settings(chat_llm_provider="qwen", chat_fallback_provider="gemini")
    gateway = create_chat_ai_gateway(cfg)
    assert gateway.primary.name == "qwen"
    assert gateway.primary.default_model == "qwen3.7-flash"
    assert gateway.fallback is not None
    assert gateway.fallback.name == "gemini"
    assert gateway.fallback.default_model == "gemini-flash-lite-latest"


def test_chat_llm_provider_gemini_uses_gemini():
    cfg = _make_settings(chat_llm_provider="gemini", chat_fallback_provider="qwen")
    gateway = create_chat_ai_gateway(cfg)
    assert gateway.primary.name == "gemini"
    assert gateway.primary.default_model == "gemini-flash-lite-latest"
    assert gateway.fallback is not None
    assert gateway.fallback.name == "qwen"
    assert gateway.fallback.default_model == "qwen3.7-flash"


# ---------------------------------------------------------------------------
# 2. Thinking Control: Qwen enable_thinking
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_qwen_chat_thinking_false_payload_contains_enable_thinking_false():
    captured_payload: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test-1",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Brushing twice daily is key."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
        )

    transport = httpx.MockTransport(handler)
    provider = QwenProvider(
        settings=_make_settings(),
        enable_thinking=False,
        transport=transport,
    )

    req = TextRequest(
        prompt="How do I brush?",
        extra_body={"enable_thinking": False},
    )
    result = await provider.generate_text(req)

    assert result.content == "Brushing twice daily is key."
    assert "enable_thinking" in captured_payload
    assert captured_payload["enable_thinking"] is False


@pytest.mark.anyio
async def test_qwen_chat_thinking_true_payload_contains_enable_thinking_true():
    captured_payload: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test-2",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Brush carefully.",
                            "reasoning_content": "Analyze oral hygiene query...",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 10,
                    "total_tokens": 20,
                    "reasoning_tokens": 15,
                },
            },
        )

    transport = httpx.MockTransport(handler)
    provider = QwenProvider(
        settings=_make_settings(),
        enable_thinking=True,
        transport=transport,
    )

    req = TextRequest(
        prompt="How do I brush?",
        extra_body={"enable_thinking": True},
    )
    result = await provider.generate_text(req)

    assert "enable_thinking" in captured_payload
    assert captured_payload["enable_thinking"] is True
    assert result.raw_metadata is not None
    assert result.raw_metadata.get("reasoning_content") == "Analyze oral hygiene query..."
    assert result.raw_metadata.get("reasoning_tokens") == 15


# ---------------------------------------------------------------------------
# 3. Clinical Report Path: 100% Unaffected
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_clinical_report_qwen_request_unaffected():
    captured_payload: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-report-1",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({
                                "summary": "Routine screening summary.",
                                "finding_explanations": ["Visible localized tooth discoloration."],
                                "recommended_steps": ["Schedule routine checkup."],
                                "professional_notes": "Routine evaluation.",
                            }),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 40, "total_tokens": 90},
            },
        )

    transport = httpx.MockTransport(handler)
    cfg = _make_settings(ai_request_timeout_seconds=60.0)

    # Standard production clinical gateway
    provider = QwenProvider(settings=cfg, transport=transport)
    from orchestrator.ai.gateway import AIGateway
    gateway = AIGateway(primary=provider, timeout_seconds=60.0)

    report_text = await generate_clinical_report_text(
        findings=[{"label": "discoloration", "confidence": 0.76}],
        triage={"condition_summary": "Possible discoloration", "urgency_level": "routine"},
        gateway=gateway,
    )

    assert "Routine screening summary." in report_text.summary
    # Clinical report payload MUST NOT have enable_thinking injected
    assert "enable_thinking" not in captured_payload


# ---------------------------------------------------------------------------
# 4. Model Acceptance: qwen3.7-flash and gemini-flash-lite-latest
# ---------------------------------------------------------------------------

def test_qwen_flash_accepted_as_chat_model():
    cfg = _make_settings(
        chat_llm_provider="qwen",
        chat_qwen_model="qwen3.7-flash",
        chat_qwen_enable_thinking=False,
    )
    gateway = create_chat_ai_gateway(cfg)
    assert gateway.primary.name == "qwen"
    assert gateway.primary.default_model == "qwen3.7-flash"


def test_qwen_plus_accepted_as_explicit_override():
    cfg = _make_settings(
        chat_llm_provider="qwen",
        chat_qwen_model="qwen3.7-plus",
        chat_qwen_enable_thinking=False,
    )
    gateway = create_chat_ai_gateway(cfg)
    assert gateway.primary.name == "qwen"
    assert gateway.primary.default_model == "qwen3.7-plus"


def test_gemini_flash_lite_latest_accepted_as_chat_model():
    cfg = _make_settings(
        chat_llm_provider="gemini",
        chat_fallback_provider="qwen",
        chat_gemini_model="gemini-flash-lite-latest",
    )
    gateway = create_chat_ai_gateway(cfg)
    assert gateway.primary.name == "gemini"
    assert gateway.primary.default_model == "gemini-flash-lite-latest"


# ---------------------------------------------------------------------------
# 5. Configurable Fallback Policy
# ---------------------------------------------------------------------------

def test_fallback_ordering_configurable():
    # 1. Qwen primary, Gemini fallback
    gw1 = create_chat_ai_gateway(_make_settings(chat_llm_provider="qwen", chat_fallback_provider="gemini"))
    assert gw1.primary.name == "qwen"
    assert gw1.fallback.name == "gemini"

    # 2. Gemini primary, Qwen fallback
    gw2 = create_chat_ai_gateway(_make_settings(chat_llm_provider="gemini", chat_fallback_provider="qwen"))
    assert gw2.primary.name == "gemini"
    assert gw2.fallback.name == "qwen"

    # 3. No fallback
    gw3 = create_chat_ai_gateway(_make_settings(chat_llm_provider="qwen", chat_fallback_provider=""))
    assert gw3.primary.name == "qwen"
    assert gw3.fallback is None

    # 4. Identical primary and fallback rejected
    with pytest.raises(ProviderConfigurationError, match="must differ"):
        create_chat_ai_gateway(_make_settings(chat_llm_provider="qwen", chat_fallback_provider="qwen"))


# ---------------------------------------------------------------------------
# 6. Follow-up Reference Resolution
# ---------------------------------------------------------------------------

def test_follow_up_reference_nlp_classification():
    # "Why did it flag that?" (scan/screening reference)
    res1 = analyze_message("Why did it flag that?")
    assert res1.intent == CentralDentistIntent.FOLLOW_UP_REFERENCE

    # "Why did my scan flag that?" (scan/screening reference)
    res2 = analyze_message("Why did my scan flag that?")
    assert res2.intent == CentralDentistIntent.FOLLOW_UP_REFERENCE

    # "What does that mean?" with scan context
    res3 = analyze_message("What does that mean?", has_recent_scan_context=True)
    assert res3.intent == CentralDentistIntent.FOLLOW_UP_REFERENCE

    # "Is that serious?" with active finding
    res4 = analyze_message("Is that serious?", active_finding="discoloration")
    assert res4.intent == CentralDentistIntent.FOLLOW_UP_REFERENCE


@pytest.mark.anyio
async def test_follow_up_reference_resolves_finding_from_latest_scan():
    latest_scan = ScanSummary(
        scan_id="scan-mock-123",
        created_at=datetime.now(timezone.utc),
        input_mode="upload",
        status="completed",
        verdict="possible_discoloration",
        urgency_level="routine",
        confidence=0.76,
        findings=[
            FindingItem(
                finding_code="discoloration",
                region="general",
                observation="Possible tooth discoloration",
                confidence=0.76,
            )
        ],
    )

    state: CentralDentistState = {
        "message": "Why did my scan flag that?",
        "latest_scan": latest_scan,
        "recent_turns": [],
        "active_finding": None,
    }

    turn_context = await retrieve_conversation_context(state)
    # Finding must be grounded in latest scan!
    assert turn_context["active_finding"] == "discoloration"


# ---------------------------------------------------------------------------
# 7. General Dental Questions Remain LLM-Driven (No Symptom Hardcoding)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "question",
    [
        "Why can a tooth become sensitive to cold water?",
        "What can cause gums to bleed while brushing?",
        "Why do I have bad breath in the morning?",
        "What is the difference between plaque and tartar?",
        "Explain why cavities form in simple language.",
    ],
)
def test_general_dental_questions_are_not_fast_pathed(question: str):
    res = analyze_message(question)
    # These must NOT be intercepted by deterministic fast path handlers
    assert res.is_fast_path_candidate is False
    assert res.fast_path_type is None


# ---------------------------------------------------------------------------
# 8. No Hugging Face Regression
# ---------------------------------------------------------------------------

def test_no_huggingface_regression():
    for mod in ["transformers", "torch", "sentence_transformers", "faiss"]:
        assert mod not in sys.modules, f"Forbidden legacy library {mod} detected in memory!"
