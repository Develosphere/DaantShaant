"""
Live video WebSocket session: throttle frames → pipeline → partial/final diagnosis.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import httpx
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from orchestrator.config import settings
from orchestrator.pipeline import (
    TeethAnalyzePipelineRequest,
    TeethAnalyzePipelineResponse,
    run_scan_with_relevance,
)
from orchestrator.session_log import log_event


@dataclass
class LiveSessionState:
    session_id: UUID
    user_id: UUID
    locale: str = "en"
    started_at: float = field(default_factory=time.time)
    frames_received: int = 0
    frames_analyzed: int = 0
    last_frame_at: float = 0.0
    busy: bool = False
    best: TeethAnalyzePipelineResponse | None = None
    history: list[TeethAnalyzePipelineResponse] = field(default_factory=list)
    stable_streak: int = 0
    last_condition: str | None = None


class LiveSessionManager:
    def __init__(self) -> None:
        self._sessions: dict[UUID, LiveSessionState] = {}

    def start(self, user_id: UUID, locale: str) -> LiveSessionState:
        session = LiveSessionState(session_id=uuid4(), user_id=user_id, locale=locale)
        self._sessions[session.session_id] = session
        log_event(session.session_id, "session.start", {"user_id": str(user_id), "locale": locale})
        return session

    def get(self, session_id: UUID) -> LiveSessionState | None:
        return self._sessions.get(session_id)

    def end(self, session_id: UUID) -> LiveSessionState | None:
        session = self._sessions.pop(session_id, None)
        if session:
            log_event(session_id, "session.end", {"frames_analyzed": session.frames_analyzed})
        return session


live_sessions = LiveSessionManager()


async def send_json(ws: WebSocket, payload: dict) -> None:
    await ws.send_json(payload)


async def process_frame(
    ws: WebSocket,
    session: LiveSessionState,
    image_base64: str,
    seq: int,
) -> None:
    now = time.time()
    session.frames_received += 1

    if now - session.started_at > settings.live_max_duration_seconds:
        await send_json(
            ws,
            {"type": "error", "code": "session_timeout", "message": "Session time limit reached."},
        )
        return

    min_interval = 1.0 / settings.live_max_fps
    if now - session.last_frame_at < min_interval:
        return
    session.last_frame_at = now

    if session.frames_analyzed >= settings.live_max_analyses_per_session:
        return

    if session.busy:
        return

    session.busy = True
    try:
        req = TeethAnalyzePipelineRequest(
            user_id=session.user_id,
            image_base64=image_base64,
            locale=session.locale,
        )
        # Semantic relevance gates clinical vision for each analyzed frame.
        await send_json(ws, {"type": "analysis.progress", "step": "relevance", "seq": seq})
        outcome = await run_scan_with_relevance(req)

        if outcome.status == "retake":
            # Lightweight ask for a better oral view; no clinical vision, and
            # the session stays open so later frames can still be analyzed.
            await send_json(
                ws,
                {
                    "type": "relevance.retake",
                    "seq": seq,
                    "message": outcome.relevance.reason
                    or "Move closer and show a clearer view of your mouth/teeth.",
                    "retake_reason": outcome.relevance.retake_reason,
                    "recommended_action": outcome.relevance.recommended_action,
                },
            )
            return
        if outcome.status == "rejected":
            # Unrelated frame: ask for the oral region; keep the session alive.
            await send_json(
                ws,
                {
                    "type": "relevance.rejected",
                    "seq": seq,
                    "message": "Point the camera at your mouth/jaw or oral region to continue.",
                    "recommended_action": outcome.relevance.recommended_action,
                },
            )
            return

        # Relevant: clinical analysis already ran inside the shared helper.
        result = TeethAnalyzePipelineResponse(
            analysis=outcome.analysis, diagnosis=outcome.diagnosis
        )
        session.frames_analyzed += 1

        await send_json(ws, {"type": "analysis.progress", "step": "vision", "seq": seq})
        await send_json(ws, {"type": "analysis.progress", "step": "diagnosis", "seq": seq})

        condition = result.diagnosis.condition_label.value
        if condition == session.last_condition:
            session.stable_streak += 1
        else:
            session.stable_streak = 1
            session.last_condition = condition

        session.history.append(result)
        if (
            session.best is None
            or result.analysis.overall_quality_score
            > session.best.analysis.overall_quality_score
        ):
            session.best = result

        log_event(
            session.session_id,
            "frame.diagnosis",
            {
                "seq": seq,
                "analysis_id": str(result.analysis.analysis_id),
                "diagnosis_id": str(result.diagnosis.diagnosis_id),
                "condition": condition,
                "confidence": result.diagnosis.confidence,
                "model_id": result.analysis.model_id,
            },
        )

        payload = _pipeline_to_dict(result)
        if session.stable_streak >= settings.live_stable_frames_for_partial:
            await send_json(ws, {"type": "analysis.partial", **payload})

    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 422:
            try:
                body = exc.response.json()
                detail = body.get("detail", {})
                if isinstance(detail, dict):
                    await send_json(
                        ws,
                        {
                            "type": "quality.hint",
                            "message": detail.get("hint", "Improve lighting and hold still."),
                            "quality_score": detail.get("quality_score"),
                        },
                    )
                    return
            except Exception:
                pass
        await send_json(
            ws,
            {"type": "error", "code": "analysis_failed", "message": exc.response.text},
        )
    except Exception as exc:
        await send_json(ws, {"type": "error", "code": "analysis_failed", "message": str(exc)})
    finally:
        session.busy = False


def _pipeline_to_dict(result: TeethAnalyzePipelineResponse) -> dict:
    return {
        "analysis": result.analysis.model_dump(mode="json"),
        "diagnosis": result.diagnosis.model_dump(mode="json"),
    }


async def finalize_session(ws: WebSocket, session: LiveSessionState) -> None:
    final = session.best or (session.history[-1] if session.history else None)
    if final is None:
        await send_json(
            ws,
            {
                "type": "analysis.final",
                "message": "No analyzable frames — try better lighting and hold still.",
                "frames_received": session.frames_received,
                "frames_analyzed": session.frames_analyzed,
            },
        )
        return

    log_event(
        session.session_id,
        "session.final_diagnosis",
        {
            "diagnosis_id": str(final.diagnosis.diagnosis_id),
            "condition": final.diagnosis.condition_label.value,
            "severity": final.diagnosis.severity.value,
            "confidence": final.diagnosis.confidence,
        },
    )

    from orchestrator.db.session import async_session_factory
    from orchestrator.repositories import ScanRepository

    async with async_session_factory() as db_session:
        async with db_session.begin():
            await ScanRepository(db_session).add_result(
                patient_user_id=session.user_id,
                input_mode="live",
                analysis=final.analysis,
                diagnosis=final.diagnosis,
            )

    await send_json(
        ws,
        {
            "type": "analysis.final",
            **_pipeline_to_dict(final),
            "frames_received": session.frames_received,
            "frames_analyzed": session.frames_analyzed,
            "session_id": str(session.session_id),
        },
    )


async def handle_live_websocket(ws: WebSocket, authenticated_user_id: UUID) -> None:
    await ws.accept()
    session: LiveSessionState | None = None

    try:
        while True:
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                break
            msg_type = data.get("type")

            if msg_type == "session.start":
                locale = data.get("locale", "en")
                session = live_sessions.start(authenticated_user_id, locale)
                await send_json(
                    ws,
                    {
                        "type": "session.ready",
                        "session_id": str(session.session_id),
                        "max_fps": settings.live_max_fps,
                        "max_analyses": settings.live_max_analyses_per_session,
                    },
                )

            elif msg_type == "frame":
                if session is None:
                    await send_json(ws, {"type": "error", "code": "no_session", "message": "Send session.start first"})
                    continue
                image_b64 = data.get("image_base64", "")
                seq = int(data.get("seq", 0))
                if not image_b64:
                    continue
                asyncio.create_task(process_frame(ws, session, image_b64, seq))

            elif msg_type == "session.end":
                if session is None:
                    await send_json(ws, {"type": "error", "code": "no_session", "message": "No active session"})
                    continue
                await finalize_session(ws, session)
                live_sessions.end(session.session_id)
                session = None

            elif msg_type == "ping":
                await send_json(ws, {"type": "pong"})

    except WebSocketDisconnect:
        if session:
            live_sessions.end(session.session_id)
    except Exception:
        if session:
            live_sessions.end(session.session_id)
        raise
