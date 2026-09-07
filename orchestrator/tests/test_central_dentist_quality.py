"""Quality and tone guard tests for Central Dentist (Phase 12A Final).

Asserts that Central Dentist responses are clean, direct, and free from
robotic LLM slop phrasing.
"""

import pytest

from orchestrator.central_dentist.prompts import clean_response


def test_clean_response_strips_ai_slop_preambles():
    slop_1 = "As an AI language model, your scan shows tooth discoloration."
    cleaned_1 = clean_response(slop_1)
    assert "as an ai" not in cleaned_1.lower()
    assert "your scan shows tooth discoloration" in cleaned_1.lower()

    slop_2 = "Based on the information provided, it is important to note that your scan flagged tartar."
    cleaned_2 = clean_response(slop_2)
    assert "based on the information provided" not in cleaned_2.lower()
    assert "it is important to note that" not in cleaned_2.lower()
    assert "your scan flagged tartar" in cleaned_2.lower()

    slop_3 = "I understand your concern. Gums bleed when irritated by plaque."
    cleaned_3 = clean_response(slop_3)
    assert "i understand your concern" not in cleaned_3.lower()
    assert "gums bleed" in cleaned_3.lower()


def test_clean_response_strips_markdown_formatting():
    raw = "### Summary\n**Your latest scan** flagged *calculus* at 80%."
    cleaned = clean_response(raw)
    assert "**" not in cleaned
    assert "###" not in cleaned
    assert "*calculus*" not in cleaned
    assert "calculus" in cleaned
    assert "Your latest scan flagged calculus at 80%." in cleaned
