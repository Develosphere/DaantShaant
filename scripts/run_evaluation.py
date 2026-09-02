#!/usr/bin/env python3
"""DaantShaant Evaluation Harness CLI (Phase 8-lite).

Usage:
  python scripts/run_evaluation.py [--manifest PATH] [--real] [--json-out PATH] [--summary-only]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add orchestrator and packages to sys.path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "orchestrator" / "src"))
sys.path.insert(0, str(_ROOT / "packages" / "dantshaant_common" / "src"))

from orchestrator.evaluation.runner import format_evaluation_summary, run_evaluation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DaantShaant Clinical Evaluation Harness (Phase 8-lite)"
    )
    parser.add_argument(
        "--manifest",
        type=str,
        default=str(
            _ROOT
            / "orchestrator"
            / "src"
            / "orchestrator"
            / "evaluation"
            / "fixtures"
            / "manifest.example.json"
        ),
        help="Path to evaluation manifest JSON file",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        default=False,
        help="Execute real pipeline on dataset images (default: offline mock evaluation)",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default=None,
        help="Path to save evaluation report as JSON",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        default=False,
        help="Print demo summary JSON only",
    )
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)

    if not manifest_path.exists():
        print(f"Error: Manifest file not found: {manifest_path}", file=sys.stderr)
        return 1

    print(f"Loading manifest: {manifest_path}")
    print(f"Running in mode: {'REAL' if args.real else 'OFFLINE/MOCK'}")

    report = await run_evaluation(manifest_path, real=args.real)

    if args.summary_only:
        print(json.dumps(report.demo_summary, indent=2))
    else:
        print("\n" + format_evaluation_summary(report) + "\n")

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2)
        print(f"Report saved to: {out_path}")

    return 0


def main() -> None:
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
