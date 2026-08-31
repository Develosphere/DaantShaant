# DaantShaant Context

> **This file is CURRENT STATE.** Read this first every chat.
> Last updated: Phase 0 - Hackathon Rebaseline (COMPLETE)

---

## Product Identity

DaantShaant is a conversational AI oral health assistant with vision-based teeth analysis, persistent chat, real-time diagnosis, RAG-grounded dental knowledge, a dentist marketplace, and product recommendations. It is an **awareness tool**, not a medical diagnosis system.

Target markets: Pakistan and UAE.

---

## Hackathon Strategy

- Existing project adopted as baseline - NOT a rebuild from scratch.
- Any IDE/AI development tool permitted.
- Alibaba Cloud hosting is NOT mandatory.
- Qoder usage is NOT mandatory.
- Technical sophistication and implementation quality are the main judging criteria.
- Modular phase workflow: each phase = one bounded chat, then close.

---

## Current Architecture

```
Next.js 14 (port 3000)
    |
FastAPI Orchestrator (port 8000)
    |-- RAG System (FAISS + sentence-transformers)
    |-- Conversation Engine (OpenRouter / Llama)
    |-- Intent Classifier
    |-- Live WebSocket Session Handler
    |-- Product Recommendation LangGraph
    +-- Dentist Recommendation LangGraph
        |
Teeth Analyzer (port 8001)     Diagnosis (port 8002)
  OpenCV + Gemini Flash          Rule-based classifier
        |
MongoDB (port 27017)
  Collections: users, conversations, messages, analysis_history
  + dentist_portal: products, sessions, recommendations
```

---

## Existing Working Capabilities

- **Patient portal**: dashboard, scan (snapshot/upload/live WebSocket), scan history, chat, dentist finder
- **Dentist portal**: dashboard, product management (CRUD + AI descriptions), orders, auth (bcrypt + PyJWT)
- **Admin portal**: dashboard, user management, auth
- **Dental scan modes**: Snapshot, Upload, Live WebSocket streaming
- **AI vision**: Gemini 2.0 Flash for teeth image analysis
- **Chat**: OpenRouter (meta-llama/llama-3.2-3b-instruct:free) + RAG-grounded responses
- **RAG**: sentence-transformers embeddings + FAISS vector store + hybrid retrieval + dental knowledge ingestion
- **LangGraph graphs**:
  - Product recommendation graph (search -> details -> rank -> log)
  - Dentist recommendation graph (platform + Google Places -> merge -> rank)
- **Dentist marketplace**: product listing, AI-generated descriptions, embedding-based recommendations
- **Google Maps/Places**: dentist location search and mapping
- **MongoDB persistence**: users, conversations, messages, analysis_history, dentist portal data

---

## Known Technical Problems

- MongoDB is not suitable for the hackathon relational data needs (users, orders, products).
- OpenRouter/free-tier LLM routing is fragile and rate-limited.
- Gemini API key management is fragmented across services.
- Google Maps/Places requires paid API key and has usage limits.
- Clinical dental workflow is fragmented - not a unified LangGraph.
- Authentication is basic (bcrypt + PyJWT) with no refresh token rotation or ownership enforcement.
- No unified AI gateway - AI calls scattered across services.

---

## Locked Technology Decisions

| Domain | CURRENT | TARGET |
|--------|---------|--------|
| Database | MongoDB | Supabase PostgreSQL |
| DB Access | motor/pymongo | SQLAlchemy 2 + asyncpg + Alembic |
| Auth | bcrypt + PyJWT (dentist only) | Unified JWT: short-lived access + opaque rotating refresh |
| Primary AI | Gemini / OpenRouter | Alibaba Model Studio -> Qwen (qwen3.7-plus) |
| Fallback AI | - | Gemini Flash-Lite family |
| Maps | Google Maps / Google Places | MapLibre GL JS + OpenFreeMap + OSM + Overpass API |
| Frontend hosting | - | Vercel |
| Backend hosting | Local | Office VPS / Docker Compose (alt: Railway) |
| DB hosting | Local MongoDB | Supabase PostgreSQL |

---

## Current Persistence

**MongoDB** (local, `mongodb://localhost:27017`, database: `dantshaant`)

Collections:
- `users` - user profiles (username unique sparse index)
- `conversations` - chat conversations (user_id index)
- `messages` - individual messages (conversation_id + timestamp index)
- `analysis_history` - teeth analysis records (user_id + created_at index)
- Dentist portal: products, sessions, recommendations (via `dentist_portal/db.py`)

---

## Current AI Architecture

- **Teeth Analyzer**: Gemini 2.0 Flash (vision) via `TEETH_ANALYZER_GEMINI_API_KEY`
- **Chat**: OpenRouter -> `meta-llama/llama-3.2-3b-instruct:free`
- **Product recommendations**: Gemini embeddings for product search/ranking
- **Dentist recommendations**: Gemini via LangGraph tools
- **Product description generation**: Gemini via OpenRouter
- All AI calls are fragmented - no unified gateway.

