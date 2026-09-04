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

> Correction (recorded in Phase 2A.5b below): OpenRouter was **not** dead before 2A.5b — the product recommendation system was still its last live consumer via `llm_provider.gemini.generate`. The next phase was therefore reframed as "Migrate Recommendation AI Off Legacy LLM Provider" (2A.5b), and legacy-infrastructure removal became 2A.5c.

---

## Phase 2A.5b - Migrate Recommendation AI Off Legacy LLM Provider

**Date:** September 2026

**Status:** COMPLETE

### Summary

Migrated the product recommendation system's two AI text-generation calls to the shared AI gateway (Qwen primary, Gemini technical fallback). This removed the recommendation system's dependency on `llm_provider`/`openrouter_client` and made the Product Recommendation LangGraph fully provider-neutral. No other subsystem was touched.

### Files Modified

- `orchestrator/src/orchestrator/recommendation_ai_system/recommendation_agent.py` (`generate_response_node` now builds a `TextRequest` and calls `AIGateway.generate_text(...)`; lazy `_get_gateway()`; removed `from orchestrator.llm_provider import llm_provider`; preserved prompt, temperature 0.4 / max_tokens 800, and the deterministic template fallback)
- `orchestrator/src/orchestrator/recommendation_ai_system/tools.py` (`rank_recommendations` now builds a `TextRequest` and calls `AIGateway.generate_text(...)`; lazy `_get_gateway()` + injectable `gateway` kwarg; removed the `llm_provider` import; preserved prompt, product-summary context, temperature 0.2 / max_tokens 600, markdown-fence stripping, JSON-array parsing, and the deterministic reranking fallback)

### Files Created

- `orchestrator/tests/test_recommendation_gateway_migration.py` (14 tests using fake providers / spy gateways only)

### Preserved behavior

- LangGraph topology unchanged: `START -> search_products -> (conditional similarity) -> get_details -> rank -> log_session -> generate_response -> END`, plus `terminate_low_similarity`.
- Ranking/product-selection logic, database queries, similarity behavior, session logging, and the public `RecommendResponse` contract are untouched.
- Prompt intent and supplied product/issue context preserved; requests use `model=None` so Qwen resolves `QWEN_CHAT_MODEL` and Gemini resolves `GEMINI_MODEL`.

### Failure behavior

- Qwen technical failure -> Gemini fallback automatically through the gateway.
- Technical double failure (`AllProvidersFailedError`) or empty gateway output -> pre-existing deterministic template/ranking fallback.
- `ProviderConfigurationError` / `ProviderInternalError` propagate; never masked.
- `rank_recommendations` kept on `generate_text` + existing JSON-array parsing (not forced into `generate_structured`, whose shared contract is a `dict`).

### Validation

- `test_recommendation_gateway_migration.py` + `test_ai_gateway.py`: 26 passed.
- `test_description_gateway_migration.py` + `test_chat_gateway_migration.py`: 24 passed (no regressions).
- Zero external AI API calls.

### OpenRouter / legacy audit (post-migration)

- `openrouter_client.generate_chat_response` runtime callers = **0**.
- `llm_provider.LLMProvider` failover-chain runtime callers = **0**.
- `llm_provider.py` still imported by `conversation_engine` for `get_deterministic_fallback` only, and its module-level `llm_provider = LLMProvider()` global still imports/instantiates `openrouter_client`. So `llm_provider.py` and `openrouter_client.py` cannot yet be deleted independently — cleanup is deferred to Phase 2A.5c.

### Next

Phase 2B — Semantic Dental Relevance.

---

## Phase 2A.5c - Remove Legacy OpenRouter / LLM Infrastructure

**Date:** September 2026

**Status:** COMPLETE

### Summary

Relocated the deterministic dental fallback out of the legacy `llm_provider.py` into a provider-independent module (`ai/fallbacks.py`), then deleted `llm_provider.py` and `openrouter_client.py`. This removed the last vestiges of the OpenRouter → Gemini failover chain from the orchestrator. No business module was affected — both files had zero active runtime callers after Phase 2A.5b.

### Files Created

- `orchestrator/src/orchestrator/ai/fallbacks.py` — provider-independent deterministic dental fallback table and `get_deterministic_fallback(user_message, active_issue)` function. No AI provider, no networking, no HTTP client.
- `orchestrator/tests/test_deterministic_fallback.py` (9 tests verifying fallback behavior, import isolation, and no networking dependency)

### Files Modified

- `orchestrator/src/orchestrator/conversation_engine.py` (updated both `get_deterministic_fallback` imports from `orchestrator.llm_provider` to `orchestrator.ai.fallbacks`; removed legacy docstring reference)
- `orchestrator/tests/test_chat_gateway_migration.py` (removed legacy `llm_provider`/`openrouter_client` imports and monkeypatches from guard test)
- `orchestrator/tests/test_description_gateway_migration.py` (removed legacy `openrouter_client` import and monkeypatch from guard test)
- `orchestrator/tests/test_recommendation_gateway_migration.py` (removed legacy `openrouter_client` import and monkeypatch from guard test)
- Docs: `context.md`, `docs/phase-log.md`, `docs/third-party-usage.md`, `docs/architecture.md`

### Files Deleted

- `orchestrator/src/orchestrator/llm_provider.py` — `LLMProvider`, `_GeminiClient`, module-level `llm_provider = LLMProvider()` global, and the old deterministic fallback table
- `orchestrator/src/orchestrator/openrouter_client.py` — `OpenRouterClient` and module-level `openrouter_client = OpenRouterClient()` global

### Env / Config

- No `OPENROUTER_*` entries existed in `.env.example` or orchestrator `config.py` — no env cleanup was needed.
- Teeth Analyzer retains its own separate `TEETH_ANALYZER_OPENROUTER_API_KEY` / `TEETH_ANALYZER_OPENROUTER_MODEL` config (out of scope; Phase 2C target).
- `httpx` retained (required by `QwenProvider` and `GeminiProvider`).

### Targeted Legacy Audit (post-cleanup)

- `from orchestrator.llm_provider` / `import orchestrator.llm_provider` in orchestrator source: **0**
- `from orchestrator.openrouter_client` / `import orchestrator.openrouter_client` in orchestrator source: **0**
- `LLMProvider(` / `llm_provider.` in orchestrator source: **0**
- `openrouter_client` / `generate_chat_response(` in orchestrator source: **0**
- `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` in orchestrator source: **0**
- Teeth Analyzer (`services/teeth_analyzer/`) retains its own `backends/openrouter.py`, `TEETH_ANALYZER_OPENROUTER_API_KEY`, and `openrouter_model` config — clinical vision legacy OpenRouter path remains for Phase 2C.

### Validation

- `test_deterministic_fallback.py`: 9 passed.
- `test_chat_gateway_migration.py`: 12 passed.
- `test_description_gateway_migration.py`: 12 passed.
- `test_recommendation_gateway_migration.py`: 13 passed.
- `test_ai_gateway_factory.py` + `test_ai_gateway.py`: 26 passed.
- Total: 72 passed. Zero external AI API calls.

### Phase 2A Completion

All Phase 2A acceptance criteria satisfied:

- Shared AIGateway exists and is composed in production.
- Qwen adapter (primary) and Gemini adapter (fallback) exist.
- Chat text generation, product description generation, and product recommendation text generation all use the gateway.
- Legacy orchestrator `LLMProvider` is REMOVED.
- Legacy orchestrator `openrouter_client.py` is REMOVED.
- Deterministic fallback relocated and behavior preserved.

### Next

Phase 2B — Semantic Dental Relevance.

---

## Phase 2B.1 - Semantic Dental Relevance Core (MVP Fast Track) - COMPLETE

### Summary

Created the standalone Semantic Dental Relevance core: given an image, it decides whether the image is semantically appropriate for dental/oral screening. Categories: relevant / retake / unrelated. External jaw/cheek swelling may be relevant even without visible teeth; ordinary face selfies without useful oral/jaw visibility are unrelated. No diagnosis, severity, or treatment logic exists at this stage. Production scan routes (snapshot/upload/WebSocket) are NOT yet wired - deliberately, that is Phase 2B.2.

### Files Created

