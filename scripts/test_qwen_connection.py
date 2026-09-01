"""Manual Qwen smoke test (Phase 2A.2) — REAL API call, developer-run only.

Usage (from the repo root):

    orchestrator\\.venv\\Scripts\\python.exe scripts\\test_qwen_connection.py

Reads DASHSCOPE_API_KEY / QWEN_BASE_URL / QWEN_* model keys from the root
.env through the orchestrator AISettings. Prints only a short sanitized
summary. NEVER prints the API key, authorization headers, or environment
configuration. Keep this script OUT of automated test runs.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "orchestrator" / "src"))

from orchestrator.ai.exceptions import AIGatewayError  # noqa: E402
from orchestrator.ai.qwen import QwenProvider  # noqa: E402
from orchestrator.ai.schemas import TextRequest  # noqa: E402
from orchestrator.config import AISettings  # noqa: E402


async def main() -> int:
    settings = AISettings()
    try:
        provider = QwenProvider(settings=settings)
    except AIGatewayError as exc:
        print(f"FAILURE: provider configuration error: {exc}")
        return 1

    started = time.perf_counter()
    try:
        result = await provider.generate_text(
            TextRequest(prompt="Reply with exactly: connection ok", max_tokens=50)
        )
    except AIGatewayError as exc:
        print(f"FAILURE: {type(exc).__name__}: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - surface unexpected bugs clearly
        print(f"FAILURE: unexpected {type(exc).__name__}")
        return 1

    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    content = result.content.strip().replace("\n", " ")
    if len(content) > 120:
        content = content[:120] + "..."
    print("SUCCESS")
    print(f"  provider    : {result.provider}")
    print(f"  model       : {result.model}")
    print(f"  latency     : {elapsed_ms} ms")
    print(f"  content     : {content}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
