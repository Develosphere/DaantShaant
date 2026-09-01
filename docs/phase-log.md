# DaantShaant Phase Log

Chronological engineering history. Each entry is one bounded phase.

---

## Phase 0 — Hackathon Rebaseline

**Date:** August 2026
**Status:** COMPLETE

### Summary

Existing DaantShaant repository adopted as hackathon baseline. Rebuild-from-scratch plan discontinued.

### Key Decisions

- **Database:** MongoDB -> Supabase PostgreSQL (SQLAlchemy 2 + asyncpg + Alembic)
- **Primary AI:** Alibaba Model Studio / Qwen (qwen3.7-plus) selected as primary
- **Fallback AI:** Gemini Flash-Lite family
- **OpenRouter:** Removed from final primary architecture
- **Maps:** Google Maps/Places -> MapLibre GL JS + OpenFreeMap + OSM + Overpass API
- **LangGraph:** Unified clinical LangGraph planned (currently fragmented)
- **Auth:** Unified JWT identity with refresh token rotation planned

### Files Created

- `/context.md` — compact current-state memory for all future Qoder chats
- `/docs/phase-log.md` — this file
- `/docs/third-party-usage.md` — technology usage inventory
- `/docs/architecture.md` — current and target architecture reference
- `/AGENTS.md` — Qoder agent rules and model strategy
- `/.qoder/rules/00-core.md` — core Qoder development rules

### Constraints Observed

- No application source code modified
- No dependencies added
- No database logic changed
- Documentation and governance only

### Next

Phase 1A — Supabase PostgreSQL Foundation

---

## Phase 1A — Supabase PostgreSQL Foundation

**Date:** September 2026  
**Status:** COMPLETE

### Summary

- Added SQLAlchemy 2, asyncpg, Alembic, async engine/session factory, 15 relational models, and the `001_baseline` migration.
- Added safe PostgreSQL connection validation.
- Verified the configured Supabase PostgreSQL 17.6 development database.

### Note

Phase 1A was present as uncommitted implementation work when Phase 1B began. Phase 1B fixed its Alembic environment loading/async URL issue and applied it remotely.

---

## Phase 1B — Full Supabase PostgreSQL Cutover

**Date:** September 2026  
**Status:** COMPLETE

### Summary

The former Phase 1B identity/auth scope and Phase 1C domain scope were merged and completed as one cutover. Supabase PostgreSQL is now the sole application database.

### Database

- Fixed Alembic to load the repository-root `.env`, prefer `DATABASE_MIGRATION_URL`, fall back to `DATABASE_URL`, normalize asyncpg URLs, and preserve percent-encoded credentials.
- Applied `001_baseline` and `002_domain_compatibility`; remote database reports migration head.
- Activated AsyncSession repositories for identity, sessions, scans/reports, chat, dentists, products, orders, recommendations, and appointments.
- Verified remote `SELECT 1` and safe create/read/delete cleanup.

### Identity and Auth

- Unified all ownership on `users.id` UUID; removed the random browser clinical UUID mapping.
- Replaced bcrypt/default-secret auth with Argon2id, required-config access JWTs, opaque rotating refresh tokens, hashed `auth_sessions`, and HttpOnly refresh cookies.
- Enforced disabled accounts and patient/dentist/admin role/ownership checks.
- Removed public admin registration and added the controlled `scripts/create_admin.py` path.
- Moved frontend access tokens to memory with cookie-based session restoration.

### Domain Cutover

- Migrated users/profiles, dentists, scans/findings/reports, conversations/messages, products, product/dentist recommendations, orders, and appointments.
- Snapshot, chat-image, and finalized live scans persist relational history.
- Product/order ownership resolves through the authenticated dentist owner.
- Chat and appointment APIs no longer trust arbitrary patient IDs.

### Removal

- Deleted the runtime database connection modules for the removed datastore.
- Removed Motor, PyMongo, BSON/ObjectId usage, bcrypt, environment settings, health checks, and browser compatibility mappings.
- The old local datastore was not reachable; no accessible demo dataset required an import script.

### Validation

- Local backend suite: 60 passed, 1 opt-in integration test skipped.
- Supabase transactional integration: 1 passed (auth rotation, CRUD, FK ownership, cross-user denial, disabled account).
- Next.js production build: passed.
- Alembic: `002_domain_compatibility (head)`.

### Next

Phase 2A — Shared DaantShaant AI Gateway.

---

## Phase 2A.1 — Shared AI Gateway Core

**Date:** September 2026  
**Status:** COMPLETE

### Summary

Created a provider-neutral AI gateway foundation. No existing caller was migrated and no real external AI request was added.

### Files Created

- `orchestrator/src/orchestrator/ai/{__init__,base,schemas,exceptions,gateway}.py`
- `orchestrator/tests/test_ai_gateway.py` (fake providers only)

### Design

- `AIProvider` abstract async contract: `generate_text` / `generate_vision` / `generate_structured`.
- Normalized `AIResult` (content, provider, model, usage, latency_ms, finish_reason, raw_metadata, fallback_used, data) and `TextRequest`/`VisionRequest`/`StructuredRequest` schemas; no SDK object leaks.
- `AIGateway` routes by capability, enforces a request timeout, normalizes metadata, and applies the fallback policy.
- Exception hierarchy: technical failures (timeout/rate-limit/server/unavailable/invalid-response) are fallback-eligible; configuration, invalid-request, and structured-parse failures never fall back. Both providers failing raises `AllProvidersFailedError`.

