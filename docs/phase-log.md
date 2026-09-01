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

---

## Phase 2A.4 - AI Gateway Composition + First Real Caller Migration

**Date:** September 2026

**Status:** COMPLETE

### Summary

Composed the production AI gateway (Qwen primary + Gemini technical fallback) and migrated exactly one real business caller to it: the orchestrator's conversational/chat text-generation path. Clinical vision, product descriptions, and the recommendation LangGraphs were deliberately left untouched.

### Files Created

- `orchestrator/src/orchestrator/ai/factory.py` (`create_ai_gateway(settings)`, lazy cached `get_ai_gateway()`, `SUPPORTED_AI_PROVIDERS`)
- `orchestrator/tests/test_ai_gateway_factory.py`
- `orchestrator/tests/test_chat_gateway_migration.py`

### Files Modified

- `orchestrator/src/orchestrator/conversation_engine.py` (all assistant text generation now goes through `AIGateway.generate_text`; legacy `openrouter_client` / `llm_provider` chain removed from this module)
- `orchestrator/src/orchestrator/ai/qwen.py` (`generate_text` now defaults to `QWEN_CHAT_MODEL` instead of leaving that field unused)
- `orchestrator/src/orchestrator/ai/__init__.py` (export factory surface)
- `orchestrator/src/orchestrator/llm_provider.py` (`_get_deterministic_fallback` renamed to the public `get_deterministic_fallback`; behavior unchanged)
- Docs: `context.md`, `docs/architecture.md`, `docs/third-party-usage.md`

### Composition

```text
create_ai_gateway(settings)
  PRIMARY  = QwenProvider    (QWEN_CHAT_MODEL)
  FALLBACK = GeminiProvider  (GEMINI_MODEL)
  timeout  = AI_REQUEST_TIMEOUT_SECONDS
```

`PRIMARY_AI_PROVIDER` / `FALLBACK_AI_PROVIDER` accept only `qwen` / `gemini` (plus an empty fallback). Unknown, empty-primary, or identical primary/fallback values raise `ProviderConfigurationError`; nothing is ever silently substituted. Adapter modules are imported inside the builders and providers are built on first use, so importing the factory composes no provider, creates no HTTP client, and performs no network I/O (verified by a test that fails if `httpx.AsyncClient` is constructed during composition).

### Caller migration

`ConversationEngine` now depends only on `AIGateway` + normalized contracts: `TextRequest(messages=[system,user], temperature, max_tokens)` -> `AIResult.content`. The request carries no provider-specific model id, so each provider resolves its own configured model. RAG (`retrieval_service.get_enhanced_prompt`), conversation memory, state context, incomplete-response completion, banned-phrase cleaning, and dentist-recommendation logic are unchanged; only the final provider invocation moved. `POST /v1/chat/message` still returns the same `SendMessageResponse` shape (no new fields). Minimal structured logging at the boundary records `status/provider/model/latency_ms/fallback_used` only - no keys, no image data, no prompt text.

Failure policy at the caller: configuration errors (`ProviderConfigurationError`) and programming errors (gateway-wrapped `ProviderInternalError`) propagate and are never masked by a provider switch. Only `AllProvidersFailedError` (both providers failing technically) - or an empty reply - degrades to the pre-existing deterministic issue-aware dental answer, so the patient still receives a message.

### Validation

- `test_ai_gateway.py` + `test_qwen_provider.py` + `test_gemini_provider.py` + `test_ai_gateway_factory.py`: 72 passed.
- `test_chat_gateway_migration.py`: 12 passed.
- Zero external AI API calls: fake gateways, in-memory `AIProvider` fakes, `httpx.MockTransport`, and a stubbed RAG boundary. The full backend suite was intentionally not run.

### Remaining legacy AI callers (untouched by design)

- Teeth Analyzer / clinical vision: direct Gemini (Phase 2B target).
- `dentist_portal/description_generator.py`: `openrouter_client` (last OpenRouter consumer).
- `recommendation_ai_system/`: `llm_provider.gemini.generate` (direct Gemini).
- `llm_provider.generate()` (OpenRouter -> Gemini -> deterministic chain) now has no callers; the module remains as the home of the deterministic dental fallback table until Phase 2A.5.

### Next

Phase 2A.5b - Remove Dead OpenRouter Infrastructure.

---

## Phase 2A.5a - Migrate Product Description Generator Off OpenRouter

**Date:** September 2026

**Status:** COMPLETE

### Summary

Migrated the last direct OpenRouter consumer — the dentist portal's product description generator — to the shared AI gateway (Qwen primary, Gemini technical fallback). No other module was touched.

### Files Modified

- `orchestrator/src/orchestrator/dentist_portal/description_generator.py` (replaced `openrouter_client` with `AIGateway.generate_text(TextRequest)`; lazy gateway resolution; preserved public signature, prompt content, JSON parsing, markdown-fence stripping, temperature/max_tokens, and deterministic fallback)

### Files Created

- `orchestrator/tests/test_description_gateway_migration.py` (12 tests using fake providers/gateways only)

### Call path

```text
Old: generate_product_description -> openrouter_client.generate_chat_response -> OpenRouter API
New: generate_product_description -> get_ai_gateway() -> AIGateway.generate_text(TextRequest)
     -> QwenProvider (QWEN_CHAT_MODEL) PRIMARY
     -> GeminiProvider (GEMINI_MODEL) FALLBACK (technical failure only)
```

### Failure behavior

- Configuration errors (`ProviderConfigurationError`) and programming errors (`ProviderInternalError`) propagate; never masked by fallback.
- `AllProvidersFailedError` (both providers fail technically) degrades to the existing deterministic product description fallback.
- Empty or unparseable JSON responses also degrade to the deterministic fallback.

### Validation

- `test_description_gateway_migration.py`: 12 passed.
- `test_ai_gateway_factory.py` + `test_chat_gateway_migration.py`: 27 passed (no regressions).
- Zero external AI API calls: fake providers and spy gateways only.

### OpenRouter status

- `description_generator.py` no longer imports or calls `openrouter_client`.
- `openrouter_client.py` still has one internal runtime reference: `llm_provider.py` imports it inside `LLMProvider.__init__()`, reached only by the recommendation system (out of scope for this phase).
- `openrouter_client.py` cannot yet be safely removed; deletion belongs in Phase 2A.5b.

### Next

Phase 2A.5b - Remove Dead OpenRouter Infrastructure.
