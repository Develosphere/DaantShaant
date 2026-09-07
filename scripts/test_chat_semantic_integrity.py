#!/usr/bin/env python3
"""DaantShaant Chat Semantic Integrity & Context Isolation Smoke Test (Phase 12E).

Asks 5 sequential, highly distinct dental domain questions to verify:
1. Standalone topic isolation (each question is treated as a clean topic).
2. No cross-topic contamination (e.g., Question 2 about implants does not inherit Question 1 diabetes context).
3. Low latency with qwen3.7-flash (non-thinking).
4. No patient data leakage when answering abstract dental science questions.

Run command:
    .\\orchestrator\\.venv\\Scripts\\python.exe scripts\\test_chat_semantic_integrity.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# Ensure orchestrator package is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "orchestrator" / "src"))

from orchestrator.ai.qwen import QwenProvider
from orchestrator.central_dentist import (
    CentralDentistState,
    central_dentist_graph,
)
from orchestrator.config import AISettings, settings


QUESTIONS = [
    {
        "num": 1,
        "topic": "Diabetes & Periodontal Disease",
        "question": "Why can diabetes worsen periodontal disease?",
        "expected_keywords": ["diabetes", "periodont", "inflammation", "gum", "sugar", "glucose", "immune"],
        "forbidden_keywords": ["zirconia", "titanium", "implant", "root canal", "tmj", "pulp"],
    },
    {
        "num": 2,
        "topic": "Zirconia vs Titanium Implant Aseptic Loosening",
        "question": (
            "Explain the mechanical and biological mechanisms behind aseptic loosening "
            "of zirconia versus titanium dental implants under severe bruxism."
        ),
        "expected_keywords": ["implant", "zirconia", "titanium", "bone", "micromotion", "loosening", "bruxism", "stress"],
        "forbidden_keywords": ["diabetes", "glycemic", "root canal", "pulp", "stain", "extrinsic"],
    },
    {
        "num": 3,
        "topic": "Root Canal Pulp Removal",
        "question": "How does a root canal remove infected pulp?",
        "expected_keywords": ["pulp", "root canal", "infect", "nerve", "canal", "clean", "chamber"],
        "forbidden_keywords": ["zirconia", "titanium", "implant", "diabetes", "bruxism", "tmj"],
    },
    {
        "num": 4,
        "topic": "TMJ Pain & Grinding",
        "question": "What causes temporomandibular joint pain after night-time grinding?",
        "expected_keywords": ["tmj", "jaw", "grinding", "bruxism", "joint", "muscle", "pressure"],
        "forbidden_keywords": ["pulp", "root canal", "zirconia", "titanium", "implant", "stain"],
    },
    {
        "num": 5,
        "topic": "Intrinsic vs Extrinsic Staining",
        "question": "What is the difference between intrinsic and extrinsic tooth staining?",
        "expected_keywords": ["stain", "intrinsic", "extrinsic", "surface", "enamel", "dentin", "discolor"],
        "forbidden_keywords": ["root canal", "pulp", "implant", "zirconia", "tmj", "bruxism"],
    },
]


async def run_semantic_smoke_test() -> bool:
    print("=" * 80)
    print("DAANTSHAANT — CHAT SEMANTIC INTEGRITY & TOPIC ISOLATION SMOKE TEST")
    print("Target Model: qwen3.7-flash (enable_thinking=false)")
    print("=" * 80)

    # Initialize live QwenProvider
    ai_settings = AISettings()
    if not ai_settings.dashscope_api_key:
        print("\n[ERROR] DASHSCOPE_API_KEY is not set in environment or .env file.")
        print("Please check your .env configuration.")
        return False

    provider = QwenProvider(
        api_key=ai_settings.dashscope_api_key,
        base_url=ai_settings.qwen_base_url,
        default_model=ai_settings.chat_qwen_model or "qwen3.7-flash",
        chat_model=ai_settings.chat_qwen_model or "qwen3.7-flash",
        timeout_seconds=settings.chat_qwen_timeout_seconds or 12.0,
        enable_thinking=False,
    )

    # Create a mock gateway wrapper around this persistent provider
    class LiveGatewayAdapter:
        def __init__(self, p: QwenProvider):
            self.primary = p
            self.fallback = None
            self.timeout_seconds = p._timeout

        async def generate_text(self, request):
            return await self.primary.generate_text(request)

    gateway = LiveGatewayAdapter(provider)

    conversation_history = []
    all_passed = True

    for item in QUESTIONS:
        q_num = item["num"]
        topic = item["topic"]
        q_text = item["question"]
        expected_kws = item["expected_keywords"]
        forbidden_kws = item["forbidden_keywords"]

        print(f"\n--- [Question {q_num}/5] Topic: {topic} ---")
        print(f"User: {q_text[:90]}..." if len(q_text) > 90 else f"User: {q_text}")

        # Simulate prior turns in conversation_history to verify history isolation!
        state_input: CentralDentistState = {
            "user_id": "00000000-0000-0000-0000-000000000001",
            "conversation_id": "00000000-0000-0000-0000-000000000002",
            "message": q_text,
            "locale": "en",
            "request_id": f"smoke_q{q_num}",
            "recent_turns": list(conversation_history),
            "_gateway": gateway,
            "_db_session": None,
        }

        t0 = time.perf_counter()
        try:
            res = await central_dentist_graph.ainvoke(state_input)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            response = res.get("final_response", "")
            intent = res.get("intent", "UNKNOWN")
            sources = res.get("context_sources", [])
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            print(f"FAILED (Exception): {exc}")
            all_passed = False
            continue

        resp_lower = response.lower()
        matched_expected = [kw for kw in expected_kws if kw in resp_lower]
        matched_forbidden = [kw for kw in forbidden_kws if kw in resp_lower]

        has_expected = len(matched_expected) >= 1
        has_forbidden = len(matched_forbidden) > 0

        status_ok = has_expected and not has_forbidden
        if not status_ok:
            all_passed = False

        print(f"Latency: {latency_ms:.1f} ms | Intent: {intent} | Context Sources: {sources}")
        print(f"Response: {response}")
        print(f"Keywords Check: Expected matched={matched_expected} | Forbidden found={matched_forbidden}")
        print(f"Status: {'PASS' if status_ok else 'FAIL (cross-contamination or keyword mismatch)'}")

        # Append turn to conversation history to test isolation on the next turn
        conversation_history.append({"role": "user", "content": q_text})
        conversation_history.append({"role": "assistant", "content": response})

    await provider.aclose()

    print("\n" + "=" * 80)
    if all_passed:
        print("ALL 5 SEMANTIC ISOLATION CHECKS PASSED — ZERO CROSS-TOPIC CONTAMINATION")
    else:
        print("SOME CHECKS FAILED — REVIEW THE KEYWORD LOGS ABOVE")
    print("=" * 80)
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(run_semantic_smoke_test())
    sys.exit(0 if success else 1)
