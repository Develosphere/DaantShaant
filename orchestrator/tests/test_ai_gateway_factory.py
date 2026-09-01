"""Tests for the production AI gateway composition (Phase 2A.4).

FAKE keys only, ``httpx`` guarded where relevant, and ZERO external AI API
calls. Async is driven with ``asyncio.run`` to match the existing AI tests.
"""

from __future__ import annotations

import httpx
import pytest

from orchestrator.ai.exceptions import ProviderConfigurationError
from orchestrator.ai.factory import SUPPORTED_AI_PROVIDERS, create_ai_gateway, get_ai_gateway
from orchestrator.ai.gateway import AIGateway
from orchestrator.config import AISettings

FAKE_KEY = "sk-test-SECRET-NOT-A-REAL-KEY"
QWEN_BASE_URL = "https://example-workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"


def _settings(**overrides) -> AISettings:
    """Isolated settings: no .env lookup, fake credentials only."""
    base = {
        "primary_ai_provider": "qwen",
        "fallback_ai_provider": "gemini",
        "ai_request_timeout_seconds": 12.5,
        "dashscope_api_key": FAKE_KEY,
        "qwen_base_url": QWEN_BASE_URL,
        "qwen_default_model": "qwen3.7-plus",
        "qwen_chat_model": "qwen3.7-plus",
        "gemini_api_key": FAKE_KEY,
        "gemini_model": "gemini-flash-lite-latest",
        "gemini_base_url": "https://example.invalid/v1beta/models",
    }
    base.update(overrides)
    return AISettings(_env_file=None, **base)


# ---------------------------------------------------------------------------
# Locked policy composition
# ---------------------------------------------------------------------------
def test_qwen_is_primary_gemini_is_fallback():
    gateway = create_ai_gateway(_settings())

    assert isinstance(gateway, AIGateway)
    assert gateway.primary.name == "qwen"
    assert gateway.fallback is not None
    assert gateway.fallback.name == "gemini"
    assert gateway.timeout_seconds == 12.5


def test_supported_provider_names_are_documented():
    assert SUPPORTED_AI_PROVIDERS == ("qwen", "gemini")


def test_provider_selection_is_case_and_space_tolerant():
    gateway = create_ai_gateway(_settings(primary_ai_provider=" QwEn ", fallback_ai_provider="GEMINI"))
    assert gateway.primary.name == "qwen"
    assert gateway.fallback.name == "gemini"


def test_empty_fallback_composes_gateway_without_fallback():
    gateway = create_ai_gateway(_settings(fallback_ai_provider=""))
    assert gateway.primary.name == "qwen"
    assert gateway.fallback is None


# ---------------------------------------------------------------------------
# Configuration errors are loud, never substituted
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["openrouter", "gpt", "claude", "qwen3"])
def test_unknown_primary_raises_clear_configuration_error(bad):
    with pytest.raises(ProviderConfigurationError) as exc:
        create_ai_gateway(_settings(primary_ai_provider=bad))
    message = str(exc.value)
    assert "PRIMARY_AI_PROVIDER" in message
    assert bad in message
    assert "qwen" in message  # supported values are surfaced


def test_missing_primary_raises_instead_of_defaulting():
    with pytest.raises(ProviderConfigurationError, match="PRIMARY_AI_PROVIDER"):
        create_ai_gateway(_settings(primary_ai_provider=""))


def test_unknown_fallback_raises_clear_configuration_error():
    with pytest.raises(ProviderConfigurationError, match="FALLBACK_AI_PROVIDER"):
        create_ai_gateway(_settings(fallback_ai_provider="openrouter"))


def test_identical_primary_and_fallback_is_rejected():
    with pytest.raises(ProviderConfigurationError, match="must differ"):
        create_ai_gateway(_settings(primary_ai_provider="gemini", fallback_ai_provider="gemini"))


def test_missing_qwen_key_is_not_masked_by_fallback():
    with pytest.raises(ProviderConfigurationError, match="DASHSCOPE_API_KEY"):
        create_ai_gateway(_settings(dashscope_api_key=""))


def test_error_message_never_contains_the_api_key():
    with pytest.raises(ProviderConfigurationError) as exc:
        create_ai_gateway(_settings(dashscope_api_key=FAKE_KEY, qwen_base_url=""))
    assert FAKE_KEY not in str(exc.value)


# ---------------------------------------------------------------------------
# Import-time and composition-time cost
# ---------------------------------------------------------------------------
def test_composition_creates_no_http_client(monkeypatch):
    """Building providers must not open any network client."""

    def _boom(*args, **kwargs):  # pragma: no cover - guard must not be reached
        raise AssertionError("No HTTP client may be created while composing the gateway")

    monkeypatch.setattr(httpx, "AsyncClient", _boom)
    gateway = create_ai_gateway(_settings())
    assert gateway.primary.name == "qwen"


def test_get_ai_gateway_is_lazy_and_cached(monkeypatch):
    from orchestrator.ai import factory

    calls: list[int] = []

    def _fake_create(settings=None):
        calls.append(1)
        return create_ai_gateway(_settings())

    monkeypatch.setattr(factory, "create_ai_gateway", _fake_create)
    monkeypatch.setattr(factory, "_gateway", None)

    first = get_ai_gateway()
    second = get_ai_gateway()

    assert second is first
    assert len(calls) == 1
