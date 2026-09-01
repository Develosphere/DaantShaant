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
| Gemini | **ACTIVE (fallback)** | Clinical vision baseline and recommendation AI paths still call Gemini directly; since 2A.4 `GeminiProvider` is the production gateway FALLBACK for the migrated conversational chat path. No Google SDK introduced (plain httpx `v1beta` `generateContent`) |
| OpenRouter | **LEGACY - TO BE REMOVED** | No longer used by the conversational chat path (migrated in 2A.4). Still used by the dentist-portal product description generator; `openrouter_client.py` retained until Phase 2A.5 retires it |
| LangGraph / langchain-core | **ACTIVE** | Product and dentist recommendation graphs |
| FAISS / sentence-transformers | **ACTIVE** | Local dental RAG |
| OpenCV / Pillow | **ACTIVE** | Image processing |
| Google Maps / Places / Geocoding | **ACTIVE - TO BE REMOVED** | Existing dentist discovery/map path |
| Alibaba Model Studio / Qwen | **ACTIVE (production primary)** | Shared primary AI gateway. 2A.1 built the provider-neutral core, 2A.2 added `QwenProvider` (httpx, OpenAI-compatible `/chat/completions`), 2A.4 added the production composition `ai/factory.py` (`create_ai_gateway` / `get_ai_gateway`) and migrated the conversational chat text-generation caller to Qwen primary with Gemini technical fallback |
| MapLibre / OpenFreeMap / OSM / Overpass | **TARGET** | Open map replacement |
| Vercel | **TARGET** | Frontend hosting |

Supabase project API keys remain optional/future settings for services such as Storage or Realtime. Normal database CRUD uses `DATABASE_URL` and never requires a Supabase SDK.
