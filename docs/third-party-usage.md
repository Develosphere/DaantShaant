# DaantShaant Third-Party Usage

Statuses describe the current runtime after Phase 1B.

| Technology | Status | Usage |
|---|---|---|
| Supabase PostgreSQL | **ACTIVE - SOLE DATABASE** | Managed PostgreSQL hosting |
| SQLAlchemy 2 | **ACTIVE** | Provider-neutral async ORM/repository layer |
| asyncpg | **ACTIVE** | PostgreSQL async driver |
| Alembic | **ACTIVE** | PostgreSQL schema migrations |
| Argon2-cffi | **ACTIVE** | Argon2id password hashing |
| PyJWT | **ACTIVE** | Short-lived access JWTs |
| MongoDB | **REMOVED** | No application runtime usage |
| motor / pymongo / bson | **REMOVED** | Dependencies and ObjectId semantics removed |
| bcrypt | **REMOVED** | Replaced by Argon2id |
| Next.js 14 / React 18 | **ACTIVE** | Web application |
| FastAPI / Uvicorn | **ACTIVE** | API and service runtime |
| Pydantic v2 | **ACTIVE** | API schemas and configuration |
| httpx | **ACTIVE** | Service-to-service HTTP |
| Gemini | **ACTIVE** | Vision and existing recommendation AI paths; 2A.3 added `GeminiProvider` gateway fallback adapter (httpx, `v1beta` `generateContent`) — not yet caller-wired, no Google SDK introduced |
| OpenRouter | **ACTIVE - TO BE REMOVED** | Existing chat path; replaced in Phase 2A |
| LangGraph / langchain-core | **ACTIVE** | Product and dentist recommendation graphs |
| FAISS / sentence-transformers | **ACTIVE** | Local dental RAG |
| OpenCV / Pillow | **ACTIVE** | Image processing |
| Google Maps / Places / Geocoding | **ACTIVE - TO BE REMOVED** | Existing dentist discovery/map path |
| Alibaba Model Studio / Qwen | **ACTIVE (adapter built, not yet caller-wired)** | Shared primary AI gateway; 2A.1 built the provider-neutral core, 2A.2 added `QwenProvider` (httpx, OpenAI-compatible `/chat/completions`); no application caller migrated yet |
| MapLibre / OpenFreeMap / OSM / Overpass | **TARGET** | Open map replacement |
| Vercel | **TARGET** | Frontend hosting |

Supabase project API keys remain optional/future settings for services such as Storage or Realtime. Normal database CRUD uses `DATABASE_URL` and never requires a Supabase SDK.
