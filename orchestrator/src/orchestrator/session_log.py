"""Append-only session diagnosis logs (JSONL)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from orchestrator.config import settings


def _repo_root() -> Path:
    # orchestrator/src/orchestrator/session_log.py -> repo root
    return Path(__file__).resolve().parents[3]


def _log_path() -> Path:
    path = _repo_root() / settings.session_log_dir
    path.mkdir(parents=True, exist_ok=True)
    return path / "sessions.jsonl"


def log_event(
    session_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": str(session_id),
        "event": event_type,
        **payload,
    }
    with _log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