---

## Existing LangGraph State

Two real LangGraph workflows exist:

1. **Product Recommendation Graph** (`recommendation_ai_system/recommendation_agent.py`)
   - StateGraph: search_products -> get_details -> rank -> log
   - Backed by Gemini embeddings + MongoDB product store

2. **Dentist Recommendation Graph** (`dentist_recommendation/dentist_agent.py`)
   - StateGraph: query_platform + query_places -> merge -> rank
   - Queries both platform dentists (MongoDB) and Google Places

**The main clinical dental workflow (scan -> analyze -> diagnose -> report -> specialist -> marketplace) is NOT a unified LangGraph.** It is currently a sequential pipeline in `orchestrator/pipeline.py`.

---

## Existing RAG State

- **Embeddings**: sentence-transformers (local)
- **Vector store**: FAISS CPU (`faiss-cpu`)
- **Ingestion**: `scripts/ingest-dental-knowledge.ps1` -> `data/dental_knowledge/` -> `data/rag/`
- **Retrieval**: hybrid (semantic search via `rag/retrieval_service.py`)
- **Used by**: chat service for grounded dental responses

---

## Existing Map State

- **Google Maps JavaScript API**: used in frontend (`@types/google.maps` in devDependencies)
- **Google Places API**: used for dentist location search (`places_service.py`)
- **Geocoding**: via Google Maps API key (`GOOGLE_MAPS_API_KEY`)
- Community dentists are queried at runtime via Google Places - not cached in DB.

---

## Existing Authentication State

- **Dentist portal**: bcrypt password hashing + PyJWT tokens
- **Patient portal**: basic user registration/login (MongoDB-backed)
- **Admin portal**: basic registration/login
- **No unified identity**: separate auth per portal
- **No refresh token rotation**
- **No HttpOnly cookie** for refresh tokens
- **No ownership enforcement** at middleware level

---

## Target Architecture

```
Next.js 14 (Vercel)
    |
FastAPI (Office VPS / Docker Compose)
    |
Supabase PostgreSQL (via SQLAlchemy 2 + asyncpg + Alembic)
    |
DaantShaant AI Gateway
    |-- Qwen primary (qwen3.7-plus via Alibaba Model Studio)
    +-- Gemini fallback (Flash-Lite family)
    |
Clinical LangGraph (unified)
    Mechanical Quality -> Semantic Relevance -> Clinical Vision
    -> Clinical RAG -> Evidence Rules -> Triage
    -> Report -> Specialist -> Dentist Marketplace -> Persist
    |
MapLibre GL JS + OpenFreeMap + OSM + Overpass API
```

---

## Current Phase

**Phase 0 - Hackathon Rebaseline: COMPLETE**

All documentation and governance files created. No application source code modified. No dependencies added.

---

## Completed Phases

| Phase | Name | Status |
|-------|------|--------|
| 0 | Hackathon Rebaseline | COMPLETE |

---

## Deferred / Parallel Work

- **Final Designer UI/UX**: deferred until core functionality is stable
- **Phase 3B - Final Designer UI/UX**: explicitly deferred

---

## Next Phase

**Phase 1A - Supabase PostgreSQL Foundation**

- Set up Supabase project and PostgreSQL database
- Add SQLAlchemy 2 + asyncpg + Alembic to orchestrator
- Create `DATABASE_URL` configuration
- Implement async DB engine and session factory
- Create Alembic migration infrastructure
- Do NOT migrate domain models yet (that is Phase 1C)

---

## Phase Roadmap (compact)

| Phase | Name |
|-------|------|
| 0 | Hackathon Rebaseline |
| 1A | Supabase PostgreSQL Foundation |
| 1B | Identity/Auth Migration |
| 1C | Mongo Domain Migration |
| 2A | Qwen AI Gateway |
| 2B | Semantic Dental Relevance |
| 2C | Qwen Clinical Vision |
| 3A | Clinical RAG Upgrade |
| 3B | Evidence / Rule Engine |
| 4 | Unified Clinical LangGraph |
| 5 | Reports + Persistent Case Chat |
| 6 | Google Removal + OSM/Overpass + MapLibre |
| 7 | Live Scan Intelligence |
| 8 | Evaluation Harness |
| 9 | Testing / Security |
| 10 | Final Designer UI Integration |
| 11 | Deployment |
| 12 | Demo Hardening |

---

## Instructions for Next Qoder Chat

1. Read this file (`/context.md`) FIRST.
2. Read `docs/phase-log.md` for chronological history.
3. Read the relevant phase section in the roadmap above.
4. Inspect ONLY the files relevant to the target phase.
5. DO NOT scan the entire repository.
6. DO NOT modify unrelated working modules.
7. Execute the bounded phase (max 6-8 steps).
8. Run tests for meaningful changes.
9. Update `context.md` at phase completion.
10. Append entry to `docs/phase-log.md`.
11. Replace obsolete information instead of endlessly appending.
