# DaantShaant Architecture

## Current Architecture (Implemented)

```text
Browser / Next.js 14
    |  access JWT in memory
    |  rotating refresh token in HttpOnly cookie
    v
FastAPI Orchestrator
    |-- unified auth and role/ownership guards
    |-- scan, chat, marketplace, recommendations
    |-- SQLAlchemy repositories (AsyncSession)
    |
    +--> Teeth Analyzer (OpenCV + Gemini vision)
    +--> Diagnosis service (rule classifier)
    +--> FAISS + sentence-transformers RAG
    +--> Shared AI Gateway (chat: Qwen primary / Gemini fallback)
    +--> Legacy direct AI paths (Teeth Analyzer: vision Gemini + clinical OpenRouter)
    +--> Product and Dentist LangGraphs
    +--> Google Maps / Places
    |
    v
asyncpg
    |
Supabase PostgreSQL (sole application database)
```

### Persistence

SQLAlchemy 2 models and repositories are the application persistence boundary. Alembic manages schema changes. Supabase is managed PostgreSQL hosting; application CRUD does not use a vendor SDK.

```text
users.id (canonical UUID)
  |-- patient_profiles.user_id
  |-- dentists.owner_user_id (unique for platform dentists)
  |-- scans.patient_user_id -> scan_findings + clinical_reports
  |-- conversations.patient_user_id -> messages
  |-- recommendations / appointments / orders
  +-- auth_sessions (hashed refresh tokens)
```

Tables: `users`, `auth_sessions`, `patient_profiles`, `dentists`, `scans`, `scan_findings`, `clinical_reports`, `conversations`, `messages`, `products`, `product_recommendations`, `orders`, `dentist_recommendations`, `appointment_requests`, and `commission_records`.

MongoDB is REMOVED: no connection module, runtime dependency, configuration, health check, fallback, or ObjectId API semantics remain.

### Authentication

- Application-owned auth; Supabase Auth is not used.
- Argon2id password hashes.
- HS256 access JWT using required `JWT_SECRET`.
- Opaque refresh token; only its SHA-256 hash is persisted.
- Refresh rotation revokes the prior session.
- Logout revokes the current session and clears the HttpOnly cookie.
- Public admin signup is absent; controlled admin creation uses `scripts/create_admin.py`.
- Patient and dentist resource ownership is checked against the authenticated UUID.

### AI Gateway (Phase 2A - COMPLETE)

The shared, provider-neutral gateway lives at `orchestrator/src/orchestrator/ai/`:

```text
All migrated business callers:
    - Conversation engine (chat text generation)
    - Product description generator
    - Product recommendation LangGraph (reranking + final message)
    -> ai/factory.create_ai_gateway(settings) / get_ai_gateway()   [lazy, no import-time I/O]
        -> AIGateway (routing, timeout, normalization, fallback policy)
            -> PRIMARY  QwenProvider   (QWEN_CHAT_MODEL)
            -> FALLBACK GeminiProvider (GEMINI_MODEL)

Deterministic fallback (provider-independent):
    - ai/fallbacks.get_deterministic_fallback() — issue-aware dental answer

Still on legacy direct paths (Phase 2C targets)
    -> Teeth Analyzer / clinical vision   -> direct Gemini + separate OpenRouter backend
```

Composition is driven by `PRIMARY_AI_PROVIDER=qwen` / `FALLBACK_AI_PROVIDER=gemini`; an unsupported name raises `ProviderConfigurationError` instead of silently selecting another provider. Providers are constructed on first use, so no HTTP client, no provider instance, and no network call exist at import time.

The migrated chat caller builds a neutral `TextRequest` (system + user turns, temperature, max_tokens) and reads only `AIResult.content`, keeping the `POST /v1/chat/message` response contract unchanged. Configuration and programming errors propagate rather than being masked by fallback; only a technical failure of both providers degrades to the existing deterministic dental answer.

### Clinical Perception & Triage Pipeline — DentalTensor Vision v1.0 (ACTIVE)

Visual screening perception is powered by **DentalTensor Vision v1.0** (developed by **Nathan Asif**), a dedicated YOLO11n-based oral pathology computer-vision detector fine-tuned for intraoral screening photographs. DentalTensor is an independent, reusable model/perception product; DaantShaant is the product integration consuming DentalTensor.

The end-to-end oral screening flow operates as follows:

