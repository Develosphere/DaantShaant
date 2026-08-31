from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from uuid import UUID

from orchestrator.config import settings
from orchestrator.database import Database
from orchestrator.live_session import handle_live_websocket
from orchestrator.pipeline import (
    TeethAnalyzePipelineRequest,
    TeethAnalyzePipelineResponse,
    check_dependencies,
    run_teeth_analysis_pipeline,
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
    # Connect to MongoDB
    await Database.connect()

    # Initialize Dentist Portal indexes
    try:
        from orchestrator.dentist_portal.db import init_portal_indexes
        await init_portal_indexes()
    except Exception as e:
        print(f"[PORTAL] Index init failed: {e}")
    
    # Initialize RAG system
    try:
        from orchestrator.rag.vector_store import vector_store
        vector_store.load()
        print("[RAG] RAG vector store loaded successfully")
    except Exception as e:
        print(f"[RAG] RAG vector store not available: {e}")
    
    yield
    # Disconnect from MongoDB
    await Database.disconnect()


app = FastAPI(
    title="DantShaant Orchestrator",
    version="0.3.0",
    description="Gateway — HTTP snapshot + WebSocket live video + Chat API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
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
    
    # Check MongoDB connection
    try:
        await Database.get_db().command("ping")
        deps["mongodb"] = "ok"
    except Exception:
        deps["mongodb"] = "unreachable"
    
    status = "ok" if all(v == "ok" for v in deps.values()) else "degraded"
    return {
        "status": status,
        "service": "orchestrator",
        "version": "0.3.0",
        "dependencies": deps,
    }


# --- Original Analysis Endpoints ---


@app.post("/v1/teeth/analyze", response_model=TeethAnalyzePipelineResponse)
async def analyze_teeth(
    request: TeethAnalyzePipelineRequest,
) -> TeethAnalyzePipelineResponse:
    try:
        return await run_teeth_analysis_pipeline(request)
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
    await handle_live_websocket(websocket)


# --- Chat API Endpoints ---


@app.post("/v1/chat/conversation", response_model=CreateConversationResponse)
async def create_new_conversation(
    request: CreateConversationRequest,
) -> CreateConversationResponse:
    """Create a new conversation."""
    try:
        return await create_conversation(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/v1/chat/conversations/{user_id}", response_model=list[ConversationSummary])
async def list_user_conversations(user_id: UUID) -> list[ConversationSummary]:
    """Get all conversations for a user."""
    try:
        return await get_user_conversations(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/v1/chat/messages/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(conversation_id: UUID) -> ConversationHistoryResponse:
    """Get all messages in a conversation."""
    try:
        return await get_conversation_messages(conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/v1/chat/message", response_model=SendMessageResponse)
async def send_chat_message(request: SendMessageRequest) -> SendMessageResponse:
    """Send a message and get assistant response."""
    try:
        return await send_message(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


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
