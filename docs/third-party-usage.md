# DaantShaant — Third-Party Usage

Technology inventory: CURRENT, TARGET, and LEGACY status for every external dependency.

---

## Alibaba-Native

| Technology | Status | Usage |
|------------|--------|-------|
| Alibaba Model Studio | **TARGET** | Primary AI provider for Qwen models |
| Qwen (qwen3.7-plus) | **TARGET** | Primary runtime LLM for all AI paths |

---

## Third-Party / Open-Source

| Technology | Status | Usage |
|------------|--------|-------|
| Next.js 14 | **CURRENT** | Frontend framework (React 18) |
| React 18 | **CURRENT** | UI component library |
| FastAPI | **CURRENT** | Backend API framework (orchestrator, teeth_analyzer, diagnosis) |
| Uvicorn | **CURRENT** | ASGI server |
| Pydantic v2 | **CURRENT** | Data validation and settings |
| httpx | **CURRENT** | Async HTTP client (service-to-service) |
| MongoDB | **CURRENT** | Primary database (all collections) |
| motor / pymongo | **CURRENT** | MongoDB async driver |
| Gemini (Google) | **CURRENT** | Vision analysis (teeth_analyzer), product embeddings |
| OpenRouter | **CURRENT** | Chat LLM routing (meta-llama/llama-3.2-3b-instruct:free) |
| LangGraph | **CURRENT** | Product + dentist recommendation graphs |
| langchain-core | **CURRENT** | LangGraph dependency |
| FAISS (faiss-cpu) | **CURRENT** | RAG vector store |
| sentence-transformers | **CURRENT** | RAG text embeddings |
| Google Maps JavaScript API | **CURRENT** | Frontend map display |
| Google Places API | **CURRENT** | Dentist location search |
| Google Geocoding API | **CURRENT** | Address resolution |
| bcrypt | **CURRENT** | Password hashing (dentist portal) |
| PyJWT | **CURRENT** | JWT token generation/verification |
| OpenCV | **CURRENT** | Image preprocessing (teeth_analyzer) |
| Pillow | **CURRENT** | Image handling |
| Supabase PostgreSQL | **TARGET** | Managed PostgreSQL hosting |
| SQLAlchemy 2 | **TARGET** | Async database ORM/access layer |
| asyncpg | **TARGET** | PostgreSQL async driver |
| Alembic | **TARGET** | Database migrations |
| Gemini Flash-Lite | **TARGET** | Fallback AI provider |
| MapLibre GL JS | **TARGET** | Frontend map rendering |
| OpenFreeMap | **TARGET** | Free map tile server |
| OpenStreetMap | **TARGET** | Map data source |
| Overpass API | **TARGET** | Community POI (dentists) query |
| Vercel | **TARGET** | Frontend hosting |
| Google Maps / Places | **LEGACY / TO BE REMOVED** | Replaced by MapLibre + OSM + Overpass in Phase 6 |
| OpenRouter | **LEGACY / TO BE REMOVED** | Replaced by Qwen AI Gateway in Phase 2A |

---

## Notes

- **Alibaba Model Studio** is the only Alibaba-native service used; it is not mandatory for hackathon participation.
- **Supabase** is used mainly as managed PostgreSQL hosting. Core DB logic remains PostgreSQL-provider-neutral via SQLAlchemy 2 + DATABASE_URL.
- **Google Maps/Places** removal is scheduled for Phase 6. Until then it remains active.
- **OpenRouter** removal is scheduled for Phase 2A (Qwen AI Gateway). Until then it remains active for chat.