- `orchestrator/src/orchestrator/clinical/__init__.py` + `clinical/relevance.py` - `DentalRelevanceResult` (classification, is_dental_relevant, confidence, relevance_score, visible_regions, reason, retake_reason, recommended_action), a short relevance prompt, the JSON schema, and `evaluate_dental_relevance(image_base64, content_type, gateway=None)`. Uses `StructuredRequest` via `AIGateway.generate_structured` (Qwen primary -> Gemini technical fallback); `model=None` so each provider resolves its own configured default. Gateway resolved lazily via `get_ai_gateway()` when not injected; no concrete provider imports.
- `orchestrator/tests/test_dental_relevance.py` (19 tests; fake gateways/in-memory providers; zero real AI calls; no real images or network)
- `scripts/test_dental_relevance.py` - manual `--image` smoke script (developer-run only, not part of the test suite)

### Key Decisions

- Action mapping is deterministic: relevant -> continue, retake -> retake, unrelated -> reject. No confidence thresholds invented; model confidence/relevance_score are preserved for later evaluation. `is_dental_relevant` is derived (relevant -> true; retake is not "proceed").
- Provider failures propagate as typed gateway errors - a provider outage is never reported as "unrelated". `ProviderConfigurationError`/`ProviderInternalError`/`StructuredOutputError` all propagate; malformed/missing structured output raises `StructuredOutputError`.
- Privacy: image base64 is never logged, never embedded in errors, and not persisted by the service.

### Validation

- `tests/test_dental_relevance.py`: 19 passed. Zero external AI API calls. No other suites required (gateway core untouched).

### Next

Phase 2B.2 - Scan Pipeline Relevance Integration.

---

## Phase 2B.2 - Production Semantic Relevance Integration

**Date:** September 2026
**Status:** COMPLETE (Phase 2B fully complete)

### Summary

Wired the Phase 2B.1 semantic-relevance core into all three production scan modes (snapshot, upload, live WebSocket). Clinical vision is now gated behind relevance: relevant images continue to the unchanged Teeth Analyzer; retake/unrelated stop before clinical vision. Relevance routing lives in ONE shared helper consumed by every scan mode.

### Integration Point

`orchestrator/src/orchestrator/pipeline.py::run_scan_with_relevance(request, gateway=None) -> ScanOutcome` is the single reusable helper. Snapshot and upload are the same HTTP endpoint (`POST /v1/teeth/analyze`); live `process_frame` calls the same helper. No logic duplicated across routes.

### Files Modified

- `orchestrator/src/orchestrator/pipeline.py` - added `RelevanceInfo`, `ScanOutcome`, and `run_scan_with_relevance` (relevance evaluated before the combined quality+vision analyzer call; safe `[RELEVANCE]` log)
- `orchestrator/src/orchestrator/main.py` - `/v1/teeth/analyze` now returns `ScanOutcome`, calls the helper, persists relevance only for `analyzed` scans
- `orchestrator/src/orchestrator/live_session.py` - `process_frame` gates each analyzed frame on relevance; sends lightweight `relevance.retake` / `relevance.rejected` status without ending the session
- `orchestrator/src/orchestrator/repositories/clinical.py` - `ScanRepository.add_result(..., relevance=...)` persists `relevance_score` + `relevance_result` (existing columns)

### Files Created

- `orchestrator/tests/test_scan_relevance_integration.py` - 13 focused tests (fake relevance + fake clinical analyzer)

### Key Decisions

- Routing uses `recommended_action`/`classification`, never the `is_dental_relevant` boolean, so retake stays distinct from unrelated/reject.
- Provider failure != bad image: gateway errors propagate (HTTP) or fall to the safe analysis-error path (live) and the session continues; never fabricated as `unrelated`.
- A bad live frame does not kill the session; `frames_analyzed` counts only real clinical analyses; later relevant frames are still processed.
- Temporary ordering limitation: the Teeth Analyzer still fuses mechanical quality + clinical vision in one request, so relevance runs before that combined call (gated images skip the analyzer entirely, saving expensive vision). Phase 2C may reorganize the boundary.
- No new DB schema/migration (relevance columns already in the baseline). No concrete-provider imports added to scan business logic.

### Validation

- `tests/test_scan_relevance_integration.py` + `tests/test_dental_relevance.py`: 31 passed. Zero external AI API calls. App import smoke OK.

### Next

Phase 2C - Qwen Clinical Vision.

---

## Phase 2C - Qwen Clinical Vision (Teeth Analyzer) - COMPLETE

**Date:** September 2026
**Status:** COMPLETE

### Summary

Migrated the Teeth Analyzer service's clinical vision to a SERVICE-LOCAL provider policy: **Qwen PRIMARY -> Gemini TECHNICAL FALLBACK**, and removed all active OpenRouter runtime usage project-wide (ZERO active references). The service stays self-contained - it does NOT call the orchestrator and shares no code with the orchestrator gateway (no circular dependency); it mirrors the proven gateway design in its own stack. Image preprocessing / mechanical-quality logic and the public scan contract were preserved; Diagnosis (:8002) was not rewritten. Clinical output is structured VISUAL SCREENING (not a definitive diagnosis), compatible with existing downstream.

### Files Created

- `services/teeth_analyzer/src/teeth_analyzer/backends/errors.py` - typed exception hierarchy: `ProviderTechnicalError` subclasses (timeout/unavailable/rate-limit/server/invalid-response) carry `fallback_eligible=True`; `ProviderConfigurationError` / `ProviderInternalError` are non-fallback; `AllProvidersFailedError`.
- `services/teeth_analyzer/src/teeth_analyzer/backends/vision_common.py` - ONE shared clinical-vision prompt + `parse_findings` normalizer so both providers return the SAME internal shape (`VisualFinding[]`). Screening wording ("NOT a definitive diagnosis and NOT treatment advice"); allowed finding codes preserved for Diagnosis but worded possible/suspected.
- `services/teeth_analyzer/src/teeth_analyzer/backends/qwen.py` - `analyze_with_qwen` (async, plain httpx): OpenAI-compatible `{QWEN_BASE_URL}/chat/completions`, `Authorization: Bearer {DASHSCOPE_API_KEY}`, multimodal (text + `data:image/jpeg;base64,...`), `response_format=json_object`; provider/HTTP errors mapped to the typed hierarchy; keys/base64 redacted from errors.
- `services/teeth_analyzer/src/teeth_analyzer/provider_policy.py` - `run_clinical_vision(jpeg_bytes, locale) -> ClinicalVisionOutcome(findings, provider, model, latency_ms, fallback_used)`: Qwen first, single Gemini retry only on a `fallback_eligible` technical error, non-fallback errors propagate, both-technical-failure raises `AllProvidersFailedError`; `[CLINICAL_VISION]` log line (never base64/keys/Authorization).
- `services/teeth_analyzer/tests/conftest.py` - `sys.path` shim so the focused tests import `teeth_analyzer` from any venv/cwd.
- `services/teeth_analyzer/tests/test_clinical_vision.py` - 19 tests (16 required + 3 extra); zero real AI (httpx.MockTransport + fakes + stubbed quality gate + tiny fake base64).

### Files Modified

