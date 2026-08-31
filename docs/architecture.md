# DaantShaant — Architecture

Current and target architecture reference. Clearly labeled.

---

## A. Current Architecture (IMPLEMENTED)

```
Browser (localhost:3000)
    |
    v
Next.js 14 Frontend (port 3000)
    |-- Patient Portal (dashboard, scan, chat, dentist finder)
    |-- Dentist Portal (dashboard, products, orders)
    +-- Admin Portal (dashboard, users)
    |
    v
FastAPI Orchestrator (port 8000)
    |-- POST /v1/teeth/analyze        -> pipeline.py
    |-- WebSocket /v1/live/session    -> live_session.py
    |-- Chat API                      -> chat_service.py
    |-- RAG Endpoints                 -> rag_endpoints.py
    |-- Dentist Portal Auth           -> routes_auth.py
    |-- Dentist Portal Products       -> routes_products.py
    |-- Recommendation AI             -> recommendation_ai_system/
    +-- Dentist Recommendation        -> dentist_recommendation/
    |
    +---> Teeth Analyzer (port 8001)
    |         |-- OpenCV preprocessing
    |         +-- Gemini 2.0 Flash vision backend
    |
    +---> Diagnosis Service (port 8002)
    |         +-- Rule-based clinical classifier
    |
    +---> MongoDB (port 27017)
    |         |-- users, conversations, messages, analysis_history
    |         +-- dentist_portal: products, sessions, recommendations
    |
    +---> FAISS RAG (local files: data/rag/)
    |         +-- sentence-transformers embeddings
    |
    +---> Google Maps / Places API
              +-- Dentist location search
```

### Current Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, React 18, TypeScript |
| API Gateway | FastAPI, Uvicorn |
| Vision | Gemini 2.0 Flash, OpenCV |
| Chat LLM | OpenRouter (Llama 3.2 3B) |
| Database | MongoDB (motor/pymongo) |
| RAG | FAISS + sentence-transformers |
| Maps | Google Maps / Google Places |
| Auth | bcrypt + PyJWT (dentist portal only) |
| Workflow | LangGraph (product + dentist recommendation) |

### Current Services

| Service | Port | Responsibility |
|---------|------|---------------|
| Orchestrator | 8000 | API gateway, pipeline composition, chat, RAG, WebSocket |
| Teeth Analyzer | 8001 | Vision inference: image -> VisualFinding[] |
| Diagnosis | 8002 | Clinical mapping: findings -> ConditionLabel, severity |

---

## B. Target Architecture (PLANNED)

```
Browser
    |
    v
Next.js 14 (Vercel)
    |-- Patient Portal
    |-- Dentist Portal
    +-- Admin Portal
    |
    v
FastAPI (Office VPS / Docker Compose)
    |-- Auth middleware (unified JWT)
    |-- API routes
    |-- DaantShaant AI Gateway
    |     |-- Qwen primary (qwen3.7-plus)
    |     +-- Gemini fallback (Flash-Lite)
    |
    |-- Clinical LangGraph (unified)
    |     |-- Mechanical Quality
    |     |-- Semantic Relevance
    |     |-- Clinical Vision (Qwen)
    |     |-- Clinical RAG (FAISS)
    |     |-- Evidence Rules
    |     |-- Triage
    |     |-- Report Generation
    |     |-- Specialist Selection
    |     |-- Dentist Marketplace
    |     +-- Persist to DB
    |
    +---> Supabase PostgreSQL
    |         |-- SQLAlchemy 2 + asyncpg + Alembic
    |         +-- All domain tables
    |
    +---> MapLibre GL JS + OpenFreeMap + OSM + Overpass API
              +-- Community dentist POI (cached in PostgreSQL)
```

### Target Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend hosting | Vercel |
| Frontend framework | Next.js 14, React 18, TypeScript |
| Backend hosting | Office VPS / Docker Compose |
| API Gateway | FastAPI, Uvicorn |
| Database | Supabase PostgreSQL |
| DB Access | SQLAlchemy 2 + asyncpg + Alembic |
| Primary AI | Alibaba Model Studio / Qwen (qwen3.7-plus) |
| Fallback AI | Gemini Flash-Lite family |
| RAG | FAISS + sentence-transformers (upgraded) |
| Maps | MapLibre GL JS + OpenFreeMap + OSM + Overpass API |
| Auth | Unified JWT (access + refresh rotation, HttpOnly cookie) |
| Workflow | LangGraph (unified clinical graph) |

### Key Differences: Current vs Target

| Aspect | Current | Target |
|--------|---------|--------|
| Database | MongoDB (document) | PostgreSQL (relational) |
| AI provider | Gemini + OpenRouter (fragmented) | Qwen primary + Gemini fallback (unified gateway) |
| Maps | Google Maps/Places (paid API) | MapLibre + OSM (free/open) |
| Clinical workflow | Sequential pipeline | Unified LangGraph |
| Auth | Per-portal, basic JWT | Unified identity, refresh rotation |
| Hosting | All local | Vercel (frontend) + VPS/Docker (backend) |
