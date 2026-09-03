# DaantShaant Third-Party Usage

Statuses describe the current runtime after Phase 6 Fast Track.

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
| httpx | **ACTIVE** | Service-to-service HTTP, direct Qwen/Gemini vision REST calls, and Overpass/Nominatim geodata calls (no SDKs) |
| Gemini | **ACTIVE (fallback)** | Recommendation embeddings still call Gemini directly. Since 2A.4 `GeminiProvider` is the orchestrator gateway FALLBACK (chat text, product descriptions, recommendation reranking/final message). Since 2C it is ALSO the Teeth Analyzer clinical-vision TECHNICAL FALLBACK, service-local over plain httpx `v1beta` `generateContent` (the `google-generativeai` SDK dependency was removed from the analyzer). No Google SDK introduced anywhere |
| OpenRouter | **REMOVED - PROJECT-WIDE (ZERO active runtime references)** | Removed from orchestrator business text-generation paths (2A.5a–2A.5c). `llm_provider.py` and `openrouter_client.py` deleted. Phase 2C removed the last consumer - Teeth Analyzer clinical vision: `services/teeth_analyzer/src/teeth_analyzer/backends/openrouter.py` deleted and `TEETH_ANALYZER_OPENROUTER_API_KEY`/`_MODEL` config dropped. Only historical doc mentions and a test asserting its absence remain. PERMANENTLY ABANDONED |
| LangGraph / langchain-core | **ACTIVE** | Unified clinical screening pipeline orchestration (Phase 4-lite); product and dentist recommendation graphs (Phase 6 Fast Track). Pure deterministic orchestration — no patient data sent externally by LangGraph itself |
| FAISS / sentence-transformers | **ACTIVE** | Local dental RAG |
| OpenCV / Pillow | **ACTIVE** | Image processing |
| Google Maps / Places / Geocoding | **REMOVED - PROJECT-WIDE (ZERO active runtime callers)** | Phase 6 Fast Track removed Google Maps JS, Google Places API, and Google Geocoding API from active runtime paths. Replaced with OpenStreetMap, Overpass API, MapLibre GL JS, OpenFreeMap, and browser geolocation |
| OpenStreetMap / Overpass API | **ACTIVE** | Discover nearby dental clinics and practices from public OSM geodata (`amenity=dentist`, `healthcare=dentist`). Only search coordinates and radius are transmitted; NO patient clinical data is sent. Fallback: PostgreSQL registered platform dentists |
| MapLibre GL JS | **ACTIVE** | Client-side open-source vector map rendering for interactive dentist recommendation maps |
| OpenFreeMap | **ACTIVE** | Public vector map tile service and Liberty style source for MapLibre client-side map rendering |
| OpenStreetMap / Nominatim | **ACTIVE** | Lightweight geocoding and address suggestion lookup for PK/UAE location search with DaantShaant User-Agent |
| Foursquare Places API | **OPTIONAL RUNTIME** | Optional secondary clinic discovery provider (`categories=15007,15008`). Active only if `FOURSQUARE_API_KEY` is configured; skipped safely when unconfigured. Transmits only coordinates and search radius (no patient clinical data). Provider errors isolated from primary Overpass/PostgreSQL runtime |
| Geoapify Places API | **OPTIONAL RUNTIME** | Optional tertiary clinic discovery provider (`categories=healthcare.dentist`). Active only if `GEOAPIFY_API_KEY` is configured; skipped safely when unconfigured. Transmits only coordinates and search radius (no patient clinical data). Provider errors isolated from primary Overpass/PostgreSQL runtime |
| Alibaba Model Studio / Qwen | **ACTIVE (production primary)** | Shared primary AI gateway. 2A.1 built the provider-neutral core, 2A.2 added `QwenProvider` (httpx, OpenAI-compatible `/chat/completions`), 2A.4 added the production composition `ai/factory.py` (`create_ai_gateway` / `get_ai_gateway`) and migrated the conversational chat text-generation caller to Qwen primary with Gemini technical fallback. 2C added a SERVICE-LOCAL Qwen-primary clinical-vision policy in the Teeth Analyzer (`backends/qwen.py`, multimodal `/chat/completions` via `DASHSCOPE_API_KEY` + `QWEN_VISION_MODEL=qwen3.7-plus`), independent of the orchestrator gateway |
| Vercel | **TARGET** | Frontend hosting |

Supabase project API keys remain optional/future settings for services such as Storage or Realtime. Normal database CRUD uses `DATABASE_URL` and never requires a Supabase SDK.
