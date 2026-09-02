from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi import Depends
from fastapi.middleware.cors import CORSMiddleware
from uuid import UUID

from orchestrator.config import settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from orchestrator.db.session import engine, get_db_session
from orchestrator.dentist_portal.auth import decode_access_token, get_current_patient
from orchestrator.live_session import handle_live_websocket
from orchestrator.pipeline import (
    AuthenticatedTeethAnalyzeRequest,
    ScanOutcome,
    TeethAnalyzePipelineRequest,
    check_dependencies,
    run_scan_with_relevance,
)
from orchestrator.chat_schemas import (
    CreateConversationRequest,
    CreateConversationResponse,
    ConversationHistoryResponse,
    ConversationSummary,
    SendMessageRequest,
    SendMessageResponse,
)
from orchestrator.chat_service import (
    create_conversation,
    get_user_conversations,
    get_conversation_messages,
    send_message,
)
from orchestrator.rag_endpoints import router as rag_router
from orchestrator.dentist_portal.routes_auth import router as portal_auth_router
from orchestrator.dentist_portal.routes_products import router as portal_products_router
from orchestrator.recommendation_ai_system.routes import router as recommendation_router
from orchestrator.dentist_recommendation.routes import router as dentist_recommendation_router
from orchestrator.dentist_recommendation.routes_geocode import router as geocode_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = settings
    # Initialize RAG system
    try:
        from orchestrator.rag.vector_store import vector_store
        vector_store.load()
        print("[RAG] RAG vector store loaded successfully")
    except Exception as e:
        print(f"[RAG] RAG vector store not available: {e}")
    
    yield
    await engine.dispose()


app = FastAPI(
    title="DantShaant Orchestrator",
    version="0.3.0",
    description="Gateway — HTTP snapshot + WebSocket live video + Chat API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include RAG endpoints
app.include_router(rag_router)

# Include Dentist Portal endpoints
app.include_router(portal_auth_router)
app.include_router(portal_products_router)
app.include_router(recommendation_router)
app.include_router(dentist_recommendation_router)
app.include_router(geocode_router)


@app.get("/health")
async def health() -> dict:
    deps = await check_dependencies()
    
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        deps["postgresql"] = "ok"
    except Exception:
        deps["postgresql"] = "unreachable"
    
    status = "ok" if all(v == "ok" for v in deps.values()) else "degraded"
    return {
        "status": status,
        "service": "orchestrator",
        "version": "0.3.0",
        "dependencies": deps,
    }


# --- Original Analysis Endpoints ---


@app.post("/v1/teeth/analyze", response_model=ScanOutcome)
async def analyze_teeth(
    request: AuthenticatedTeethAnalyzeRequest,
    user: dict = Depends(get_current_patient),
    session: AsyncSession = Depends(get_db_session),
) -> ScanOutcome:
    """Snapshot/upload scan. Serves both modes over the shared relevance-gated
    pipeline: clinical analysis runs only for ``relevant`` images; ``retake``
    and ``unrelated`` short-circuit before clinical vision. Relevant scans are
    persisted with their relevance verdict. Technical relevance-provider
    failures propagate (they are never reported as ``unrelated``).
    """
    try:
        owned_request = TeethAnalyzePipelineRequest(
            user_id=user["user_id"], **request.model_dump()
        )
        outcome = await run_scan_with_relevance(owned_request)
        if outcome.status == "analyzed":
            from orchestrator.repositories import ScanRepository
            await ScanRepository(session).add_result(
                patient_user_id=user["user_id"],
                input_mode="snapshot",
                analysis=outcome.analysis,
                diagnosis=outcome.diagnosis,
                relevance=outcome.relevance,
            )
        return outcome
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        try:
            detail = exc.response.json()
        except Exception:
            pass
        raise HTTPException(
            status_code=502,
            detail={"code": "downstream_error", "detail": detail},
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "downstream_unavailable", "detail": str(exc)},
        ) from exc


@app.websocket("/v1/live/session")
async def live_session_ws(websocket: WebSocket) -> None:
    token = websocket.query_params.get("access_token", "")
    try:
        payload = decode_access_token(token)
        if payload.get("role") != "patient":
            raise ValueError("patient role required")
        user_id = UUID(payload["sub"])
    except Exception:
        await websocket.close(code=4401, reason="Not authenticated")
        return
    await handle_live_websocket(websocket, user_id)


# --- Chat API Endpoints ---


@app.post("/v1/chat/conversation", response_model=CreateConversationResponse)
async def create_new_conversation(
    request: CreateConversationRequest,
    user: dict = Depends(get_current_patient),
    session: AsyncSession = Depends(get_db_session),
) -> CreateConversationResponse:
    """Create a new conversation."""
    try:
        return await create_conversation(request, user["user_id"], session)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/v1/chat/conversations", response_model=list[ConversationSummary])
async def list_current_user_conversations(
    user: dict = Depends(get_current_patient),
    session: AsyncSession = Depends(get_db_session),
) -> list[ConversationSummary]:
    """Get all conversations for a user."""
    try:
        return await get_user_conversations(user["user_id"], session)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/v1/chat/messages/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    conversation_id: UUID,
    user: dict = Depends(get_current_patient),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationHistoryResponse:
    """Get all messages in a conversation."""
    try:
        return await get_conversation_messages(
            conversation_id, user["user_id"], session
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/v1/chat/message", response_model=SendMessageResponse)
async def send_chat_message(
    request: SendMessageRequest,
    user: dict = Depends(get_current_patient),
    session: AsyncSession = Depends(get_db_session),
) -> SendMessageResponse:
    """Send a message and get assistant response."""
    try:
        return await send_message(request, user["user_id"], session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/v1/scans", response_model=list[dict])
async def list_scans(
    user: dict = Depends(get_current_patient),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    from orchestrator.repositories import ScanRepository

    scans = await ScanRepository(session).list_owned(user["user_id"])
    return [
        {
            "scan_id": str(scan.id),
            "input_mode": scan.input_mode,
            "status": scan.status,
            "quality_score": scan.mechanical_quality_score,
            "created_at": scan.created_at.isoformat(),
        }
        for scan in scans
    ]


def run() -> None:
    import uvicorn

    uvicorn.run(
        "orchestrator.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    run()
