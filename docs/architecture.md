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