```text
DaantShaant Oral Scan (Snapshot / Upload / Live WebSocket)
        ↓
Semantic Dental Relevance Gate (Qwen primary / Gemini fallback via AIGateway)
        ↓
Mechanical Quality Assessment & Preprocessing (OpenCV)
        ↓
DentalTensor Vision v1.0 (dentaltensor_nathan_asif_v1.pt; best_v2.pt / best.pt retained)
        |-- Bounding-box detection (calculus, caries, gingivitis, tooth discoloration, ulcer)
        |-- Calibrated engineering thresholds: calculus 0.35, caries 0.55, gingivitis 0.50, discoloration 0.65, ulcer 0.65 (fallback 0.50)
        ↓
Normalized Evidence & Spatial Aggregation (Teeth Analyzer)
        |-- Distribution classification: localized | multiple | generalized
        |-- Generalized discoloration heuristic (prevents yellow teeth from becoming tartar)
        |-- Canonical class map: calculus->tartar, caries->cavity_suspect, gingivitis->gingivitis_signs,
        |                        tooth discoloration->discoloration, ulcer->oral_ulcer
        ↓
Deterministic Clinical Triage (Diagnosis service, rule-based)
        |-- Highest urgency wins (routine < soon < urgent < emergency)
        |-- Specialist recommendation & visit timeframe
        |-- Non-definitive screening wording
        ↓
Patient-Friendly Clinical Report (Qwen via AIGateway in Orchestrator)
        |-- Receives structured evidence ONLY (NO raw images)
        |-- Hard guardrails: no diagnosis, no etiology hallucination, low temperature
        |-- Patient-friendly report summary, finding explanations, recommended steps
        ↓
Persistence (Supabase PostgreSQL via ScanRepository)
```

### DaantShaant Central Dentist Pipeline (ACTIVE - Phase 12A Final)

The conversational assistant has been reconstructed into **DaantShaant Central Dentist**, powered by LangGraph, Qwen via the shared AI Gateway, Central Patient Data, and Structured RAG with ZERO Hugging Face dependencies:

```text
Patient Authenticated Request (JWT, conversation_id, message)
        ↓
[Node 1: load_auth_context] (Validates user_id, sets telemetry)
        ↓
[Node 2: nlp_understanding] (Lightweight deterministic NLP <50ms: 13 intents, entity extraction, temporal parsing, fast-path detection)
        ↓
[Node 3: plan_retrieval] (Query-aware retrieval planner: selects strictly needed data domains)
        ↓
[Node 4: retrieve_patient_data] (Structured SQL RAG: scans, compare, history, appointments, dentists; strictly scoped to patient UUID)
        ↓
[Node 5: retrieve_conversation_context] (Fetches recent messages, resolves active conversational finding references)
        ↓
[Node 6: retrieve_optional_knowledge] (Curated keyword oral health guidelines; NO embeddings, NO models, NO vectors)
        ↓
[Node 7: build_grounded_context] (Compacts patient findings, confidence %, appointments into grounded prompt)
        ↓
[Node 8: qwen_or_direct_answer] (Fast-path bypass for dates/confidence/urgency OR qwen3.7-flash text generation via Chat AIGateway; thinking disabled, Gemini Flash-Lite fallback)
        ↓
[Node 9: validate_response] (Safety check, anti-slop cleaning, markdown formatting removal)
        ↓
[Node 10: persist_turn] (Persists user & assistant turns to PostgreSQL chat table)
```

### Conversational Provider Freeze (Phase 12D)
- **Primary Chat Model**: `qwen3.7-flash` (Alibaba Model Studio, sub-second latency ~789ms, 18/18 success).
- **Thinking Mode**: Explicitly disabled (`extra_body={"enable_thinking": False}`).
- **Technical Fallback**: `gemini-flash-lite-latest` (on 429 rate limits, fails immediately to grounded deterministic fallback).
- **Clinical Report Path**: 100% UNCHANGED (`get_ai_gateway()`, `qwen3.7-plus`, 60.0s timeout).
- **Timeouts & Settings**: `CHAT_QWEN_TIMEOUT_SECONDS=12.0`, `CHAT_REQUEST_TIMEOUT_SECONDS=15.0`, `temperature=0.25`, `max_tokens=200`.

## Target Architecture (Planned)

The persistence, auth, AI gateway, clinical vision, and Central Dentist targets are complete.

```text
Next.js
  -> FastAPI
      -> Shared DaantShaant AI Gateway
          -> Qwen primary
          -> Gemini fallback
      -> DaantShaant Central Dentist (LangGraph + Structured RAG + Qwen)
      -> DentalTensor Vision v1.0 (Local YOLO11n oral disease detector)
      -> OSM / Overpass dentist discovery
  -> Supabase PostgreSQL

Map rendering: MapLibre GL JS + OpenFreeMap
```

Database and identity are no longer transitional targets.
