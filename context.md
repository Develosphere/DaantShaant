# DaantShaant Context

> Current implementation state. Read this first in every engineering chat.
> Last updated: Phase 2A.2 - Alibaba Qwen Provider Adapter (COMPLETE), September 2026.

## Product

DaantShaant is an AI-assisted oral-health screening and care-navigation platform for Pakistan and the UAE. It is an awareness tool, not a licensed medical diagnosis system.

## Current Architecture

```text
Next.js 14
    |
FastAPI Orchestrator
    |-- Snapshot/upload/live scan pipeline
    |-- Chat + FAISS RAG
    |-- Product recommendation LangGraph
    |-- Dentist recommendation LangGraph
    |-- Unified access/refresh authentication
    |
SQLAlchemy 2 async + asyncpg + Alembic
    |
Supabase PostgreSQL (sole application database)
```

The Teeth Analyzer and Diagnosis services remain separate HTTP services. Existing AI, RAG, LangGraph, live scan, and Google map behavior was preserved except for the persistence/auth interfaces required by Phase 1B.

## Persistence - ACTIVE

Supabase PostgreSQL is the sole application database. Normal CRUD uses provider-neutral SQLAlchemy `AsyncSession`; no Supabase SDK is used for database CRUD.

Active tables:

- `users`
- `auth_sessions`
- `patient_profiles`
- `dentists`
- `scans`
- `scan_findings`
- `clinical_reports`
- `conversations`
- `messages`
- `products`
- `product_recommendations`
- `orders`
- `dentist_recommendations`
- `appointment_requests`
- `commission_records`

Active repositories live in `orchestrator/src/orchestrator/repositories/` and cover identity/sessions, clinical records, chat, dentists, products, orders, recommendations, and appointments.

Alembic revisions:

- `001_baseline` - relational application schema
- `002_domain_compatibility` - product embeddings and appointment metadata

The configured Supabase development database is at migration head. `SELECT 1` and safe create/read/delete validation pass.

## Unified Identity and Auth - ACTIVE

- One canonical identity: `users.id` UUID.
- Patient profiles, scans, reports, conversations, recommendations, appointments, and orders reference that UUID.
- Platform dentists use `dentists.owner_user_id -> users.id` with a unique owner.
- The frontend no longer creates a second clinical UUID.
- Passwords use Argon2id.
- Access JWTs are short-lived and held in browser memory.
- Refresh tokens are opaque, stored only as SHA-256 hashes in `auth_sessions`, rotated on refresh, revoked on logout, and sent only in an HttpOnly cookie.
- Roles: `patient`, `dentist`, `admin`.
- Disabled accounts are rejected.
- Public admin registration is absent; `scripts/create_admin.py` is the controlled creation path.
- Patient-owned routes derive ownership from the authenticated principal.
- Dentist product/order ownership resolves through `dentists.owner_user_id`.
- Appointment access is scoped to the owning patient, owning dentist, or admin.

## Removed

MongoDB and its runtime drivers/configuration are removed. There are no active runtime references, connection modules, health checks, fallbacks, environment requirements, ObjectId semantics, or browser identity mappings. The old local database was not reachable and no accessible demo dataset required an import script.

## Existing Capabilities Preserved

- Patient portal: dashboard, snapshot/upload/live scan, chat, dentist discovery
- Dentist portal: registration/login, product CRUD, AI descriptions, orders
- Admin login and dashboard routes
- Gemini vision baseline and rule-based diagnosis
- OpenRouter chat baseline and FAISS/sentence-transformers RAG
- Product and dentist recommendation LangGraphs
- Google Maps/Places baseline (scheduled for later removal)

## AI Gateway

Phase 2A.1 introduced a shared, provider-neutral AI gateway core at `orchestrator/src/orchestrator/ai/`:

- `AIProvider` abstract async interface (text/vision/structured), normalized `AIResult` and request schemas, and a small exception hierarchy.
- `AIGateway` routes by capability, enforces `AI_REQUEST_TIMEOUT_SECONDS`, normalizes provider/model/latency metadata, and performs controlled fallback only for explicitly typed technical failures (timeout, connection, 429, 5xx, malformed response). Configuration, structured-output, and unexpected programming errors (wrapped in `ProviderInternalError`) never silently fall back; both providers failing raises `AllProvidersFailedError`.
- `QwenProvider` (Phase 2A.2) implements the `AIProvider` contract against Alibaba Model Studio's OpenAI-compatible `/chat/completions` endpoint using plain `httpx` (no SDKs). It supports text, multimodal vision (base64 data URLs), and structured JSON output (`response_format=json_object` + parse into `AIResult.data`, `StructuredOutputError` on malformed output). Models come from `QWEN_*` configuration with optional per-request `model` override; provider/HTTP errors are mapped to the gateway exception hierarchy; API keys and image data never appear in errors or logs.
- No active caller has been migrated yet: Qwen is NOT wired as the application-wide provider. All current AI still runs through the legacy Gemini/OpenRouter paths unchanged. No automated test makes a real AI API call; `scripts/test_qwen_connection.py` is a manual, developer-run smoke test.
- `AISettings` in `config.py` defines the Qwen-primary / Gemini-fallback contract; `.env`/`.env.example` carry the keys.

## Known Remaining Issues

- AI calls remain fragmented across Gemini/OpenRouter; the shared provider-neutral gateway core and the Qwen adapter exist, but no caller has been migrated to the gateway and the Gemini fallback adapter is not yet implemented.
- Clinical scan-to-care flow is not yet a unified LangGraph.
- Google Maps/Places remains active and paid-key dependent.
- Clinical rule/evidence architecture still needs later phases.
- The frontend dependency audit currently reports three high-severity advisories; dependency upgrades require a separate compatibility/security phase.

## Completed Phases

| Phase | Name | Status |
|---|---|---|
| 0 | Hackathon Rebaseline | COMPLETE |
| 1A | Supabase PostgreSQL Foundation | COMPLETE |
| 1B | Full Supabase PostgreSQL Cutover (identity/auth/domain migration) | COMPLETE |
| 2A.1 | Shared AI Gateway Core (provider-neutral, no callers migrated) | COMPLETE |
| 2A.2 | Alibaba Qwen Provider Adapter (gateway-level, no callers migrated) | COMPLETE |

The former Phase 1C is obsolete because its domain migration scope was merged into Phase 1B.

## Next Phase

**Phase 2A.3 - Gemini Fallback Adapter**

- Implement a Gemini `AIProvider` adapter for the technical-fallback role.
- Map Gemini/native API errors to the existing gateway exception hierarchy.
- Still do not migrate every caller until the gateway is proven.
- Do not revisit database migration unless a proven defect requires it.
