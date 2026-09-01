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
    +--> Legacy direct AI paths (vision Gemini, OpenRouter descriptions)
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

### AI Gateway (Phase 2A.1-2A.4 - Composed, One Caller Migrated)

The shared, provider-neutral gateway lives at `orchestrator/src/orchestrator/ai/`:

```text
Conversation engine (chat text generation)   <-- migrated in 2A.4
    -> ai/factory.create_ai_gateway(settings) / get_ai_gateway()   [lazy, no import-time I/O]
        -> AIGateway (routing, timeout, normalization, fallback policy)
            -> PRIMARY  QwenProvider   (QWEN_CHAT_MODEL)
            -> FALLBACK GeminiProvider (GEMINI_MODEL)

Still on legacy direct paths (2A.5+ targets)
    -> Teeth Analyzer / clinical vision   -> direct Gemini
    -> Product description generator      -> OpenRouter
    -> Recommendation LangGraphs          -> llm_provider.gemini (direct Gemini)
```

Composition is driven by `PRIMARY_AI_PROVIDER=qwen` / `FALLBACK_AI_PROVIDER=gemini`; an unsupported name raises `ProviderConfigurationError` instead of silently selecting another provider. Providers are constructed on first use, so no HTTP client, no provider instance, and no network call exist at import time.

The migrated chat caller builds a neutral `TextRequest` (system + user turns, temperature, max_tokens) and reads only `AIResult.content`, keeping the `POST /v1/chat/message` response contract unchanged. Configuration and programming errors propagate rather than being masked by fallback; only a technical failure of both providers degrades to the existing deterministic dental answer.

## Target Architecture (Planned)

The persistence/auth target is complete. Remaining architecture work is:

```text
Next.js
  -> FastAPI
      -> Shared DaantShaant AI Gateway
          -> Qwen primary
          -> Gemini fallback
      -> Unified Clinical LangGraph
      -> Clinical FAISS RAG + evidence rules
      -> OSM / Overpass dentist discovery
  -> Supabase PostgreSQL

Map rendering: MapLibre GL JS + OpenFreeMap
```

Database and identity are no longer transitional targets.