- `services/teeth_analyzer/src/teeth_analyzer/backends/gemini.py` - rewritten to async plain-httpx `v1beta` `{model}:generateContent` (`x-goog-api-key` header, `inlineData` base64, `responseMimeType=application/json`); `google-generativeai` SDK removed; technical-fallback error mapping.
- `services/teeth_analyzer/src/teeth_analyzer/inference.py` - `analyze_image` now async; mechanical-quality gate PRESERVED and runs BEFORE any AI call; policy-driven vision; `AllProvidersFailedError` degrades to stub only if `TEETH_ANALYZER_FALLBACK_TO_STUB` is enabled, else `VisionBackendError` (503); config/programming errors propagate.
- `services/teeth_analyzer/src/teeth_analyzer/config.py` - shared-first env via `AliasChoices` (`DASHSCOPE_API_KEY`, `QWEN_BASE_URL`, `QWEN_VISION_MODEL=qwen3.7-plus`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_BASE_URL`, `AI_REQUEST_TIMEOUT_SECONDS=60`), `TEETH_ANALYZER_*` aliases preserved; `backend` default `stub -> qwen`; OpenRouter fields removed.
- `services/teeth_analyzer/src/teeth_analyzer/main.py` - endpoint awaits async `analyze_image`; `/health` bumped to v0.3.0 with `qwen_configured` / `qwen_vision_model` / `gemini_configured`.
- `services/teeth_analyzer/src/teeth_analyzer/backends/__init__.py` - exports `analyze_with_qwen` / `analyze_with_gemini` / `analyze_with_stub`.
- `services/teeth_analyzer/pyproject.toml` - removed `google-generativeai`; added `httpx>=0.27.0`.
- `orchestrator/src/orchestrator/conversation_engine.py` - stale docstring reference to the legacy router reworded (no behavior change).

### Files Deleted

- `services/teeth_analyzer/src/teeth_analyzer/backends/openrouter.py` - the last active OpenRouter consumer in the repo.

### Key Decisions

- Service-local policy, NOT an orchestrator HTTP call: avoids a circular dependency and keeps the analyzer independently deployable, while mirroring the gateway's proven fallback classification.
- Fallback is TECHNICAL only (timeout/connection/429/5xx/malformed envelope). Configuration/programming errors propagate and are NEVER masked by fallback or the offline stub.
- Both providers normalize to the SAME `VisualFinding[]` shape via one shared prompt/parser, so the public `AnalyzeResponse` and Diagnosis (:8002) are unchanged; provider/model/latency/fallback metadata stays internal (never leaked into the public scan API).
- Clinical output is framed as visual SCREENING observations (possible/suspected), not definitive diagnosis or treatment advice - consistent with the awareness-tool positioning.
- Mechanical-quality rejection skips AI entirely (preserved ordering); preprocessing was NOT rewritten.
- Disease/severity mapping and Diagnosis logic left for Phase 3B (not touched here).

### OpenRouter audit (post-removal)

- `services/teeth_analyzer/src/teeth_analyzer/backends/openrouter.py`: deleted.
- `TEETH_ANALYZER_OPENROUTER_API_KEY` / `_MODEL` config fields: removed (`.env.example` already clean; any stray legacy env is ignored via `extra="ignore"`).
- Active runtime references project-wide: **0** - verified by `test_16_openrouter_has_zero_runtime_callers`, which asserts the module is unimportable and that inference/provider_policy/qwen/gemini/vision_common contain no OpenRouter token. Remaining mentions are historical docs (`prd.md`, `TROUBLESHOOTING.md`, prior phase-log entries) and the assertion test only.

### Validation

- `services/teeth_analyzer/tests/test_clinical_vision.py`: 19 passed (run via `orchestrator/.venv` with a `conftest.py` path shim). Zero external AI API calls. Only the focused Teeth Analyzer suite was run (not the monorepo suite), per phase scope.

### Next

Phase 3B-lite - Evidence / Rule-Based Triage (do NOT start deep Phase 3A RAG).

---

## Phase 3B-lite - Deterministic Clinical Triage - COMPLETE

**Date:** September 2026
**Status:** COMPLETE

### Summary

Replaced the legacy hard-coded disease/severity mapping in the Diagnosis service (`services/diagnosis/`) with a deterministic, rule-based triage engine. Visual findings from the Teeth Analyzer are now screening observations that feed explicit rules producing safer, non-definitive patient-facing wording. NO LLM call is introduced — the same input always produces the same output.

### Files Created

- `services/diagnosis/src/diagnosis/triage.py` — the deterministic rule engine: one `TriageRule` per finding code, urgency ordering (routine < soon < urgent < emergency), deduplication, limitation injection, specialist merging, and safe observability logging. No imports of any AI provider, HTTP client, or external service.
- `services/diagnosis/tests/test_triage.py` — 27 focused tests covering all acceptance criteria. Zero external AI calls.
- `services/diagnosis/tests/conftest.py` — path shim so the focused tests run from any venv/cwd.

### Files Modified

- `packages/dantshaant_common/src/dantshaant_common/schemas.py` — additive: `UrgencyLevel` enum, `TriageResult` model, `ConditionLabel.MISSING_OR_DAMAGED_TOOTH`, `VisualFinding.visibility`, `DiagnoseResponse.triage: TriageResult | None`.
- `services/diagnosis/src/diagnosis/classifier.py` — refactored to delegate finding→concern/severity/action mapping to `triage.py`; legacy `DiagnoseResponse` contract preserved by adapting `TriageDecision` back into the existing fields; old inline `LABEL_MAP`/`CONDITION_META`/`CONDITION_PRIORITY`/`_pick_primary_finding` removed.
- `services/teeth_analyzer/src/teeth_analyzer/backends/vision_common.py` — `parse_findings` now passes through the `visibility` field from clinical vision JSON output (Phase 3B-lite triage uses it only to state screening limitations).
- `apps/web/lib/types.ts` — additive: `TriageResult` type, `UrgencyLevel` type, `visibility` on `VisualFinding`, `triage` on `DiagnosisResult`.
- `apps/web/components/DiagnosisReport.tsx` — prefers safer triage wording when available (condition_summary as headline, triage verdict/concerns/actions/limitations block); falls back gracefully when `triage` is null; label "AI Diagnosis" → "AI Screening Report"; "Detected condition" → "AI screening — possible concern".
- `apps/web/app/globals.css` — styles for the triage block (verdict, sublabel, list, urgency badge).
- `context.md` — Phase 3B-lite recorded as complete; next phase updated.
- `docs/phase-log.md` — this entry.

### Safety Fixes

- `missing_or_damaged_teeth` previously mapped to `ConditionLabel.ADVANCED_CAVITY`. Now routes to `ConditionLabel.MISSING_OR_DAMAGED_TOOTH` with urgency `soon` and restorative evaluation. Legacy aliases (`broken_teeth`, `missing_teeth`, `damaged_teeth`) corrected.
- `cavity_advanced` patient-facing output: "Possible significant tooth decay / structural damage" (never "Advanced Cavity" or "you have advanced cavity").
- All rule outputs use non-definitive language: "possible concern", "may be consistent with", "AI screening suggests", "should be confirmed by a licensed dentist". No rule claims a confirmed disease, prescribes treatment, or guarantees an outcome.

### API / Frontend Compatibility

- Legacy `DiagnoseResponse` contract fully preserved (condition_label, severity, confidence, confidence_threshold, meets_threshold, action_trigger, disclaimer, diagnosed_at). The `triage` field is additive and optional — a consumer that ignores it validates without error.
- Frontend renders safer wording from `triage` when present, falls back to legacy fields otherwise.

### Validation

- `services/diagnosis/tests/test_triage.py`: 27 passed, 0 failed. Zero external AI API calls. Only the focused diagnosis test suite was run.

### Next

Phase 4-lite — Unified Clinical LangGraph.

---

## Phase 4-lite — Unified Clinical LangGraph - COMPLETE

**Date:** September 2026
**Status:** COMPLETE

### Summary

Unified the clinical scan-to-care flow into a single, deterministic LangGraph StateGraph (`orchestrator/src/orchestrator/clinical/graph.py`). The graph orchestrates the end-to-end pipeline:
`START → intake → relevance → [route] → clinical_vision → triage → report → persist → END`

Relevance gating (`evaluate_dental_relevance`), clinical vision (`TeethAnalyzerClient` HTTP boundary), diagnosis and deterministic triage (`DiagnosisClient` HTTP boundary), and persistence (`ScanRepository`) remain modular service boundaries. No triage rules or AI provider logic are duplicated inside the orchestrator or graph.

### Topology

```text
START
  ↓
intake
  ↓
relevance ──[retake]───→ END
          ──[reject]───→ END
          ──[continue]─→ clinical_vision
                              ↓
                            triage (extracts DiagnosisClient triage payload)
                              ↓
                            report
                              ↓
                            persist (persists if db_session provided)
                              ↓
                             END
```

### Key Highlights & Boundaries Preserved

- **Deterministic Orchestration:** LangGraph serves purely as a state machine coordinator; no external LLM calls or patient data leakage introduced by the graph layer.
- **Service Boundaries Maintained:**
  - `relevance_node` calls `evaluate_dental_relevance()`.
  - `clinical_vision_node` calls `run_teeth_analysis_pipeline()` (Teeth Analyzer HTTP service).
  - `triage_node` reads `DiagnoseResponse.triage` returned by the Diagnosis service (does not import `diagnosis.triage` directly).
  - `persist_node` invokes `ScanRepository.add_result()` when `db_session` is provided.
- **Shared Common Path:** `pipeline.run_scan_with_relevance(...)` delegates to `run_clinical_graph(...)`, preserving the exact `ScanOutcome` response shape across snapshot, upload, and live WebSocket frame processing.
- **Safe Observability Trace:** Appends node execution records `{"node": ..., "status": ..., "duration_ms": ...}` without image base64, prompts, or secrets.

### Validation

- `orchestrator/tests/test_clinical_graph.py` + `orchestrator/tests/test_scan_relevance_integration.py`: 26 passed, 0 failed in 4.15s. Zero external AI API calls.

### Next

Phase 6 Fast Track — Dentist Discovery + OSM/Overpass + MapLibre/OpenFreeMap.

---

## Phase 6 Fast Track — Dentist Discovery + OSM/Overpass + MapLibre/OpenFreeMap

**Date:** September 2026
**Status:** COMPLETE

### Summary

Replaced Google Maps / Places runtime dependencies across frontend and backend with an open mapping and discovery stack:
- **Map rendering:** MapLibre GL JS + OpenFreeMap Liberty style vector tiles
- **External Dentist Discovery:** OpenStreetMap via Overpass API (`amenity=dentist`, `healthcare=dentist`)
- **Address Search & Autocomplete:** OpenStreetMap Nominatim proxy
- **Patient Location:** Browser `navigator.geolocation` + Nominatim reverse geocode fallback
- **Deterministic Ranking:** Specialization match priority > Verified Platform status > Distance > Partner tiebreaker
- **Integration:** Wired triage `recommended_specialist` from clinical screening report directly to dentist discovery

Google Maps / Places active runtime callers: **ZERO**.

### Files Created

- `orchestrator/src/orchestrator/dentist_recommendation/osm_dentists.py` (Overpass OSM dentist discovery, normalization, Haversine distance, caching, timeout & safe error fallbacks)
- `orchestrator/src/orchestrator/dentist_recommendation/ranking.py` (Deterministic multi-factor dentist ranking engine)
- `apps/web/lib/geo-location.ts` (Browser GPS `navigator.geolocation` with Nominatim reverse geocode)
- `apps/web/lib/maplibre.ts` (MapLibre GL JS client-side loader with OpenFreeMap Liberty vector tile style)
- `orchestrator/tests/test_dentist_discovery.py` (12 focused unit tests for OSM normalization, ranking, safety, Google Maps absence, LangGraph flow)

### Files Modified

- `orchestrator/src/orchestrator/dentist_recommendation/geocoding.py` (Removed Google Geocoding API, implemented OSM Nominatim)
- `orchestrator/src/orchestrator/dentist_recommendation/autocomplete_service.py` (Removed Google Places autocomplete/details, pure Nominatim)
- `orchestrator/src/orchestrator/dentist_recommendation/places_service.py` (Replaced Google Places API calls with OSM discovery adapter)
- `orchestrator/src/orchestrator/dentist_recommendation/dentist_agent.py` (LangGraph workflow updated to query OSM and use deterministic ranking)
- `orchestrator/src/orchestrator/dentist_portal/models.py` (Added `source`, `website`, `is_registered` to `DentistPin`)
- `orchestrator/src/orchestrator/config.py` (Added `MapSettings`, marked `google_maps_api_key` deprecated)
- `apps/web/lib/google-maps.ts` (Replaced Google Maps loader with re-exports of `geo-location.ts`)
- `apps/web/lib/location-autocomplete.ts` (Removed Google Places autocomplete, pure backend Nominatim proxy)
- `apps/web/lib/dentist-recommend.ts` (Updated `DentistPin` TypeScript interface)
- `apps/web/components/dentists/LocationPickerModal.tsx` (Nominatim autocomplete search + GPS button)
- `apps/web/components/dentists/DentistMapView.tsx` (MapLibre GL JS + OpenFreeMap interactive map, OSM directions, call clinic, no fake booking for external OSM clinics)
- `apps/web/components/DiagnosisReport.tsx` (Passed triage `recommended_specialist` to FindDentistsButton)
- Docs: `context.md`, `docs/third-party-usage.md`, `docs/phase-log.md`

### Validation

- `orchestrator/tests/test_dentist_discovery.py`: 12 passed. Zero real external network calls.
- Full test suite (`orchestrator/tests/`): 247 passed, 1 skipped.
- Frontend build & typecheck (`apps/web`): `npm run build` completed 100% successfully (26/26 static routes generated).

### Next

Phase 8-lite — Evaluation Harness + Demo Metrics.

---

## Phase 8-lite — Evaluation Harness + Demo Metrics

**Date:** September 2026
**Status:** COMPLETE

### Summary

Implemented a reproducible, lightweight clinical evaluation harness and metric calculation engine for DaantShaant:
- **Manifest Schema & Fixture:** Flexible JSON manifest supporting `expected_relevance`, `expected_findings`, `expected_urgency`, `expected_specialist`, and third-party provenance metadata (`source`, `license`, `attribution`).
- **Metrics Calculation:**
  - Semantic relevance accuracy, class counts, and confusion matrix
  - Multi-label clinical findings set-based precision, recall, F1, and exact match rate
  - Deterministic triage urgency and specialist match accuracy
  - Patient-facing safety phrasing violation detection (flags definitive diagnosis claims)
  - Latency distribution statistics (mean, median, p95, min, max)
  - AI provider fallback rate monitoring
- **Dentist Ranking Benchmark:** Verifies specialist clinical relevance priority over commercial partner status across standard scenarios.
- **Modes:** Offline/mock simulation mode (default) and explicit `--real` mode.
- **CLI:** `scripts/run_evaluation.py` producing human-readable tables and judge-friendly demo summary JSON.
- **Data Policy:** Zero private or patient medical images committed; raw dataset files remain external to Git.

### Files Created

- `orchestrator/src/orchestrator/evaluation/__init__.py`
- `orchestrator/src/orchestrator/evaluation/schemas.py`
- `orchestrator/src/orchestrator/evaluation/metrics.py`
- `orchestrator/src/orchestrator/evaluation/runner.py`
- `orchestrator/src/orchestrator/evaluation/fixtures/manifest.example.json`
- `scripts/run_evaluation.py`
- `orchestrator/tests/test_evaluation.py` (16 unit tests)
- `docs/evaluation.md`

### Files Modified

- `context.md`
- `docs/phase-log.md`

### Validation

- `orchestrator/tests/test_evaluation.py`: 16 passed, 0 failed in 0.60s. Zero real external network calls.
- `scripts/run_evaluation.py`: Successfully generated summary table and JSON output.

### Next

Phase 10 Fast Track — Final UI Integration + Demo UX.

---

## Phase 10 Fast Track — Final UI Integration + Demo UX Polish

**Date:** September 2026
**Status:** COMPLETE

### Summary

Unified and polished the frontend interface across the end-to-end patient journey for hackathon demonstration:
- **Hero Oral Scan Experience:** Multi-stage client-side progress tracker with elapsed time indicators and reassuring phased messages (15s/35s) for smooth long-running inference UX. Prevented duplicate requests while keeping the active preview image preserved. Added a built-in "Try sample demo scan" option for instant evaluation without uploading external files.
- **Triage-First Screening Report:** Prioritized "AI Screening Verdict" over definitive diagnosis labels, displaying readable possible concerns, semantic urgency levels (`routine`, `soon`, `urgent`, `emergency`), human-friendly finding names (e.g. "Possible decay-related visual finding", "Visible tartar / calculus"), confidence labeled as "AI visual confidence", explicit limitations, and visible non-medical screening safety disclaimers.
- **Dentist Discovery & MapLibre OpenFreeMap:** Enhanced bi-directional interaction between dentist cards and OpenFreeMap vector map (clicking a card pans/zooms to the pin; clicking a pin selects the dentist). Distinguished verified platform providers (supporting consultation booking) from external OpenStreetMap clinics (providing direct call and directions without fake booking buttons). Provided clean, friendly geolocation error handling with instant location search.
- **Safety Identity & Friendly Error Mapping:** Standardized chat assistant branding to "DaantShaant AI Assistant" / "Your AI oral-health companion". Intercepted raw backend JSON errors (`downstream_unavailable`, timeouts, relevance retakes/rejections) into clean, polite user-facing guidance.

### Files Modified

- `apps/web/lib/types.ts` (Added `RelevanceInfo`, enhanced `PipelineResult` with status and relevance metadata)
- `apps/web/lib/api.ts` (Friendly user-facing error message mapping, relevance status check, removed raw JSON errors)
- `apps/web/components/dentists/FindDentistsButton.tsx` (Removed legacy `google-maps` import, replaced with `geo-location`)
- `apps/web/components/dentists/DentistMapView.tsx` (Card-to-map focus interaction, external clinic badge, friendly geolocation denial fallback)
- `apps/web/components/DiagnosisReport.tsx` (Triage-first presentation, human-readable finding names, urgency levels, safety statement)
- `apps/web/components/CameraPanel.tsx` (Multi-stage progress UX, elapsed timer, 15s/35s messages, demo sample image helper)
- `apps/web/components/ChatInterface.tsx` (Branding and assistant safety identity updates)
- `apps/web/components/ChatMessage.tsx` (Standardized assistant sender label)
- `apps/web/app/scan/page.tsx` (Polished copy and screening tool description)
- `apps/web/app/globals.css` (Added semantic urgency classes and progress styles)
- `context.md` (Updated state and completed phases)
- `docs/phase-log.md` (Appended Phase 10 Fast Track log)

### Validation

- Next.js Production Build (`npm run build` in `apps/web`): Succeeded with exit code 0. All 26 static routes generated cleanly.
- Code audit completed for scan, report, dentist map, and chat interfaces.

### Next

Phase 10.1 — Bilingual English/Urdu + Light/Dark Theme + Public Copy Hardening.

---

## Phase 10.1 — Bilingual English/Urdu + Light/Dark Theme + Public Copy Hardening

**Date:** September 2026
**Status:** COMPLETE

### Summary

Implemented end-to-end bilingual English/Urdu localization, dynamic Light/Dark theme switching, address language synchronization, and hardened public-facing copy:
- **Bilingual i18n System:** English (DEFAULT) and Urdu dictionaries with 100% key parity (190 keys). Real-time directionality switching (`dir="ltr"` / `dir="rtl"`), `lang="en" | "ur"`, and Urdu typography fallback (`"Noto Nastaliq Urdu"`, `"Noto Sans Arabic"`).
- **Theme System:** Light (DEFAULT) and Dark themes with `data-theme="light"` / `data-theme="dark"` on `<html>`. Rich design tokens ensuring high contrast across all components with zero washed-out or white-on-white text issues.
- **Geocoding & Address Synchronization:** Frontend passes active `locale` (`en` or `ur`) to backend autocomplete/resolve routes and client reverse geocoding with `Accept-Language` headers, ensuring Nominatim results match user language choice.
- **Public-Facing Copy Hardening:** Removed stack/implementation terminology (`OSM`, `Nominatim`, `OpenStreetMap`, `OpenFreeMap`, `MapLibre`, `Qwen`, `Gemini`, `LangGraph`, `Supabase`, `Python`, `API`, model providers) from user-facing screens while keeping legal map attribution.
- **Responsible Identity:** Standardized brand and identity to "DaantShaant Oral Health Assistant" and "Your oral-health companion", clarifying screening is informational and does not replace a licensed human dentist.
- **Header Controls:** Language toggle (`EN | اردو`) and theme toggle (☀️ / 🌙) on portal and public headers.

### Files Created

- `apps/web/i18n/types.ts`
- `apps/web/i18n/en.ts`
- `apps/web/i18n/ur.ts`
- `apps/web/i18n/context.tsx`
- `apps/web/i18n/index.ts`
- `apps/web/theme/context.tsx`
- `apps/web/theme/index.ts`

### Files Modified

- `apps/web/app/globals.css`
- `apps/web/app/layout.tsx`
- `apps/web/components/portal/PortalHeader.tsx`
- `apps/web/components/portal/portal-header.module.css`
- `apps/web/components/Header.tsx`
- `apps/web/components/DiagnosisReport.tsx`
- `apps/web/components/CameraPanel.tsx`
- `apps/web/components/ChatInterface.tsx`
- `apps/web/components/ChatMessage.tsx`
- `apps/web/components/dentists/LocationPickerModal.tsx`
- `apps/web/components/dentists/DentistMapView.tsx`
- `apps/web/components/dentists/FindDentistsButton.tsx`
- `apps/web/components/portal/LoginPage.tsx`
- `apps/web/components/portal/RegisterPage.tsx`
- `apps/web/components/portal/PatientFeatureViews.tsx`
- `apps/web/components/portal/PortalSectionPage.tsx`
- `apps/web/components/portal/portal-auth.module.css`
- `apps/web/lib/location-autocomplete.ts`
- `apps/web/lib/geo-location.ts`
- `orchestrator/src/orchestrator/dentist_recommendation/routes_geocode.py`
- `orchestrator/src/orchestrator/dentist_recommendation/autocomplete_service.py`
- `orchestrator/src/orchestrator/dentist_recommendation/geocoding.py`
- `context.md`
- `docs/phase-log.md`

### Validation

- i18n Key Parity Test: 190 EN keys, 190 UR keys, 0 missing.
- Next.js Production Build (`npm run build`): Completed with code 0 (26/26 static routes generated).
- Backend Test Suite: 263 passed, 1 skipped in 30.13s.

### Next

Phase 10.1B — Localization, Copy, Address Language & Contrast Repair

---

## Phase 10.1B — Localization, Copy, Address Language & Contrast Repair

**Date:** September 2026  
**Status:** COMPLETE

### Summary

Repaired and normalized patient-facing localization, copy, address language formatting, and visual contrast:
- **Zero Raw i18n Key Leakage:** Centralized translation fallback logic in `LanguageProvider` / `useLanguage().t()`. Added case-insensitive safety lookup, developer-mode missing key warnings, and safe humanized fallbacks ensuring raw technical keys never leak into the patient UI.
- **Canonical Key Parity (257 Keys):** Synchronized `en.ts` and `ur.ts` with 100% key parity across all 257 keys, standardizing on canonical lowercase dot-notation (`scan.*`, `report.*`, `dashboard.*`, `location.*`, `dentists.*`, `auth.*`, `chat.*`, `common.*`, `finding.*`, `nav.*`, `scans.*`).
- **Standard Dental Terminology:** Established verified English copy and authentic, high-quality Urdu dental phrasing for all screening stages, findings, urgency tiers, and clinical guidance.
- **Address Language Normalization:** Updated Nominatim requests to send `addressdetails=1`, `namedetails=1`, and `accept-language={lang}`. Built `format_location_label` in Python orchestrator and `formatReverseGeocodeLabel` in TypeScript frontend to extract language-appropriate namedetails and structured address parts (`[Place, City, Region, Country]`) with smart multi-script deduplication, eliminating mixed Urdu/English administrative hierarchies in English mode.
- **Professional Healthcare Typography & Contrast:**
  - Light theme: Deep navy headings (`--text-heading: #0B315D`), high-contrast slate text (`--text-primary: #1E293B`, `--text-secondary: #475569`, `--text-muted: #64748B`).
  - Dark theme: Soft crisp light neutrals (`--text-heading: #F1F5F9`, `--text-primary: #F8FAFC`, `--text-secondary: #CBD5E1`), high-contrast dark surfaces (`--bg-surface`, `--bg-surface-raised`), eliminating low-contrast and washed-out text.
  - Removed decorative Anton font from body copy, buttons, and clinical text, reserving it only for major hero branding; restored readable system / Jakarta Sans font.
  - Replaced oversaturated neon cyan text in report recommendations, specialist, and timeframe with readable primary text and subtle accents.

### Files Modified

- `apps/web/i18n/context.tsx`
- `apps/web/i18n/en.ts`
- `apps/web/i18n/ur.ts`
- `apps/web/app/globals.css`
- `apps/web/components/portal/patient-feature.module.css`
- `apps/web/components/dentists/dentist-map.module.css`
- `apps/web/components/dentists/LocationPickerModal.tsx`
- `apps/web/components/dentists/DentistMapView.tsx`
- `apps/web/lib/geo-location.ts`
- `orchestrator/src/orchestrator/dentist_recommendation/autocomplete_service.py`
- `context.md`
- `docs/phase-log.md`

### Validation

- Dictionary Key Parity: 257 EN keys, 257 UR keys (100% parity, 0 missing).
- Component i18n Key Verification: 130 unique component `t()` calls matched directly into dictionaries with 0 missing keys.
- Next.js Production Build (`npm run build`): Exit code 0, 26/26 static routes generated successfully.
- Address Formatter Unit Validation: Verified concise structured output in English and Urdu with multi-script deduplication.

### Next

Phase 10.2 — Nearby Dentist Repair + Product Marketplace Integrity

---

## Phase 10.2 — Nearby Dentist Repair + Product Marketplace Integrity

**Date:** September 2026  
**Status:** COMPLETE

### Summary

Repaired nearby dentist discovery runtime execution and locked strict real-data integrity for the oral care product marketplace:
- **Nearby Dentist Discovery Repaired:**
  - Diagnosed Overpass API runtime rejection caused by default HTTP client headers (HTTP 406 Not Acceptable). Added compliant headers (`User-Agent: DaantShaant/1.0`, `Accept: application/json`).
  - Optimized Overpass queries to evaluate `node` and `way` elements, eliminating heavy `relation` evaluations that triggered HTTP 504 Gateway Timeouts on wide radiuses.
  - Implemented resilient fallback endpoint sequencing across Overpass mirror endpoints (`overpass-api.de`, `lz4.overpass-api.de`, `z.overpass-api.de`).
  - Resolved LangGraph execution crash (`AttributeError: module 'langchain' has no attribute 'debug'`) with an ambient safeguard across graph entrypoints.
  - Added compound specialist string normalization (`normalize_specialist_candidates`) and expanded clinical keyword mapping to cleanly split strings like `"general dentist / restorative dentist"` into distinct specialist tags.
  - Ensured registered platform database dentists are always preserved and returned as authoritative records if external discovery is unavailable, with zero technical provider names (`Overpass`, `OSM`, `HTTP 504`) exposed to the public UI.
- **Product Marketplace Integrity Locked (Zero AI-Fabricated Listings):**
  - Audited and eliminated hardcoded mock product objects (`mock-toothbrush`, `mock-toothpaste`) from `apps/web/components/DiagnosisReport.tsx`.
  - Removed synthetic fallback card generation from `apps/web/components/ChatMessage.tsx`.
  - Restricted product candidate retrieval to active database products listed by active registered dentists in PostgreSQL (`ProductRepository.list_active` joining `Dentist`).
  - Enforced strict database hydration: the LLM may only rank candidates and provide patient-specific clinical rationale; catalog data (`name`, `price`, `images`, `seller/dentist_id`, `category`) is strictly authoritative from PostgreSQL. Hallucinated or unknown product IDs are rejected.
  - Added bilingual empty state when no products exist in the catalog:
    - EN: `"No recommended products are currently available from registered dental providers."`
    - UR: `"رجسٹرڈ ڈینٹل فراہم کنندگان کی جانب سے فی الحال کوئی تجویز کردہ پروڈکٹس دستیاب نہیں ہیں۔"`
  - Commercial business model discussions deferred until explicitly requested by Nathan.

### Files Modified

- `orchestrator/src/orchestrator/__init__.py`
- `orchestrator/src/orchestrator/dentist_recommendation/osm_dentists.py`
- `orchestrator/src/orchestrator/dentist_recommendation/condition_mapping.py`
- `orchestrator/src/orchestrator/dentist_recommendation/ranking.py`
- `orchestrator/src/orchestrator/dentist_recommendation/platform_query.py`
- `orchestrator/src/orchestrator/dentist_recommendation/dentist_agent.py`
- `orchestrator/src/orchestrator/repositories/marketplace.py`
- `orchestrator/src/orchestrator/recommendation_ai_system/tools.py`
- `orchestrator/src/orchestrator/recommendation_ai_system/recommendation_agent.py`
- `apps/web/components/DiagnosisReport.tsx`
- `apps/web/components/ChatMessage.tsx`
- `apps/web/i18n/en.ts`
- `apps/web/i18n/ur.ts`
- `context.md`
- `docs/phase-log.md`

### Files Created

- `orchestrator/tests/test_product_marketplace_integrity.py`

### Validation

- Dentist & Product Automated Test Suites (`test_dentist_discovery.py` & `test_product_marketplace_integrity.py`): 28 passed, 0 failed. Zero external AI calls.
- Next.js Production Build (`npm run build`): Exit code 0, 26/26 static routes generated successfully.
- Safe Real Overpass Manual Query: Verified endpoint behavior with safe metadata logging only.

### Next

Phase 10.3 — Live Nearby Dentist Discovery Integration

---

## Phase 10.3 — Live Nearby Dentist Discovery Integration

**Date:** September 2026  
**Status:** COMPLETE

### Summary

Integrated live nearby-dentist discovery into the real DaantShaant patient flow using direct browser coordinates, adaptive search radius, resilient multi-source discovery, and clinical ranking:
- **Direct Current-Location Discovery**:
  - `navigator.geolocation` coordinates are passed directly from browser to the recommendation endpoint (`POST /portal/recommend/dentists/`), eliminating geocoding/reverse geocoding overhead on the discovery path.
  - Reverse geocoding is performed asynchronously purely for the user-facing location badge.
  - Location permission denial and timeouts produce friendly translated guidance without leaking raw browser errors.
- **Adaptive Locality Radius (`[3, 5, 8, 10]` km)**:
  - Searches nearest locality first (3 km) and only expands if fewer than target clinics are found (`MIN_RESULT_TARGET = 5`).
  - Stops immediately when sufficient clinics are located, preventing unnecessary wide-city searches.
  - Fallback is bounded at 10 km.
  - Safe developer diagnostics log center coordinates, attempts, provider counts, merged counts, target status, final radius, and elapsed duration.
- **Multi-Source External Discovery & Failure Isolation**:
  - Primary external discovery via OpenStreetMap / Overpass API with 30-minute in-memory caching.
  - Optional Foursquare (`FOURSQUARE_API_KEY`) and Geoapify (`GEOAPIFY_API_KEY`) adapters are safely queried when configured and skipped when unconfigured.
  - Provider errors are strictly isolated: if external providers fail or time out, registered platform database dentists are always preserved and returned.
- **Multi-Source Deduplication & Deterministic Ranking**:
  - Intelligent deduplication merges clinics across platform and external providers using proximity (<80m), name token overlap, phone numbers, and website domains.
  - Platform database records remain 100% authoritative for registered DaantShaant dentists.
  - Missing ratings are preserved as `None` (never converted to 0 stars).
  - General dental clinics lacking specific specialist metadata are preserved and ranked by distance.
- **MapLibre UX & Search Radius Circle**:
  - Map auto-fits local markers and patient position with sensible padding.
  - Visualizes adaptive search radius with a subtle GeoJSON circle and summary text (`"X dental clinics found within Y km"`).
  - External listings display direct contact info (Call, Directions, Website) with no fake booking; registered dentists retain "Book Consultation".
- **Product Section Microfix**:
  - In `DiagnosisReport.tsx`, when `recommendedProducts.length === 0`, the entire product recommendation block is hidden, continuing cleanly to the clinical safety disclaimer.

### Files Modified

- `apps/web/components/DiagnosisReport.tsx`
- `apps/web/components/dentists/DentistMapView.tsx`
- `apps/web/components/dentists/LocationPickerModal.tsx`
- `apps/web/i18n/en.ts`
- `apps/web/i18n/ur.ts`
- `apps/web/lib/dentist-recommend.ts`
- `docs/third-party-usage.md`
- `orchestrator/src/orchestrator/dentist_portal/models.py`
- `orchestrator/src/orchestrator/dentist_recommendation/dentist_agent.py`
- `orchestrator/src/orchestrator/dentist_recommendation/osm_dentists.py`
- `orchestrator/src/orchestrator/dentist_recommendation/ranking.py`
- `orchestrator/src/orchestrator/dentist_recommendation/routes.py`
- `context.md`
- `docs/phase-log.md`

### Files Created

- `orchestrator/src/orchestrator/dentist_recommendation/external_providers.py`
- `orchestrator/tests/test_phase10_3_dentist_discovery.py`

### Validation

- Dedicated Phase 10.3 Automated Test Suite (`test_phase10_3_dentist_discovery.py`): 10 passed, 0 failed.
- Combined Dentist Automated Test Suites (`test_dentist_discovery.py` + `test_phase10_3_dentist_discovery.py`): 30 passed, 0 failed. Zero external AI calls.
- Product Marketplace Test Suite (`test_product_marketplace_integrity.py`): 8 passed, 0 failed.
- Next.js Production Build (`npm run build`): Exit code 0, 26/26 static routes generated successfully.
- Live Karachi Coordinates Test (`24.905865, 67.030718`): Overpass live query returned real clinics (4 at 3km -> expanded adaptively to 5km -> 20 found -> target reached, final radius 5.0km, returned 15 ranked dentists).

### Next

Phase 11 — Deployment Fast Track.

---

## Phase 10.4 — Production Live Dentist Discovery + Map Integration

**Date:** September 2026  
**Status:** IMPLEMENTED — PENDING NATHAN MANUAL LIVE ACCEPTANCE

### Summary

Engineered the complete production live dentist discovery and MapLibre integration experience for DaantShaant:
- **Unified Location Flows**:
  - Preserved Nathan's decoupled LocationPickerModal where selecting an autocomplete suggestion stores `{label, lat, lng}` and enables the "Find Dentists" button without premature discovery.
  - "Use Current Location (GPS)" directly passes browser coordinates (`navigator.geolocation`) without redundant roundtrip geocoding.
- **Adaptive Locality Radius (`[3, 5, 8, 10]` km)**:
  - Searches 3 km first, expanding to 5, 8, or 10 km only when results are below target (`MIN_RESULT_TARGET = 5`), finding the nearest sufficient set rather than entire-city results.
- **Multi-Source Discovery & Platform Authority**:
  - Combines registered platform dentists (PostgreSQL) with OpenStreetMap Overpass live listings, plus optional Foursquare and Geoapify providers if configured.
  - Platform database records remain 100% authoritative.
  - Failures in any external provider are strictly isolated: registered dentists and working sources continue without returning 500/504 errors to the UI.
- **Statistical & Bayesian Ranking Engine**:
  - Deterministic multi-factor scoring: Clinical specialist match > Platform verification > Proximity > Bayesian rating > Multi-source consensus & profile completeness > Partner tiebreaker.
  - Bayesian weighted rating: `(v / (v + m)) * R + (m / (v + m)) * C` prevents low-review 5.0 clinics from dominating well-established 4.8 clinics. Missing ratings are preserved as `None` (never 0 stars).
  - Clinics without specific specialty tags are retained as "Nearby Dental Clinic" rather than filtered out.
- **MapLibre OpenFreeMap Integration & Card Interaction**:
  - Professional healthcare markers: Pulsing user location, verified platform clinics (#3b82f6), best specialist matches (#22c55e), external clinics (#64748b).
  - Interactive two-way card <-> marker focus and flyTo.
  - Strict CTA distinction: "Book Consultation" displayed only for registered platform dentists; external clinics provide direct Call, Directions (OSM routing), and Website links.
  - Preserved full English/Urdu bilingual localization and Light/Dark contrast themes.

### Files Modified

- `orchestrator/src/orchestrator/dentist_portal/models.py`
- `orchestrator/src/orchestrator/dentist_recommendation/ranking.py`
- `apps/web/components/dentists/DentistMapView.tsx`
- `apps/web/lib/dentist-recommend.ts`
- `context.md`
- `docs/phase-log.md`

### Files Created

- `orchestrator/tests/test_phase10_4_dentist_discovery.py`

### Validation

- Dedicated Phase 10.4 19-Scenario Test Suite (`test_phase10_4_dentist_discovery.py`): 19 passed, 0 failed.
- Combined Dentist Test Suite (`test_phase10_3_dentist_discovery.py`, `test_phase10_4_dentist_discovery.py`, `test_dentist_discovery.py`): 50 passed, 0 failed. Zero external live calls.
- Frontend Next.js Production Build (`npm run build`): Exit code 0, 26/26 static routes generated successfully.
- NO browser, live API keys, or manual localhost testing performed by agent.

### Next

Phase 10.4.1 — Stale / Missing / Unowned Scan ID Resilience.

---

## Phase 10.4.1 — Stale / Missing / Unowned Scan ID Resilience in Dentist Discovery

**Date:** September 2026  
**Status:** COMPLETE

### Summary

Dentist discovery now treats `scan_id` strictly as optional linking context rather than a blocking precondition:
- **Resilient Route Execution**: `POST /portal/recommend/dentists/` checks scan ownership in `ScanRepository` if `scan_id` is supplied. If the scan ID is missing from DB, unowned by the requesting patient, or malformed, the route logs a safe development warning, drops the scan context (`resolved_scan_id = None`), and continues dentist discovery without returning a 404 or 400.
- **Security Guarantee**: Unowned scan IDs are never treated as valid and never attached to recommendation session records in Supabase PostgreSQL (`DentistRecommendation`), preventing any leakage or unauthorized association of another user's clinical scan.
- **Frontend Hygiene**: `fetchDentistRecommendations` and `DentistMapView.tsx` sanitize `scan_id` to ensure empty strings, `"undefined"`, or `"null"` query param artifacts are omitted prior to making API calls.

### Files Modified

- `orchestrator/src/orchestrator/dentist_recommendation/routes.py`
- `apps/web/lib/dentist-recommend.ts`
- `apps/web/components/dentists/DentistMapView.tsx`
- `apps/web/components/dentists/FindDentistsButton.tsx`
- `context.md`
- `docs/phase-log.md`

### Files Created

- `orchestrator/tests/test_phase10_4_1_scan_id_resilience.py`

### Validation

- Dedicated Phase 10.4.1 Test Suite (`test_phase10_4_1_scan_id_resilience.py`): 7 passed, 0 failed.
- Combined Dentist Test Suites (`test_phase10_4_1_scan_id_resilience.py`, `test_phase10_4_dentist_discovery.py`): 26 passed, 0 failed. Zero external live calls.
- Frontend TypeScript check (`npx tsc --noEmit`): Exit code 0, 0 errors.
- NO browser, live API keys, or manual localhost testing performed by agent.

### Next

Phase 10.4.2 — Map Visibility, Brand Styling, Full-Viewport Modals & Contact Details.

---

## Phase 10.4.2 — Map Visibility, Brand Styling, Full-Viewport Modals & Contact Details

**Date:** September 2026  
**Status:** COMPLETE

### Summary

Fixed map tile visibility, aligned branding colors with DaantShaant identity, ensured full-viewport coverage for modals, and integrated optional contact/directions links:
- **Map Tile Rendering & Canvas Sizing**: Bundled `maplibre-gl/dist/maplibre-gl.css` statically, eliminated container unmounting during search queries by maintaining the map DOM node and displaying an overlay loader, and added `ResizeObserver` plus post-render `map.resize()` invocations to guarantee WebGL tile layers always compute viewport dimensions correctly.
- **Brand Colors & Registered Dentist Flair**: Standardized brand blue `#00A2F0` exclusively for registered dentists (blue pin with inner crest, blue left card highlight `.listItemPlatform`, `#00A2F0` badge `.badgePartner`, and booking CTA). External clinics use neutral slate styling (`#64748b` pin and subtle neutral badge). All incorrect green highlights (`#22c55e`, `#059669`) removed across cards, badges, and pins. The patient location marker is styled with a distinct warm amber pulsing pin (`#f59e0b`), avoiding brand confusion.
- **Full-Viewport Modal Overlays**: Fixed dark backdrop clipping by rendering the dentist detail modal into `document.body` via React's `createPortal`, matching `LocationPickerModal` with fixed viewport dimensions (`inset: 0`, `width: 100vw`, `height: 100vh`, `z-index: 99999`).
- **Optional Contact & Social Details**: Extended backend models (`DentistPin`) and candidate extraction in `platform_query.py`, `osm_dentists.py`, `external_providers.py`, and `ranking.py` to extract `phone`, `email`, `website`, `whatsapp`, and `linkedin`. The frontend renders only populated contact fields as safe clickable links (`tel:`, `mailto:`, `https://wa.me/...`, LinkedIn, website in new tabs) and omits unavailable fields without "N/A" placeholders.
- **Google Maps Directions**: Replaced OSM directions link with Google Maps directions URL (`https://www.google.com/maps/dir/?api=1&origin={lat},{lng}&destination={lat},{lng}`) opening in a new tab.

### Files Modified

- `apps/web/lib/maplibre.ts`
- `apps/web/components/dentists/DentistMapView.tsx`
- `apps/web/components/dentists/dentist-map.module.css`
- `apps/web/components/dentists/location-picker.module.css`
- `apps/web/lib/dentist-recommend.ts`
- `orchestrator/src/orchestrator/dentist_portal/models.py`
- `orchestrator/src/orchestrator/dentist_recommendation/platform_query.py`
- `orchestrator/src/orchestrator/dentist_recommendation/osm_dentists.py`
- `orchestrator/src/orchestrator/dentist_recommendation/external_providers.py`
- `orchestrator/src/orchestrator/dentist_recommendation/ranking.py`
- `context.md`
- `docs/phase-log.md`

### Validation

- Orchestrator Pytest Suite (`test_phase10_4_1_scan_id_resilience.py`, `test_phase10_4_dentist_discovery.py`): 26 passed, 0 failed.
- Frontend TypeScript check (`npx tsc --noEmit`): Exit code 0, 0 errors.
- Frontend Next.js Production Build (`npm run build`): Exit code 0, 26/26 routes successfully generated.
- Strict adherence to rule: NO browser, localhost, or live automated testing performed by agent.

### Next

Phase 10.4.3 — Final Map Baselayer Repair + Dentist Listing UI Simplification.

---

## Phase 10.4.3 — Final Map Baselayer Repair + Dentist Listing UI Simplification

**Date:** September 2026  
**Status:** IMPLEMENTED — PENDING NATHAN MANUAL LIVE ACCEPTANCE

### Summary

Surgically repaired map background tile rendering by switching from external vector style loading to an explicit raster style specification with OpenStreetMap tiles, and simplified the patient-facing dentist discovery interface:
- **Explicit OSM Raster Baselayer**: Replaced the external `OPENFREEMAP_LIBERTY_STYLE` JSON URL with an in-memory `OSM_RASTER_STYLE` object (`maplibregl.StyleSpecification`) referencing standard OpenStreetMap raster tiles (`https://tile.openstreetmap.org/{z}/{x}/{y}.png`). Road networks, building footprints, and labels render immediately without CORS issues or vector style fetch delays.
- **Truthful Attribution & Safe Fallback**: Streamlined attribution to `© OpenStreetMap contributors` with standard copyright link; eliminated outdated OpenFreeMap/OpenMapTiles strings. Added a friendly fallback message (`dentists.map_unavailable`) if MapLibre fails, preventing raw technical errors or silent beige canvases.
- **Registered Dentist Brand Rules**: Reserved `#00A2F0` exclusively for registered platform dentists (`d.tier === 'platform' || d.dentist_id != null`). Cards feature `border-left: 4px solid #00A2F0`, markers are styled in `#00A2F0` with inner pin flair, and the listing displays a single authoritative badge: `DaantShaant Recommended` (`background: #00A2F0; color: #ffffff`).
- **Normal Dentist UI Neutrality**: Non-registered nearby dentists appear cleanly with neutral card styling, slate markers (`#64748B`), and no algorithmic or source badges. Removed "External Clinic Listing", "Best Specialist Match", "Verified Dental Clinic", and "Nearby Dental Clinic" badges from public listing cards, modal, and legend.
- **Simplified Minimal Legend**: Streamlined the map legend to three clear items: 🟠 Your Location, 🔵 DaantShaant Recommended, ⚫ Nearby Dentists.
- **Detail Modal Cleanup**: Removed the "External Clinic Listing" footer note. Preserved direct contact links (Phone, Email, Website, WhatsApp, LinkedIn) and Google Maps directions for all dentists; registered dentists feature the "DaantShaant Recommended" badge and "Book Consultation" CTA.
- **Parity & Themes**: Kept 100% bilingual translation key parity across `en.ts` and `ur.ts` with no missing keys or raw tokens; verified light and dark mode styling with zero green color remnants.

### Files Modified

- `apps/web/lib/maplibre.ts`
- `apps/web/components/dentists/DentistMapView.tsx`
- `apps/web/components/dentists/dentist-map.module.css`
- `apps/web/i18n/en.ts`
- `apps/web/i18n/ur.ts`
- `context.md`
- `docs/phase-log.md`

### Validation

- Frontend TypeScript check (`npx tsc --noEmit`): Exit code 0, 0 errors.
- Frontend Next.js Production Build (`npm run build`): Exit code 0, 26/26 static routes generated successfully.
- Orchestrator Pytest Suite (`test_phase10_4_1_scan_id_resilience.py`, `test_phase10_4_dentist_discovery.py`): 26 passed, 0 failed.
- Strict compliance: NO browser, dev server, localhost, or live automated testing performed by agent.

### Next

Phase 10.5 — Portal Security + Brand Consistency + Dentist Operations.

---

## Phase 10.5 — Portal Security + Brand Consistency + Dentist Operations

**Date:** September 2026  
**Status:** IMPLEMENTED — PENDING NATHAN MANUAL ACCEPTANCE

### Summary

Addressed security, brand consistency, session resilience, and dentist operational features across both the frontend and backend:
- **Generic Role-Safe Login Authentication**: Fixed login account-role information disclosure and email enumeration. Both patient and dentist login endpoints now return generic 401 `{"detail": "Invalid email or password"}` on any failure (unknown email, incorrect password, inactive account, or cross-portal role mismatch). Frontend displays generic translated `auth.invalid_credentials` error in English and Urdu.
- **Extended Session Lifetimes & Concurrency Fix**: Set access token expiration to 30 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES=30`). Maintained 7-day rotating refresh tokens in HttpOnly cookies. Resolved concurrent frontend refresh race conditions by deduplicating refresh calls with a promise queue in `apps/web/lib/portal-auth.ts`.
- **Global Modal Portal & Full-Viewport Backdrops**: Introduced `ModalPortal` (`createPortal(..., document.body)`). Wrapped patient `CheckoutModal` and dentist `ProductsManager` modals. Overlays use fixed viewport bounds (`100vw`/`100vh`, `inset: 0`, `z-index: 99999`) preventing parent container clipping.
- **Canonical DaantShaant Logo**: Built `<DaantShaantLogo />` reusing `/landing/logo.png`. Applied across public header, patient header, dentist auth shell, and dentist portal header. Clicking logo in public/dentist auth routes to landing `/`; in authenticated portal routes to dashboard.
- **Dentist Auth & Onboarding Back Navigation**: Added top-left "Back" arrow on dentist login and registration pages linking to `/get-started`. Added top-left "Back" arrow on `/get-started` linking to `/`.
- **Dentist Brand Color Normalization**: Normalized dentist auth, onboarding, and portal controls from mismatched purple and navy (`#073564`) to DaantShaant brand blue `#00A2F0`. Patient product card CTA normalized to `#00A2F0` without altering clinical recommendation logic.
- **Dentist Real Seller-Scoped Orders**: Built `GET /portal/products/orders` in `routes_products.py` resolving authenticated dentist ID from token. Dentists see only orders containing products they uploaded. Replaced "Coming soon" on `/dentist/orders` with `OrdersManager` table with bilingual empty states.
- **Dentist Appointment Management**: Added "Appointments" nav item to dentist portal header (`/dentist/appointments`). Created `POST /recommend/dentists/appointments/{id}/status` allowing status mutations (`confirmed`, `completed`, `cancelled`) with strict dentist ownership verification (cross-dentist 404 denial). Built `AppointmentsManager` displaying appointments, patient contact details, and status actions.

### Files Modified

- `apps/web/components/common/ModalPortal.tsx` [NEW]
- `apps/web/components/common/DaantShaantLogo.tsx` [NEW]
- `apps/web/components/Header.tsx`
- `apps/web/components/portal/PortalHeader.tsx`
- `apps/web/components/portal/PortalAuthShell.tsx`
- `apps/web/components/portal/LoginPage.tsx`
- `apps/web/components/portal/portal-auth.module.css`
- `apps/web/components/portal/portal-header.module.css`
- `apps/web/components/get-started/RoleSelection.tsx`
- `apps/web/components/get-started/role-selection.module.css`
- `apps/web/components/dentist/ProductsManager.tsx`
- `apps/web/components/dentist/products-manager.module.css`
- `apps/web/components/dentist/OrdersManager.tsx` [NEW]
- `apps/web/components/dentist/orders-manager.module.css` [NEW]
- `apps/web/components/dentist/AppointmentsManager.tsx` [NEW]
- `apps/web/app/dentist/orders/page.tsx`
- `apps/web/app/dentist/appointments/page.tsx` [NEW]
- `apps/web/components/CheckoutModal.tsx`
- `apps/web/app/globals.css`
- `apps/web/i18n/en.ts`
- `apps/web/i18n/ur.ts`
- `apps/web/lib/portal-auth.ts`
- `.env` & `.env.example`
- `orchestrator/src/orchestrator/config.py`
- `orchestrator/src/orchestrator/dentist_portal/user_service.py`
- `orchestrator/src/orchestrator/dentist_portal/routes_products.py`
- `orchestrator/src/orchestrator/dentist_recommendation/routes.py`
- `orchestrator/tests/test_phase10_5_portal_security_and_ops.py` [NEW]
- `context.md`
- `docs/phase-log.md`

### Validation

- Frontend TypeScript check (`npx tsc --noEmit`): Exit code 0, 0 errors.
- Frontend Next.js Production Build (`npm run build`): Exit code 0, 27/27 static routes generated successfully.
- Orchestrator Pytest Suite (`test_phase10_5_portal_security_and_ops.py`): 12 passed, 0 failed.
- Strict compliance: NO browser, dev server, localhost, or live automated testing performed by agent.

### Next

Phase 11 — Deployment Fast Track.







