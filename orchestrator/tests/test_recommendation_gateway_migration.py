"""Tests for the migrated product recommendation AI path (Phase 2A.5b).

The product recommendation graph's two text-generation calls —
``rank_recommendations`` (reranking) and ``generate_response_node`` (final
patient-facing message) — now run through the shared ``AIGateway``
(Qwen primary -> Gemini technical fallback). These tests use fake gateways and
in-memory providers only: ZERO external Qwen/Gemini/OpenRouter calls, and no
database / FAISS / embedding execution.
"""

from __future__ import annotations

import asyncio
import inspect
import json

import pytest

from orchestrator.ai import AIGateway
from orchestrator.ai.base import AIProvider
from orchestrator.ai.exceptions import (
    ProviderConfigurationError,
    ProviderInternalError,
    ProviderServerError,
)
from orchestrator.ai.schemas import AIResult, StructuredRequest, TextRequest, VisionRequest
from orchestrator.recommendation_ai_system import recommendation_agent, tools


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
RANKING_JSON = json.dumps(
    [
        {"product_id": "p1", "rank": 1, "recommendation_reason": "Best for sensitivity"},
        {"product_id": "p2", "rank": 2, "recommendation_reason": "Good backup"},
    ]
)

MARKDOWN_FENCED_RANKING = f"```json\n{RANKING_JSON}\n```"


class ScriptedProvider(AIProvider):
    """Minimal in-memory adapter: returns canned text or raises a typed error."""

    def __init__(self, name: str, *, content: str = "", failure: Exception | None = None) -> None:
        self.name = name
        self.default_model = f"{name}-configured-model"
        self.content = content
        self.failure = failure
        self.requests: list[TextRequest] = []

    async def generate_text(self, request: TextRequest) -> AIResult:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return AIResult(content=self.content, model=self.default_model)

    async def generate_vision(self, request: VisionRequest) -> AIResult:  # pragma: no cover
        raise NotImplementedError

    async def generate_structured(self, request: StructuredRequest) -> AIResult:  # pragma: no cover
        raise NotImplementedError


class SpyGateway:
    """Stands in for ``AIGateway`` so tests can inspect the normalized request."""

    def __init__(self, result: AIResult | None = None, failure: Exception | None = None) -> None:
        self.result = result or AIResult(content="", provider="qwen", model="qwen3.7-plus")
        self.failure = failure
        self.requests: list[TextRequest] = []

    async def generate_text(self, request: TextRequest) -> AIResult:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return self.result


def _run(coro):
    return asyncio.run(coro)


def _products() -> list[dict]:
    return [
        {
            "product_id": "p1",
            "name": "Sensi Toothpaste",
            "ai_description": "For sensitive teeth",
            "problems_solved": ["sensitivity"],
            "price": 7.5,
            "similarity_score": 0.9,
        },
        {
            "product_id": "p2",
            "name": "Soft Brush",
            "ai_description": "Gentle bristles",
            "problems_solved": ["gum pain"],
            "price": 3.0,
            "similarity_score": 0.6,
        },
    ]


def _response_state() -> dict:
    return {
        "issue": "sensitive teeth",
        "patient_id": "patient-1",
        "session_id": "session-1",
        "candidates": [],
        "detailed_candidates": [],
        "ranked_candidates": [
            {
                "product_id": "p1",
                "name": "Sensi Toothpaste",
                "price": 7.5,
                "recommendation_reason": "Best for sensitivity",
                "problems_solved": ["sensitivity"],
            },
            {
                "product_id": "p2",
                "name": "Soft Brush",
                "price": 3.0,
                "recommendation_reason": "Gentle on gums",
                "problems_solved": ["gum pain"],
            },
        ],
        "final_output": "",
    }


# ---------------------------------------------------------------------------
# 1. rank_recommendations uses AIGateway (and never OpenRouter)
# ---------------------------------------------------------------------------
def test_rank_uses_gateway(monkeypatch):
    import orchestrator.openrouter_client as legacy_openrouter

    def _never(*args, **kwargs):  # pragma: no cover - guard must not be reached
        raise AssertionError("Migrated recommendation path must not call OpenRouter")

    monkeypatch.setattr(legacy_openrouter.openrouter_client, "generate_chat_response", _never)

    gateway = SpyGateway(result=AIResult(content=RANKING_JSON, provider="qwen", model="qwen3.7-plus"))
    ranked = _run(tools.rank_recommendations(_products(), "sensitive teeth", gateway=gateway))

    assert [r["product_id"] for r in ranked] == ["p1", "p2"]
    assert ranked[0]["recommendation_reason"] == "Best for sensitivity"
    assert len(gateway.requests) == 1


# ---------------------------------------------------------------------------
# 2. Primary (Qwen) success preserves response behavior
# ---------------------------------------------------------------------------
def test_rank_primary_success_preserves_behavior():
    qwen = ScriptedProvider("qwen", content=RANKING_JSON)
    gemini = ScriptedProvider("gemini", content="MUST NOT BE USED")
    gateway = AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5)

    ranked = _run(tools.rank_recommendations(_products(), "sensitive teeth", gateway=gateway))

    assert [r["product_id"] for r in ranked] == ["p1", "p2"]
    assert qwen.requests and not gemini.requests


# ---------------------------------------------------------------------------
# 3. Qwen technical failure -> Gemini fallback succeeds
# ---------------------------------------------------------------------------
def test_rank_qwen_failure_falls_back_to_gemini():
    qwen = ScriptedProvider("qwen", failure=ProviderServerError("Qwen HTTP 503"))
    gemini = ScriptedProvider("gemini", content=RANKING_JSON)
    gateway = AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5)

    ranked = _run(tools.rank_recommendations(_products(), "sensitive teeth", gateway=gateway))

    assert [r["product_id"] for r in ranked] == ["p1", "p2"]
    assert qwen.requests and gemini.requests
    assert gemini.requests[0].model is None  # provider resolves GEMINI_MODEL itself


