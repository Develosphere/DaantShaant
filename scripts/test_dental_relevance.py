"""Manual smoke test for the Semantic Dental Relevance core (Phase 2B.1).

Developer-run only; never executed by the test suite. Makes ONE real AI call
through the shared gateway (Qwen primary, Gemini fallback).

Usage:
    python scripts/test_dental_relevance.py --image path/to/photo.jpg
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import mimetypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "orchestrator" / "src"))

from orchestrator.clinical.relevance import evaluate_dental_relevance  # noqa: E402


async def _run(image_path: Path) -> None:
    content_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

    result = await evaluate_dental_relevance(image_base64, content_type)

    # Safe structured output only - no image data is echoed.
    print(result.model_dump_json(indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate dental relevance for a local image.")
    parser.add_argument("--image", required=True, type=Path, help="Path to a local image file")
    args = parser.parse_args()

    if not args.image.is_file():
        parser.error(f"Image file not found: {args.image}")

    asyncio.run(_run(args.image))


if __name__ == "__main__":
    main()
