"""Tests for the provider-independent deterministic dental fallback (Phase 2A.5c).

Verifies that:
- The fallback behavior is preserved after relocation from ``llm_provider``.
- Importing the fallback module does NOT instantiate any AI provider or HTTP client.
"""

from __future__ import annotations

import sys


def test_active_issue_match_returns_exact_response():
    from orchestrator.ai.fallbacks import get_deterministic_fallback

    result = get_deterministic_fallback("anything", active_issue="bleeding gums")
    assert result.startswith("Gums often bleed because plaque irritates")


def test_keyword_scan_matches_bleeding():
    from orchestrator.ai.fallbacks import get_deterministic_fallback

    result = get_deterministic_fallback("my gums bleed when I brush")
    assert "plaque" in result.lower()
    assert "gum" in result.lower()


def test_keyword_scan_matches_toothache():
    from orchestrator.ai.fallbacks import get_deterministic_fallback

    result = get_deterministic_fallback("I have a terrible toothache")
    assert "toothache" in result.lower() or "cavities" in result.lower()


def test_keyword_scan_matches_sensitivity():
    from orchestrator.ai.fallbacks import get_deterministic_fallback

    result = get_deterministic_fallback("my teeth are really sensitive to cold")
    assert "sensitivity" in result.lower() or "enamel" in result.lower()


def test_unknown_message_returns_generic_fallback():
    from orchestrator.ai.fallbacks import get_deterministic_fallback, GENERIC_DENTAL_FALLBACK

    result = get_deterministic_fallback("hello how are you")
    assert result == GENERIC_DENTAL_FALLBACK


def test_active_issue_takes_priority_over_keyword():
    from orchestrator.ai.fallbacks import get_deterministic_fallback, DENTAL_FALLBACKS

    # Message mentions "bleed" but active_issue is "toothache"
    result = get_deterministic_fallback("my gums bleed", active_issue="toothache")
    assert result == DENTAL_FALLBACKS["toothache"]


def test_unknown_active_issue_falls_through_to_keyword():
    from orchestrator.ai.fallbacks import get_deterministic_fallback

    result = get_deterministic_fallback("my tooth hurts", active_issue="nonexistent_issue")
    assert "toothache" in result.lower() or "cavities" in result.lower()


def test_importing_fallback_module_creates_no_provider_or_client():
    """Importing the fallback module must not construct any AI provider or HTTP client."""
    # Remove the module from cache to force a fresh import
    mods_to_remove = [key for key in sys.modules if key.startswith("orchestrator.ai.fallbacks")]
    for mod in mods_to_remove:
        del sys.modules[mod]

    # Snapshot modules that should NOT be imported
    blocked = {"orchestrator.ai.qwen", "orchestrator.ai.gemini", "orchestrator.openrouter_client"}
    before = set(sys.modules)

    import orchestrator.ai.fallbacks  # noqa: F401

    newly_imported = set(sys.modules) - before
    assert not newly_imported.intersection(blocked), (
        f"Fallback module must not pull in provider/client modules: {newly_imported.intersection(blocked)}"
    )


def test_fallback_module_has_no_httpx_dependency():
    """The fallback module source must not import httpx or any networking library."""
    import inspect
    from orchestrator.ai import fallbacks

    source = inspect.getsource(fallbacks)
    assert "httpx" not in source
    assert "import requests" not in source
    assert "openrouter" not in source.lower()