# ---------------------------------------------------------------------------
# 4. Prompt / product context reaches the gateway
# ---------------------------------------------------------------------------
def test_rank_prompt_context_reaches_gateway():
    gateway = SpyGateway(result=AIResult(content=RANKING_JSON))
    _run(tools.rank_recommendations(_products(), "sensitive teeth", gateway=gateway))

    request = gateway.requests[0]
    assert isinstance(request, TextRequest)
    assert [m.role for m in request.messages] == ["system", "user"]
    assert request.messages[0].content == "You are a dental product ranking expert. Return only JSON."
    assert "sensitive teeth" in request.messages[1].content
    assert "Sensi Toothpaste" in request.messages[1].content
    assert request.temperature == 0.2
    assert request.max_tokens == 600
    assert request.model is None


def test_generate_response_prompt_context_reaches_gateway(monkeypatch):
    gateway = SpyGateway(result=AIResult(content="Here are your recommendations.", provider="qwen"))
    monkeypatch.setattr(recommendation_agent, "_gateway", gateway)

    out = _run(recommendation_agent.generate_response_node(_response_state()))

    assert out == {"final_output": "Here are your recommendations."}
    request = gateway.requests[0]
    assert request.messages[0].content == "You are DentAssist, a friendly dental product advisor."
    assert "sensitive teeth" in request.messages[1].content
    assert "Sensi Toothpaste" in request.messages[1].content
    assert request.temperature == 0.4
    assert request.max_tokens == 800
    assert request.model is None


# ---------------------------------------------------------------------------
# 5. Product LangGraph topology unchanged
# ---------------------------------------------------------------------------
def test_product_langgraph_topology_preserved():
    graph = recommendation_agent.recommendation_graph.get_graph()
    node_names = set(graph.nodes.keys())
    assert {
        "search_products",
        "get_details",
        "rank",
        "log_session",
        "generate_response",
        "terminate_low_similarity",
    } <= node_names

    edges = {(e.source, e.target) for e in graph.edges}
    assert ("get_details", "rank") in edges
    assert ("rank", "log_session") in edges
    assert ("log_session", "generate_response") in edges


# ---------------------------------------------------------------------------
# 6. Migrated modules no longer import the legacy provider
# ---------------------------------------------------------------------------
def test_recommendation_modules_do_not_import_legacy_provider():
    for module in (recommendation_agent, tools):
        source = inspect.getsource(module)
        assert "openrouter_client" not in source
        assert "llm_provider" not in source


# ---------------------------------------------------------------------------
# 7. Config / programming errors are NOT silently swallowed
# ---------------------------------------------------------------------------
def test_rank_configuration_error_propagates():
    qwen = ScriptedProvider("qwen", failure=ProviderConfigurationError("QWEN_API_KEY missing"))
    gemini = ScriptedProvider("gemini", content="MUST NOT BE REACHED")
    gateway = AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5)

    with pytest.raises(ProviderConfigurationError):
        _run(tools.rank_recommendations(_products(), "issue", gateway=gateway))
    assert not gemini.requests


def test_generate_response_programming_error_propagates(monkeypatch):
    gateway = SpyGateway(failure=ProviderInternalError("bug in request construction"))
    monkeypatch.setattr(recommendation_agent, "_gateway", gateway)

    with pytest.raises(ProviderInternalError):
        _run(recommendation_agent.generate_response_node(_response_state()))


# ---------------------------------------------------------------------------
# 8. Deterministic fallback remains intact on full technical failure
# ---------------------------------------------------------------------------
def test_rank_double_failure_uses_deterministic_fallback():
    qwen = ScriptedProvider("qwen", failure=ProviderServerError("down"))
    gemini = ScriptedProvider("gemini", failure=ProviderServerError("also down"))
    gateway = AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5)

    ranked = _run(tools.rank_recommendations(_products(), "sensitive teeth", gateway=gateway))

    assert [r["product_id"] for r in ranked] == ["p1", "p2"]
    assert ranked[0]["rank"] == 1
    assert "Addresses sensitive teeth" in ranked[0]["recommendation_reason"]


def test_generate_response_double_failure_uses_template_fallback(monkeypatch):
    qwen = ScriptedProvider("qwen", failure=ProviderServerError("down"))
    gemini = ScriptedProvider("gemini", failure=ProviderServerError("also down"))
    gateway = AIGateway(primary=qwen, fallback=gemini, timeout_seconds=5)
    monkeypatch.setattr(recommendation_agent, "_gateway", gateway)

    out = _run(recommendation_agent.generate_response_node(_response_state()))

    assert "🦷 Recommended for: sensitive teeth" in out["final_output"]
    assert "Sensi Toothpaste" in out["final_output"]


def test_generate_response_empty_gateway_uses_template_fallback(monkeypatch):
    gateway = SpyGateway(result=AIResult(content="", provider="qwen", model="qwen-model"))
    monkeypatch.setattr(recommendation_agent, "_gateway", gateway)

    out = _run(recommendation_agent.generate_response_node(_response_state()))

    assert "Sensi Toothpaste" in out["final_output"]


# ---------------------------------------------------------------------------
# Extra: markdown-fenced ranking JSON is still parsed
# ---------------------------------------------------------------------------
def test_rank_markdown_fenced_json_parsed():
    gateway = SpyGateway(result=AIResult(content=MARKDOWN_FENCED_RANKING, provider="qwen"))
    ranked = _run(tools.rank_recommendations(_products(), "sensitive teeth", gateway=gateway))
    assert [r["product_id"] for r in ranked] == ["p1", "p2"]
