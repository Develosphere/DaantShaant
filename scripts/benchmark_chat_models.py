#!/usr/bin/env python3
"""DaantShaant Chat-Only LLM Benchmark & Quality Evaluation Tool (Phase 12D).

Benchmarks candidate chat models against realistic dental questions and grounded scan follow-ups:
- Config A: qwen3.7-plus (thinking=True)
- Config B: qwen3.7-plus (thinking=False)
- Config C: qwen3.7-flash (thinking=False)
- Config D: gemini-flash-lite-latest (Gemini provider)

Measures:
- Latency: Min, Avg, Max (total_ms and time_to_headers where available)
- Thinking detection: reasoning_content and reasoning_tokens
- Response quality: dental relevance, clarity, conciseness, safety
- Success / failure rates

Run directly via:
    .\\orchestrator\\.venv\\Scripts\\python.exe scripts\\benchmark_chat_models.py

NEVER prints: API keys, Authorization headers, or raw secrets.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# Ensure orchestrator package is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "orchestrator" / "src"))

from orchestrator.ai.exceptions import AIGatewayError
from orchestrator.ai.gemini import GeminiProvider
from orchestrator.ai.qwen import QwenProvider
from orchestrator.ai.schemas import ChatMessage, TextRequest
from orchestrator.central_dentist.prompts import (
    CENTRAL_DENTIST_SYSTEM_PROMPT,
    clean_response,
)
from orchestrator.config import AISettings, settings as app_settings

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger("benchmark_chat_models")


# ---------------------------------------------------------------------------
# Test Prompts
# ---------------------------------------------------------------------------

BENCHMARK_PROMPTS = [
    {
        "id": "p1_healthy_teeth",
        "title": "General: Keep Teeth Healthy",
        "question": "How can I keep my teeth healthy?",
        "grounded_context": "",
    },
    {
        "id": "p2_cold_sensitivity",
        "title": "Symptom: Cold Sensitivity",
        "question": "Why can a tooth become sensitive to cold water?",
        "grounded_context": "",
    },
    {
        "id": "p3_bleeding_gums",
        "title": "Symptom: Bleeding Gums",
        "question": "What can cause gums to bleed while brushing?",
        "grounded_context": "",
    },
    {
        "id": "p4_plaque_tartar",
        "title": "Knowledge: Plaque vs Tartar",
        "question": "What is the difference between plaque and tartar?",
        "grounded_context": "",
    },
    {
        "id": "p5_cavities_simple",
        "title": "Knowledge: Cavity Formation",
        "question": "Explain why cavities form in simple language.",
        "grounded_context": "",
    },
    {
        "id": "p6_grounded_scan_followup",
        "title": "Grounded Scan Follow-Up: Why Flagged",
        "question": "Why did my scan flag that?",
        "grounded_context": (
            "=== PATIENT RECORD ===\n"
            "Latest Scan (Recent screening): Possible tooth discoloration [Urgency: Routine, Confidence: 76%]\n"
            "Visible Findings: Possible tooth discoloration (76%)\n\n"
            "=== REFERENCE GUIDELINE ===\n"
            "Tooth discoloration refers to visible shades of yellow, brown, or gray on the tooth surface. "
            "Visual screening detects surface color variation, but cannot determine the underlying cause "
            "(such as superficial staining from tea or coffee versus internal changes). A routine dental checkup "
            "is recommended to evaluate the tooth surface."
        ),
    },
]


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class SingleRunResult:
    run_index: int
    success: bool
    total_ms: float
    response_chars: int
    cleaned_response: str
    error: str = ""
    thinking_detected: bool = False
    reasoning_tokens: Optional[int] = None
    reasoning_preview: str = ""


@dataclass
class PromptBenchmarkResult:
    prompt_id: str
    prompt_title: str
    question: str
    runs: list[SingleRunResult] = field(default_factory=list)
    min_ms: float = 0.0
    avg_ms: float = 0.0
    max_ms: float = 0.0
    success_rate: float = 0.0
    sample_response: str = ""
    thinking_detected: bool = False


@dataclass
class ModelBenchmarkResult:
    config_id: str
    config_name: str
    provider_name: str
    model_name: str
    thinking_configured: bool
    prompts: list[PromptBenchmarkResult] = field(default_factory=list)
    overall_min_ms: float = 0.0
    overall_avg_ms: float = 0.0
    overall_max_ms: float = 0.0
    total_successful_runs: int = 0
    total_runs: int = 0
    thinking_detected: bool = False


# ---------------------------------------------------------------------------
# Benchmark Runner
# ---------------------------------------------------------------------------

class ChatModelBenchmarker:
    def __init__(self, settings: AISettings, timeout: float = 15.0, runs_per_prompt: int = 3):
        self.settings = settings
        self.timeout = timeout
        self.runs_per_prompt = runs_per_prompt

    def _build_qwen_provider(self, model: str, enable_thinking: bool) -> QwenProvider:
        return QwenProvider(
            settings=self.settings,
            chat_model=model,
            default_model=model,
            timeout_seconds=self.timeout,
            enable_thinking=enable_thinking,
        )

    def _build_gemini_provider(self, model: str) -> GeminiProvider:
        return GeminiProvider(
            settings=self.settings,
            default_model=model,
            timeout_seconds=self.timeout,
        )

    async def benchmark_single_turn(
        self,
        provider: Any,
        prompt_item: dict[str, str],
        run_idx: int,
        enable_thinking: Optional[bool] = None,
        model_override: Optional[str] = None,
    ) -> SingleRunResult:
        question = prompt_item["question"]
        grounded_ctx = prompt_item.get("grounded_context", "")

        if grounded_ctx:
            user_content = f"PATIENT QUESTION: {question}\n\n{grounded_ctx}".strip()
        else:
            user_content = f"PATIENT QUESTION: {question}".strip()

        extra_body = None
        if provider.name == "qwen" and enable_thinking is not None:
            extra_body = {"enable_thinking": enable_thinking}

        request = TextRequest(
            messages=[
                ChatMessage(role="system", content=CENTRAL_DENTIST_SYSTEM_PROMPT),
                ChatMessage(role="user", content=user_content),
            ],
            model=model_override,
            temperature=0.25,
            max_tokens=200,
            extra_body=extra_body,
            metadata={"request_id": f"bench_{prompt_item['id']}_r{run_idx}"},
        )

        t0 = time.perf_counter()
        try:
            res = await asyncio.wait_for(provider.generate_text(request), timeout=self.timeout)
            total_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            raw_text = res.content or ""
            cleaned = clean_response(raw_text)

            thinking_detected = False
            reasoning_tokens = None
            reasoning_preview = ""

            if res.raw_metadata:
                r_content = res.raw_metadata.get("reasoning_content")
                if r_content:
                    thinking_detected = True
                    reasoning_preview = str(r_content)[:120].strip() + "..."
                r_tokens = res.raw_metadata.get("reasoning_tokens")
                if r_tokens is not None:
                    reasoning_tokens = int(r_tokens)
                    if reasoning_tokens > 0:
                        thinking_detected = True

            return SingleRunResult(
                run_index=run_idx,
                success=True,
                total_ms=total_ms,
                response_chars=len(cleaned),
                cleaned_response=cleaned,
                thinking_detected=thinking_detected,
                reasoning_tokens=reasoning_tokens,
                reasoning_preview=reasoning_preview,
            )
        except asyncio.TimeoutError:
            total_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return SingleRunResult(
                run_index=run_idx,
                success=False,
                total_ms=total_ms,
                response_chars=0,
                cleaned_response="",
                error=f"Timeout after {self.timeout:.1f}s",
            )
        except Exception as exc:
            total_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return SingleRunResult(
                run_index=run_idx,
                success=False,
                total_ms=total_ms,
                response_chars=0,
                cleaned_response="",
                error=f"{type(exc).__name__}: {exc}",
            )

    async def run_configuration(
        self,
        config_id: str,
        config_name: str,
        provider_type: str,
        model_name: str,
        enable_thinking: bool,
    ) -> ModelBenchmarkResult:
        print(f"\n{'='*75}")
        print(f"[*] RUNNING CONFIGURATION {config_id}: {config_name}")
        print(f"    Provider: {provider_type} | Model: {model_name} | Thinking: {enable_thinking}")
        print(f"{'='*75}")

        # Instantiate persistent provider instance for connection reuse across all runs
        if provider_type == "qwen":
            provider = self._build_qwen_provider(model=model_name, enable_thinking=enable_thinking)
        else:
            provider = self._build_gemini_provider(model=model_name)

        model_res = ModelBenchmarkResult(
            config_id=config_id,
            config_name=config_name,
            provider_name=provider_type,
            model_name=model_name,
            thinking_configured=enable_thinking,
        )

        all_latencies: list[float] = []

        try:
            for p_idx, prompt_item in enumerate(BENCHMARK_PROMPTS, 1):
                p_title = prompt_item["title"]
                print(f"\n  [Prompt {p_idx}/6] {p_title}")
                print(f"    Query: \"{prompt_item['question']}\"")

                prompt_res = PromptBenchmarkResult(
                    prompt_id=prompt_item["id"],
                    prompt_title=p_title,
                    question=prompt_item["question"],
                )

                runs: list[SingleRunResult] = []
                for r in range(1, self.runs_per_prompt + 1):
                    print(f"      Run {r}/{self.runs_per_prompt}... ", end="", flush=True)
                    run_res = await self.benchmark_single_turn(
                        provider=provider,
                        prompt_item=prompt_item,
                        run_idx=r,
                        enable_thinking=enable_thinking if provider_type == "qwen" else None,
                        model_override=model_name,
                    )
                    runs.append(run_res)
                    model_res.total_runs += 1

                    if run_res.success:
                        model_res.total_successful_runs += 1
                        all_latencies.append(run_res.total_ms)
                        think_info = ""
                        if run_res.thinking_detected:
                            prompt_res.thinking_detected = True
                            model_res.thinking_detected = True
                            think_info = f" [THINKING: tokens={run_res.reasoning_tokens or 'yes'}]"
                        print(f"SUCCESS in {run_res.total_ms:.1f} ms ({run_res.response_chars} chars){think_info}")
                    else:
                        print(f"FAILED ({run_res.error}) in {run_res.total_ms:.1f} ms")

                prompt_res.runs = runs
                successful_runs = [r for r in runs if r.success]
                if successful_runs:
                    lats = [r.total_ms for r in successful_runs]
                    prompt_res.min_ms = min(lats)
                    prompt_res.max_ms = max(lats)
                    prompt_res.avg_ms = round(sum(lats) / len(lats), 2)
                    prompt_res.success_rate = round(len(successful_runs) / len(runs), 2)
                    prompt_res.sample_response = successful_runs[0].cleaned_response

                    print(f"      -> Min: {prompt_res.min_ms:.1f}ms | Avg: {prompt_res.avg_ms:.1f}ms | Max: {prompt_res.max_ms:.1f}ms")
                    # Sample preview (first 180 chars)
                    preview = prompt_res.sample_response.replace("\n", " ").strip()
                    if len(preview) > 160:
                        preview = preview[:157] + "..."
                    print(f"      -> Sample Response: \"{preview}\"")
                else:
                    print(f"      -> ALL {self.runs_per_prompt} RUNS FAILED")

                model_res.prompts.append(prompt_res)

        finally:
            if hasattr(provider, "aclose"):
                await provider.aclose()

        if all_latencies:
            model_res.overall_min_ms = min(all_latencies)
            model_res.overall_max_ms = max(all_latencies)
            model_res.overall_avg_ms = round(sum(all_latencies) / len(all_latencies), 2)

        return model_res


# ---------------------------------------------------------------------------
# Report Presentation
# ---------------------------------------------------------------------------

def print_summary_comparison(results: list[ModelBenchmarkResult]) -> None:
    print("\n" + "=" * 80)
    print("DAANTSHAANT CHAT MODEL BENCHMARK — FINAL SUMMARY COMPARISON")
    print("=" * 80)

    header = f"{'Config':<8} | {'Provider':<7} | {'Model':<22} | {'Thinking':<9} | {'Success':<8} | {'Min (ms)':<9} | {'Avg (ms)':<9} | {'Max (ms)':<9}"
    print(header)
    print("-" * len(header))

    for res in results:
        thinking_str = "YES" if res.thinking_detected else ("True" if res.thinking_configured else "False")
        success_str = f"{res.total_successful_runs}/{res.total_runs}"
        print(
            f"{res.config_id:<8} | "
            f"{res.provider_name:<7} | "
            f"{res.model_name:<22} | "
            f"{thinking_str:<9} | "
            f"{success_str:<8} | "
            f"{res.overall_min_ms:<9.1f} | "
            f"{res.overall_avg_ms:<9.1f} | "
            f"{res.overall_max_ms:<9.1f}"
        )

    print("-" * len(header))

    print("\n[+] DETAILED QUALITY & GROUNDING INSPECTION:")
    print("=" * 80)
    for res in results:
        print(f"\n--- CONFIG {res.config_id}: {res.config_name} ---")
        for p in res.prompts:
            print(f"\n  [{p.prompt_title}]")
            print(f"  Latency: Min {p.min_ms:.1f}ms | Avg {p.avg_ms:.1f}ms | Max {p.max_ms:.1f}ms")
            if p.sample_response:
                print(f"  Response:")
                for line in p.sample_response.splitlines():
                    print(f"    {line}")
            else:
                print(f"  Response: <FAILED>")
    print("=" * 80)


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

async def main_async() -> int:
    parser = argparse.ArgumentParser(
        description="DaantShaant Chat LLM Benchmark (Qwen thinking, non-thinking, flash, and Gemini flash-lite)"
    )
    parser.add_argument(
        "--config",
        choices=["ALL", "A", "B", "C", "D"],
        default="ALL",
        help="Specific configuration to run (default: ALL)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of runs per prompt (default: 3)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Per-request timeout in seconds (default: 15.0)",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="",
        help="Optional path to save JSON results",
    )

    args = parser.parse_args()

    # Load canonical settings
    settings = AISettings()

    print("\n" + "=" * 80)
    print("DAANTSHAANT CHAT MODEL BENCHMARK INITIALIZATION")
    print(f"Base URL Host: {settings.qwen_base_url.split('/')[2] if '://' in settings.qwen_base_url else 'configured'}")
    print(f"Qwen Key Configured: {'YES (masked)' if bool(settings.dashscope_api_key) else 'NO'}")
    print(f"Gemini Key Configured: {'YES (masked)' if bool(settings.gemini_api_key) else 'NO'}")
    print(f"Timeout Budget: {args.timeout}s per call | {args.runs} runs per prompt")
    print("=" * 80)

    benchmarker = ChatModelBenchmarker(
        settings=settings,
        timeout=args.timeout,
        runs_per_prompt=args.runs,
    )

    configs_to_run = []
    if args.config in ("ALL", "A"):
        configs_to_run.append(("A", "qwen3.7-plus (thinking=true)", "qwen", "qwen3.7-plus", True))
    if args.config in ("ALL", "B"):
        configs_to_run.append(("B", "qwen3.7-plus (thinking=false)", "qwen", "qwen3.7-plus", False))
    if args.config in ("ALL", "C"):
        configs_to_run.append(("C", "qwen3.7-flash (thinking=false)", "qwen", "qwen3.7-flash", False))
    if args.config in ("ALL", "D"):
        configs_to_run.append(("D", "gemini-flash-lite-latest", "gemini", "gemini-flash-lite-latest", False))

    results: list[ModelBenchmarkResult] = []

    for cfg_id, cfg_name, p_type, m_name, think in configs_to_run:
        res = await benchmarker.run_configuration(
            config_id=cfg_id,
            config_name=cfg_name,
            provider_type=p_type,
            model_name=m_name,
            enable_thinking=think,
        )
        results.append(res)

    print_summary_comparison(results)

    if args.output_json:
        out_path = Path(args.output_json)
        data = [asdict(r) for r in results]
        out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"\n[✓] Results exported to {out_path}")

    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