### Configuration Contract

- Added `AISettings` to `orchestrator/src/orchestrator/config.py` (primary/fallback selection, timeout, Qwen keys/models, Gemini fallback keys). `.env` / `.env.example` already carried these keys.
- Legacy direct Gemini/OpenRouter env and runtime paths left intact and unchanged.

### Validation

- `test_ai_gateway.py` (11 tests) + `test_auth_security.py` (config import smoke, 6 tests): 17 passed. Zero external AI calls.

### Next

Phase 2A.2 — Alibaba Qwen Provider Adapter.

---

## Phase 2A.2 - Alibaba Qwen Provider Adapter

**Date:** September 2026

**Status:** COMPLETE

### Summary

Implemented the first concrete AI provider adapter (Qwen / Alibaba Model Studio) behind the shared Phase 2A.1 gateway contract. No existing caller was migrated and no automated test performs a real external AI call.

### Files Created

- `orchestrator/src/orchestrator/ai/qwen.py` (`QwenProvider`)
- `orchestrator/tests/test_qwen_provider.py` (httpx.MockTransport only)
- `scripts/test_qwen_connection.py` (manual, developer-run smoke test)

### Design

- Plain `httpx.AsyncClient` against the OpenAI-compatible `/chat/completions` endpoint; `QWEN_BASE_URL` is treated as a base URL (trailing slash handled, `/chat/completions` appended in the adapter). No Alibaba/OpenAI SDK.
- Text, multimodal vision (base64 `data:` URL parts, `QWEN_VISION_MODEL`), and structured generation (`response_format={"type":"json_object"}` plus schema instruction; parsed into `AIResult.data`; `StructuredOutputError` on malformed JSON).
- Model selection from `QWEN_*` config defaults, with an optional per-request `model` override added to the normalized request schemas.
- Error mapping: 401/403 → `ProviderConfigurationError`, 429 → `ProviderRateLimitError`, 5xx → `ProviderServerError`, transport/DNS → `ProviderUnavailableError`, HTTP timeout → `ProviderTimeoutError`, malformed success payload → `InvalidProviderResponseError`. Arbitrary programming errors are left to the gateway's non-fallback-eligible `ProviderInternalError`. No retries/backoff/fallback inside the adapter.
- Secrets: API key and image base64 never appear in exception messages or logs; error bodies are truncated and sanitized.

### Validation

- `test_ai_gateway.py` (13 tests) + `test_qwen_provider.py` (18 tests): 31 passed. Zero real API calls.

### Next

Phase 2A.3 — Gemini Fallback Adapter.

---

## Phase 2A.3 - Gemini Fallback Provider Adapter

**Date:** September 2026

**Status:** COMPLETE

### Summary

Implemented the Gemini technical-fallback provider adapter behind the shared Phase 2A.1 gateway contract, mirroring the Qwen adapter. No existing caller was migrated and no automated test performs a real external AI call.

### Files Created

- `orchestrator/src/orchestrator/ai/gemini.py` (`GeminiProvider`)
- `orchestrator/tests/test_gemini_provider.py` (httpx.MockTransport only)
- `scripts/test_gemini_connection.py` (manual, developer-run smoke test)

### Files Modified

- `orchestrator/src/orchestrator/ai/__init__.py` (export `GeminiProvider`)
- `orchestrator/src/orchestrator/config.py` (added optional `GEMINI_BASE_URL`)

### Design

- Plain `httpx.AsyncClient` against the Gemini `v1beta` `generateContent` REST endpoint; no Google SDK introduced (reuses the same REST transport shape as the legacy `_GeminiClient`). The API key travels in the `x-goog-api-key` header, never in the URL.
- Text (system turns -> `systemInstruction`, `assistant` -> `model` role, ordering preserved), multimodal vision (`inlineData` with `mimeType`/base64 `data`), and structured generation (`responseMimeType=application/json` plus schema instruction; parsed into `AIResult.data`; `jsonschema` validated; `StructuredOutputError` on malformed/invalid JSON) — consistent with the Qwen adapter from the gateway caller's perspective.
- Model selection from `GEMINI_MODEL` config default with an optional per-request `model` override.
- Error mapping: 400/401/403 -> `ProviderConfigurationError`, 429 -> `ProviderRateLimitError`, 5xx -> `ProviderServerError`, transport/DNS -> `ProviderUnavailableError`, HTTP timeout -> `ProviderTimeoutError`, malformed success payload -> `InvalidProviderResponseError`. Arbitrary programming errors remain the gateway's non-fallback-eligible `ProviderInternalError`. No retries/backoff/fallback inside the adapter (the gateway decides).
- Secrets: API key and image base64 never appear in exception messages or logs; error bodies are truncated and the key is redacted if ever echoed.

### Validation

- `test_ai_gateway.py` (13) + `test_qwen_provider.py` (18) + `test_gemini_provider.py` (25): 56 passed. Zero real API calls. Includes a gateway integration test proving Qwen technical failure falls back to Gemini (`fallback_used=True`, `provider="gemini"`).

### Status of callers

- No active business callers migrated. `GeminiProvider` is a technical-fallback adapter only. Qwen remains intended PRIMARY, Gemini intended FALLBACK.

### Next

Phase 2A.4 - AI Gateway Composition + First Caller Migration.
