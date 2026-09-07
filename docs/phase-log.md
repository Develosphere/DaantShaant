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

Phase 10.6 — Patient Order History, Dashboard Redesign, Navigation UX, and Full Urdu Localization.

---

## Phase 10.6 — Patient Order History, Dashboard Redesign, Navigation UX & Full Urdu Localization

**Date:** September 2026  
**Status:** IMPLEMENTED — PENDING NATHAN MANUAL ACCEPTANCE

### Summary

Delivered comprehensive UX polish, patient order tracking, dashboard usefulness, clean logo branding, full Urdu localization, and consistent `#00A2F0` styling across DaantShaant:
- **Phase A — Patient Order History**:
  - Implemented `OrderRepository.list_for_patient(patient_user_id)` querying PostgreSQL orders joined with seller dentist details.
  - Added `GET /portal/products/patient/orders` in `routes_products.py` returning seller clinic name, product details, quantity, price, simple status (`placed`, `confirmed`, `processing`, `completed`), and ISO timestamps.
  - Enhanced `buy_product` to accept optional payload with patient details and quantity, defaulting to `status="placed"`.
  - Built `PatientOrdersView` (`apps/web/components/patient/PatientOrdersView.tsx`) with orders KPI summary, order table, status badges, responsive card layouts, and synchronized client cache for immediate reflection.
  - Created `/patient/orders` page and added "Orders" item to patient navigation header.
- **Phase B — Dashboard Redesign (Patient + Dentist)**:
  - Redesigned Patient Dashboard (`PatientDashboardView.tsx`) in modern healthcare SaaS style with: welcome hero, wellness status badge, 4 quick action cards (`New Scan`, `Chat with AI`, `Find Dentists`, `Orders`), recent scan summary card, recommended oral hygiene products preview with 1-click checkout, and daily prevention guidance banner.
  - Redesigned Dentist Dashboard (`DentistDashboardHome.tsx`) with: verified partner greeting hero, 4 KPI stats cards (`Listed Products`, `Consultations`, `Pending Orders`, `Total Sales`), 3 quick action cards (`Add Product`, `View Orders`, `Appointments`), recent orders preview table, upcoming appointments preview, and clinical intake banner.
  - Removed extra header subtitles like "Oral Health Screening" and "Dentist Management Portal" from `PortalHeader` and `Header`, keeping only the well-proportioned `DaantShaantLogo`.
  - Normalized icon accents and interactive styling to DaantShaant brand blue `#00A2F0`.
- **Phase C — Onboarding / Nav UX Fixes**:
  - Fixed role cards hover interaction on `/get-started` (`RoleSelection`): set `pointer-events: none` on `.card::before` pseudo-element and `z-index: 5` on `.cardActions` / buttons so cards and buttons are effortlessly clickable.
  - Added visible "Back" link on patient onboarding/login/register pages in `PortalAuthShell` routing to `/get-started`.
  - Added language toggle (`EN | اردو`) and theme toggle (`☀️ | 🌙`) to `/get-started` navbar.
- **Phase D — Full Urdu Localization Coverage**:
  - Added 50+ new translation keys to `apps/web/i18n/en.ts` and `apps/web/i18n/ur.ts` with 100% key parity (364 keys each).
  - Wired `useLanguage()` across `RoleSelection`, `PortalAuthShell`, `CheckoutModal`, `ProductsManager`, `OrdersManager`, `AppointmentsManager`, `PatientOrdersView`, `PatientDashboardView`, and `DentistDashboardHome`.
  - Maintained RTL-friendly layouts and English fallback.
- **Phase E — Design / Brand Consistency**:
  - Set `--primary-brand: #00A2F0` and standardized `--accent: #00A2F0` in light and dark mode in `globals.css`.
  - Preserved full-viewport modal overlays (`ModalPortal` with `100vw`/`100vh`).

### Files Created

- `apps/web/components/patient/patient-orders.module.css`
- `apps/web/components/patient/PatientOrdersView.tsx`
- `apps/web/app/patient/orders/page.tsx`
- `apps/web/components/patient/patient-dashboard.module.css`
- `apps/web/components/patient/PatientDashboardView.tsx`
- `apps/web/components/dentist/dentist-dashboard.module.css`
- `apps/web/components/dentist/DentistDashboardHome.tsx`

### Files Modified

- `orchestrator/src/orchestrator/repositories/marketplace.py`
- `orchestrator/src/orchestrator/dentist_portal/routes_products.py`
- `orchestrator/tests/test_phase10_5_portal_security_and_ops.py`
- `apps/web/components/portal/PortalHeader.tsx`
- `apps/web/components/portal/PortalAuthShell.tsx`
- `apps/web/components/portal/portal-auth.module.css`
- `apps/web/components/Header.tsx`
- `apps/web/components/CheckoutModal.tsx`
- `apps/web/components/get-started/RoleSelection.tsx`
- `apps/web/components/get-started/role-selection.module.css`
- `apps/web/components/dentist/ProductsManager.tsx`
- `apps/web/components/dentist/OrdersManager.tsx`
- `apps/web/components/dentist/AppointmentsManager.tsx`
- `apps/web/app/patient/dashboard/page.tsx`
- `apps/web/app/dentist/dashboard/page.tsx`
- `apps/web/app/globals.css`
- `apps/web/i18n/en.ts`
- `apps/web/i18n/ur.ts`
- `context.md`
- `docs/phase-log.md`

### Validation

- Orchestrator Pytest Suite (`test_phase10_5_portal_security_and_ops.py`): 14 passed, 0 failed.
- Frontend Next.js Production Build (`npm run build`): Exit code 0, 28/28 static routes generated successfully with 0 errors.
- Strict compliance: NO browser, dev server, localhost, or live automated testing performed by agent.

### Next

Phase 10.6 — Final Design Cleanup + Cross-Tab Session Hardening.

---

## Phase 10.6 — Final Design Cleanup + Cross-Tab Session Hardening

**Date:** September 2026  
**Status:** IMPLEMENTED — PENDING NATHAN MANUAL ACCEPTANCE

### Summary

Hardened auth refresh coordination across browser tabs to eliminate race conditions with rotating refresh tokens, locked header chrome LTR for Urdu localization, improved dark mode logo readability, polished `/get-started`, standardized `#00A2F0` monotone vector icons, and completed Urdu localization:
- **Cross-Tab Refresh Coordination & Mutex Lock**:
  - Created `apps/web/lib/cross-tab-auth.ts` introducing `withCrossTabLock` using `navigator.locks` with an atomic, timestamped `localStorage` fallback and 8-second stale lock expiration.
  - Solved single-use refresh token rotation race across tabs: when concurrent requests receive 401, only ONE tab acquires the mutex and calls `POST /portal/auth/refresh`. Other tabs wait on the mutex and send the rotated cookie sequentially, preventing token collisions and premature logout.
  - Integrated BroadcastChannel (`"daantshaant-auth"`) broadcasting `REFRESH_STARTED`, `REFRESH_SUCCEEDED`, `REFRESH_FAILED`, and `LOGGED_OUT` events without leaking sensitive access/refresh tokens.
  - Differentiated error types in `portal-auth.ts`: 401 clears session and broadcasts failure; 5xx and network errors preserve session state.
  - Tab-safe logout: explicit logout in any tab notifies all active portal tabs via `LOGGED_OUT` to clear their local in-memory session and redirect to login.
- **Header Structure & RTL Locking**:
  - Locked all header chrome (`PortalHeader`, public `Header`, `RoleSelection`) to `direction: ltr !important;` so switching to Urdu (`dir="rtl"`) never mirrors header layout. Logo stays left, nav stays center/left, language/theme/user controls stay right.
- **Logo Dark Mode Visibility**:
  - Enhanced `DaantShaantLogo` with `.ds-logo-chip` in `globals.css`: renders a subtle light surface chip in dark mode (`rgba(255, 255, 255, 0.94)`) with smooth border-radius and shadow, ensuring canonical `logo.png` text is crisp and legible without inverting colors or modifying the source asset.
- **Get-Started UI Polish**:
  - Removed highlighted top-left `← Back` link from `/get-started` header while preserving clickable home logo.
  - Polished dark mode surfaces in `role-selection.module.css` with dark slate surfaces and high contrast.
- **Dashboard Icon Consistency (#00A2F0)**:
  - Replaced visual emojis (`📸`, `💬`, `🗺️`, `📦`, `⚡`, `🛍️`, `📅`, `💳`, `➕`, `📋`, `✨`) used as UI action icons in Patient Dashboard (`PatientDashboardView.tsx`) and Dentist Dashboard (`DentistDashboardHome.tsx`) with monotone vector SVGs colored `#00A2F0`.
  - Added full dark mode token styling across patient and dentist dashboards and orders views.
- **Urdu Localization Final Pass**:
  - Added new translation keys for verified partner status, updated scan actions, and screening disclaimers with 100% key parity across `en.ts` and `ur.ts`.

### Files Created

- `apps/web/lib/cross-tab-auth.ts`
- `apps/web/lib/__tests__/cross-tab-auth.test.ts`

### Files Modified

- `apps/web/lib/portal-auth.ts`
- `apps/web/components/portal/PortalDashboard.tsx`
- `apps/web/components/portal/portal-header.module.css`
- `apps/web/components/common/DaantShaantLogo.tsx`
- `apps/web/components/get-started/RoleSelection.tsx`
- `apps/web/components/get-started/role-selection.module.css`
- `apps/web/components/patient/PatientDashboardView.tsx`
- `apps/web/components/patient/patient-dashboard.module.css`
- `apps/web/components/patient/patient-orders.module.css`
- `apps/web/components/dentist/DentistDashboardHome.tsx`
- `apps/web/components/dentist/dentist-dashboard.module.css`
- `apps/web/components/CheckoutModal.tsx`
- `apps/web/app/globals.css`
- `apps/web/i18n/en.ts`
- `apps/web/i18n/ur.ts`
- `context.md`
- `docs/phase-log.md`

### Validation

- Unit Test Suite (`cross-tab-auth.test.ts`): 7 passed, 0 failed across all cross-tab concurrency, broadcast, and fallback scenarios.
- Backend Pytest Suite: 20 passed, 0 failed.
- TypeScript Type Check (`npx tsc --noEmit`): Exit code 0, 0 errors.
- Next.js Production Build (`npm run build`): Exit code 0, 28/28 static routes generated successfully.
- Strict compliance: NO browser, dev server, localhost, or live testing performed by agent.

### Next

Phase 10.7 — Real Data-Driven Patient + Dentist Dashboards.

---

## Phase 10.7 - Real Data-Driven Patient + Dentist Dashboards

**Date:** September 2026

**Status:** IMPLEMENTED — PENDING NATHAN MANUAL ACCEPTANCE

### Summary

Replaced hardcoded and placeholder values in Patient and Dentist dashboards with real, authenticated, server-scoped database data without altering the visual layouts. Built lightweight aggregate dashboard endpoints (`GET /portal/patient/dashboard` and `GET /portal/dentist/dashboard`) derived strictly from authenticated user credentials. Replaced hardcoded "Good Standing" with deterministic triage-derived status ("No Screening Yet", "Routine Oral Care", "Dental Visit Recommended", "Prompt Dental Care", "Urgent Professional Care"). Scoped all scans, orders, products, and appointments strictly to their respective patient or dentist owner. Added neutral skeletons during loading and clean error states with retry.

### Files Created

- `orchestrator/src/orchestrator/dentist_portal/routes_dashboard.py` (aggregate patient and dentist dashboard endpoints)
- `orchestrator/tests/test_phase10_7_dashboards.py` (comprehensive 12-test suite covering all patient and dentist dashboard scenarios)
- `apps/web/lib/dashboard-api.ts` (typed client fetch helpers for patient and dentist dashboards)

### Files Modified

- `orchestrator/src/orchestrator/main.py` (registered `portal_dashboard_router`)
- `orchestrator/src/orchestrator/repositories/clinical.py` (added `count_scans`, `get_latest_screening`, and triage metadata enrichment in `add_result`)
- `orchestrator/src/orchestrator/repositories/marketplace.py` (added `count_owned` to `ProductRepository`, `count_for_patient` and `count_for_dentist` to `OrderRepository`, and `count_for_principal` to `AppointmentRepository`)
- `apps/web/components/patient/PatientDashboardView.tsx` (wired real aggregate stats, triage status badge, latest screening summary, real recommended products, recent orders preview, and recent activity)
- `apps/web/components/patient/patient-dashboard.module.css` (added pulse skeletons, preview items, and dark mode tokens)
- `apps/web/components/dentist/DentistDashboardHome.tsx` (wired real aggregate stats for products, consultations, pending orders, completed orders, recent orders preview, and upcoming appointments)
- `apps/web/components/dentist/dentist-dashboard.module.css` (added pulse skeletons, error notice, and retry button)
- `apps/web/i18n/en.ts` (added oral status strings, error loading, retry, and dashboard titles)
- `apps/web/i18n/ur.ts` (added 100% key parity Urdu translations for all new dashboard strings)
- `context.md`
- `docs/phase-log.md`

### Validation

- Backend Pytest Suite: 26 passed, 0 failed across `test_phase10_5_portal_security_and_ops.py` and `test_phase10_7_dashboards.py`.
- TypeScript Type Check (`npx tsc --noEmit`): Exit code 0, 0 errors.
- Next.js Production Build (`npm run build`): Exit code 0, 28/28 static and dynamic routes compiled successfully.
- Strict compliance: NO browser, dev server, localhost, or live testing performed by agent.
### Next

Phase 11A — Specialized YOLO Dental Pathology Perception Pipeline.

---

## Phase 11A — Specialized YOLO Dental Pathology Perception Pipeline

**Date:** September 2026

**Status:** IMPLEMENTED — PENDING NATHAN MANUAL ACCEPTANCE

### Summary

Replaced Qwen multimodal vision as the normal visual pathology detector with local Ultralytics YOLO11n oral disease perception (`teeth_analyzer/yolo_detector.py`), confidence filtering (`threshold >= 0.50`), spatial aggregation (localized, multiple, generalized), deterministic clinical triage (`diagnosis/triage.py`), and text-only Qwen patient report generation (`orchestrator/clinical/report_generator.py`).

### Key Decisions & Architecture

- **Visual Perception**: Local YOLO11n model trained offline on Modal (Roboflow Universe oral-disease dataset, 10,698 images, CC BY 4.0).
- **Locked Class Map**:
  - `calculus` -> `tartar`
  - `caries` -> `cavity_suspect`
  - `gingivitis` -> `gingivitis_signs`
  - `tooth discoloration` -> `discoloration`
  - `ulcer` -> `oral_ulcer`
- **Calculus vs Discoloration Safety**: Tooth discoloration is never converted to calculus/tartar. Spatial aggregation recognizes generalized discoloration across the dentition to prevent yellow teeth from being reported as tartar buildup. If both conditions are detected, both are preserved separately.
- **Oral Ulcer Addition**: Added `oral_ulcer` finding and `ConditionLabel.ORAL_ULCER` with cautious non-definitive wording ("Visible oral ulcer / sore") and routine follow-up recommendation if persistent beyond 10-14 days. Does not imply cancer or systemic disease.
- **Detector Failure & No-Finding Safety**: If model weights are missing or inference crashes, raises a typed pipeline error (`VisionBackendError`) — never fabricates healthy findings or silently claims "no concerns". Clean scans with 0 detections return non-definitive screening statement: "No supported visible pathology was detected by this screening model."
- **Qwen Text-Only Role**: Qwen receives NO raw images. Receives pre-validated structured evidence (findings, deterministic triage, limitations) via AIGateway with strict guardrails preventing finding mutation, urgency escalation, or etiology hallucinations (no fluorosis, amelogenesis imperfecta, or oral cancer).
- **Weight Location**: Configured to `services/teeth_analyzer/models/oral_disease/best.pt` via `YOLO_DENTAL_MODEL_PATH` (gitignored).

### Files Created

- `services/teeth_analyzer/src/teeth_analyzer/yolo_detector.py`
- `orchestrator/src/orchestrator/clinical/report_generator.py`
- `services/teeth_analyzer/tests/test_yolo_pipeline.py`

### Files Modified

- `packages/dantshaant_common/src/dantshaant_common/schemas.py` (added `distribution` & `detection_count` to `VisualFinding`; added `ConditionLabel.ORAL_ULCER`)
- `services/teeth_analyzer/pyproject.toml` (added `ultralytics>=8.0.0`)
- `services/teeth_analyzer/src/teeth_analyzer/config.py` (added YOLO configuration settings, default provider="yolo")
- `services/teeth_analyzer/src/teeth_analyzer/inference.py` (wired YOLO detection with failure safety & legacy fallback)
- `services/diagnosis/src/diagnosis/triage.py` (added oral ulcer rule, discoloration limitation & safety phrasing)
- `services/diagnosis/src/diagnosis/classifier.py` (added threshold for `ConditionLabel.ORAL_ULCER`)
- `orchestrator/src/orchestrator/clinical/graph.py` (integrated `report_node` text generation)
- `orchestrator/src/orchestrator/repositories/clinical.py` (persisted report text into `ClinicalReport`)
- `orchestrator/src/orchestrator/evaluation/metrics.py` (added `compute_yolo_evaluation_metrics`)
- `apps/web/i18n/en.ts` & `apps/web/i18n/ur.ts` (added finding keys for oral ulcer and generalized discoloration)
- `apps/web/components/DiagnosisReport.tsx` (added ulcer icon)
- `docs/third-party-usage.md`
- `docs/architecture.md`
- `context.md`

### Validation

- Unit Test Suite (`test_yolo_pipeline.py`): 16 passed, 0 failed covering all 16 required test conditions.
- Triage Test Suite (`test_triage.py`): 27 passed, 0 failed.
- Legacy Clinical Vision Test Suite (`test_clinical_vision.py`): 19 passed, 0 failed.
- Total Backend Python Tests: 62 passed, 0 failed.
- Next.js Production Build (`npm run build`): Exit code 0, 28/28 static & dynamic routes compiled.
- Strict compliance: NO browser, dev server, localhost, live image inference, or weight downloads performed by agent.

### Next

Nathan to provide `best.pt` locally and perform manual smoke-test acceptance.

---

## Phase 11B-1 — YOLO Detector Calibration + Hard-Negative Preparation

**Date:** September 2026

**Status:** IMPLEMENTED — CALIBRATION/HARD-NEGATIVE TOOLING READY, PENDING NATHAN DATA REVIEW AND V2 TRAINING

### Summary

Addressed false positive over-detection on clean treated teeth by auditing the dataset, building class-specific confidence threshold configuration and centralized resolver, creating offline calibration evaluation and model comparison tooling, establishing the hard-negative dataset infrastructure with deterministic splitting, and fixing the conceptual bug conflating detector confidence with visual image clarity.

### Key Deliverables & Architecture

- **Dataset Audit (`scripts/audit_yolo_dataset.py`)**:
  - Audited all 10,698 images across train (8,558), valid (1,070), test (1,070).
  - Confirmed exactly 570 true negative (empty `.txt` label) images exist (5.33% of dataset).
  - 94.7% of images contain disease annotations (18:1 imbalance).
  - Tooth discoloration constitutes 26,424 boxes (42.1% of all boxes), heavily biasing background priors.
  - Results published to `docs/evaluation/yolo_dataset_audit.md`.
- **Class-Specific Threshold Configuration**:
  - Global fallback: `YOLO_DENTAL_CONFIDENCE_THRESHOLD=0.50`.
  - Class-specific overrides: `YOLO_CALCULUS_CONFIDENCE_THRESHOLD`, `YOLO_CARIES_CONFIDENCE_THRESHOLD`, `YOLO_GINGIVITIS_CONFIDENCE_THRESHOLD`, `YOLO_DISCOLORATION_CONFIDENCE_THRESHOLD`, `YOLO_ULCER_CONFIDENCE_THRESHOLD`.
  - Centralized resolver: `get_confidence_threshold(class_name)` accepts both raw YOLO labels and normalized clinical codes.
  - Predict layer queries minimum active threshold, and detection loop enforces per-class thresholds.
- **Diagnostic Spatial Metadata**:
  - Extended `AggregatedFinding` with internal metrics: `max_confidence`, `mean_confidence`, `horizontal_coverage`, `aggregate_area_ratio`, `image_third_coverage`.
  - Kept internal for evaluation; not leaked into patient UI.
- **Image Quality vs Detector Confidence Separation**:
  - Fixed bug where moderate detector confidence was presented as "Low visual clarity".
  - Mechanical image quality messages derive ONLY from `overall_quality_score < 0.5` or `action_trigger == "REQUEST_CLEARER_PHOTO"`.
  - Moderate detector confidence displays honest message: "Moderate screening confidence — professional confirmation is recommended."
- **Hard-Negative Infrastructure & Preparation Utility (`scripts/prepare_yolo_v2_dataset.py`)**:
  - Supports `dataset/hard-negatives/images/` and `labels/`.
  - Generates `dataset/oral-disease-v2.yolov11/` without mutating original dataset.
  - Deterministically partitions hard negatives into 80% train, 10% valid, 10% test using fixed seed (42).
  - Every hard negative receives a verified 0-byte `.txt` label (never manufactures false boxes).
- **Offline Evaluation & Comparison Tooling**:
  - `scripts/evaluate_yolo_calibration.py`: Sweeps confidence thresholds (0.30–0.80) to calculate Precision, Recall, F1, and cross-class confusion.
  - `scripts/compare_yolo_models.py`: Side-by-side comparison harness for `best.pt` vs `best_v2.pt`.
- **Documentation**:
  - `docs/evaluation/yolo_manual_acceptance.md`: 10 standardized clinical test categories (A–J) for Nathan's manual testing.
  - `docs/evaluation/yolo_hard_negatives_guide.md`: Detailed collection guide and Modal v2 fine-tuning commands.

### Files Created

- `scripts/audit_yolo_dataset.py`
- `scripts/evaluate_yolo_calibration.py`
- `scripts/prepare_yolo_v2_dataset.py`
- `scripts/compare_yolo_models.py`
- `docs/evaluation/yolo_dataset_audit.md`
- `docs/evaluation/yolo_manual_acceptance.md`
- `docs/evaluation/yolo_hard_negatives_guide.md`
- `services/teeth_analyzer/tests/test_calibration_and_negatives.py`

### Files Modified

- `services/teeth_analyzer/src/teeth_analyzer/config.py` (added class-specific threshold fields & `get_confidence_threshold` resolver)
- `services/teeth_analyzer/src/teeth_analyzer/yolo_detector.py` (added diagnostic metadata & per-class thresholding)
- `services/diagnosis/src/diagnosis/classifier.py` (fixed `BELOW_THRESHOLD_LIMITATION` wording)
- `apps/web/i18n/en.ts` & `apps/web/i18n/ur.ts` (added `report.moderate_confidence_alert`)
- `apps/web/components/DiagnosisReport.tsx` (separated image quality alert from moderate confidence alert)
- `docs/evaluation.md`
- `context.md`
- `docs/phase-log.md`

### Validation

- Unit Tests: 89 passed, 0 failed across all suites (including 13 new dedicated Phase 11B-1 tests).
- Next.js Build: 28/28 static & dynamic routes compiled successfully.
- Dataset Audit: Completed against all 10,698 dataset images.
- Strict compliance: Zero browser, dev server, localhost, live API calls, or model training executed.

### Next

Phase 11B-2 — Hard-Negative Mining + YOLO v2 Refinement Pipeline.

---

## Phase 11B-2 — Hard-Negative Mining + YOLO v2 Refinement Pipeline

**Date:** September 2026  
**Status:** IMPLEMENTED — HARD-NEGATIVE MINING + V2 TRAINING PIPELINE READY, PENDING NATHAN MANUAL REVIEW AND MODAL TRAINING

### Summary

Implemented the offline hard-negative mining and v2 fine-tuning pipeline to eliminate false-positive oral pathology predictions (specifically tooth discoloration and tartar) without mutating benchmark validation sets or manufacturing synthetic pathology:
- **Hard-Negative Mining**:
  - `scripts/mine_yolo_hard_negatives.py`: Evaluated all 457 empty-label training images in `dataset/oral-disease.yolov11/train/`.
  - Discovered 36 false-positive candidate images producing 86 false-positive bounding boxes (47 tooth discoloration, 22 caries, 16 calculus, 1 ulcer).
  - Clean pass rate: 421/457 (92.1%) empty-label images had zero detections at confidence >= 0.30.
  - Generated `dataset/hard-negative-candidates/review.csv` with initial status `UNREVIEWED` and priority scores.
  - Rendered offline visual contact sheets: `contact_sheet_01.jpg` (20 tiles) and `contact_sheet_02.jpg` (16 tiles).
- **v2 Dataset Strategy & Leakage Protection**:
  - `scripts/prepare_yolo_v2_dataset.py`: Updated with strict Phase 11B-2 split rules.
  - Only Nathan-approved hard negatives (`review_status == 'ACCEPT_NEGATIVE'`) are merged into the `train` split.
  - `valid` and `test` splits are copied 100% UNTOUCHED from original benchmark (zero negative leakage).
  - SHA-256 hash checking prevents any approved candidate matching valid or test images from entering training.
  - Controlled oversampling enabled via `--negative-repeat N` (default: 1, recommended: 2).
  - Original dataset `dataset/oral-disease.yolov11` is never mutated.
- **Modal v2 Fine-Tuning Script**:
  - `scripts/modal_train_yolo_v2.py`: Built using the existing working Modal pattern.
  - Uploads both `dataset/oral-disease-v2.yolov11.zip` and base weights `services/teeth_analyzer/models/oral_disease/best.pt` (`/root/best_v1.pt`).
  - Fine-tunes starting from `/root/best_v1.pt` (NOT `yolo11n.pt`) with AdamW `lr0=0.0005`, 12 epochs, batch 16, A10G GPU, saving to `daantshaant-yolo-v2-output` volume.
- **Documentation & Workflow**:
  - Updated `docs/evaluation/yolo_hard_negatives_guide.md` with candidate counts, review instructions, and exact execution commands.
  - Updated `docs/evaluation.md` and `context.md`.

### Files Created

- `scripts/mine_yolo_hard_negatives.py`
- `scripts/modal_train_yolo_v2.py`
- `services/teeth_analyzer/tests/test_phase11b2_mining_and_v2.py`
- `dataset/hard-negative-candidates/review.csv`
- `dataset/hard-negative-candidates/candidates.json`
- `dataset/hard-negative-candidates/contact_sheet_01.jpg`
- `dataset/hard-negative-candidates/contact_sheet_02.jpg`

### Files Modified

- `scripts/prepare_yolo_v2_dataset.py`
- `docs/evaluation/yolo_hard_negatives_guide.md`
- `docs/evaluation.md`
- `context.md`
- `docs/phase-log.md`

### Validation

- Unit Tests: 43 passed, 0 failed across all YOLO perception, calibration, and hard-negative mining suites (including 14 new dedicated Phase 11B-2 tests).
- Strict Compliance: Zero browser, dev server, localhost, live API calls, or model training executed by agent.

### Next

Nathan to manually inspect contact sheets and review CSV, approve clean negatives (`ACCEPT_NEGATIVE`), package v2 dataset, and launch Modal training.

---

## Phase 11B-3 — Mine Healthy Hard Negatives from Roboflow Dataset

**Date:** September 2026  
**Status:** IMPLEMENTED — CANDIDATES & CONTACT SHEETS GENERATED, MULTI-CSV MERGE READY, PENDING NATHAN REVIEW

### Summary

- Audited the external Roboflow dataset `dataset/Dental Data Set.yolov11` (427 images in `train`, 0 in `valid`/`test`).
- Parsed `data.yaml` dynamically: identified 7 classes with Class 6 (`Healthy Teeth`) representing normal dentition.
- Implemented strict exclusion logic:
  - 15 healthy-only images (all boxes belong solely to Class 6).
  - 144 mixed images (contain Class 6 + disease boxes like Calculus, Cavities, Gingivitis) strictly excluded to avoid false negatives.
  - 268 disease-only images strictly excluded.
- Evaluated all 15 healthy-only candidate images against current DaantShaant detector (`best.pt`) at confidence threshold $\ge 0.30$:
  - 9 images produced 56 false-positive predictions (54 tooth discoloration, 1 caries, 1 gingivitis) -> categorized as `candidate_type = MODEL_FALSE_POSITIVE`.
  - 6 images produced 0 detections -> categorized as `candidate_type = CLEAN_CONTROL`.
- Ranked false positives by priority score using severity weights (tooth discoloration 1.5, caries 1.4, calculus 1.3, gingivitis 1.1, ulcer 1.0).
- Computed SHA-256 file hashes: all 15 candidates are unique, and asserted 0 hash overlap with benchmark `valid` and `test` splits.
- Generated review deliverables:
  - `dataset/healthy-negative-candidates/review.csv`: 15 rows with `review_status = UNREVIEWED`, full predictions, confidence, priority, and notes.
  - `dataset/healthy-negative-candidates/candidates.json`: complete machine-readable metadata.
  - `dataset/healthy-negative-candidates/contact_sheet_01.jpg`: 1440x1440 4x4 visual review grid showing bounding boxes and confidences.
- Upgraded `scripts/prepare_yolo_v2_dataset.py` to support UTF-8-BOM, flexible path resolution, and merging multiple review CSVs (`dataset/review_ai_recommended.csv` + `dataset/healthy-negative-candidates/review.csv`).
- Documented third-party dataset source and CC BY 4.0 license in `docs/third-party-usage.md`.
- Generated detailed audit report in `docs/evaluation/yolo_small_healthy_dataset_audit.md`.

### Files Created

- `scripts/mine_healthy_negatives.py`
- `dataset/healthy-negative-candidates/review.csv`
- `dataset/healthy-negative-candidates/candidates.json`
- `dataset/healthy-negative-candidates/contact_sheet_01.jpg`
- `docs/evaluation/yolo_small_healthy_dataset_audit.md`
- `services/teeth_analyzer/tests/test_phase11b3_healthy_negatives.py`

### Files Modified

- `scripts/prepare_yolo_v2_dataset.py`
- `docs/third-party-usage.md`
- `context.md`
- `docs/phase-log.md`

### Validation

- Unit Tests: 57 passed, 0 failed across all Phase 11 test suites (14 dedicated Phase 11B-3 tests).
- Dry-run v2 Dataset Merge: verified successful loading of 8 approved from `dataset/review_ai_recommended.csv` and 0 from `dataset/healthy-negative-candidates/review.csv` with zero data leakage.
- Strict Compliance: Zero browser, dev server, localhost, external API calls, or model training executed by agent.

### Next

Nathan to review the 15 candidate images in `dataset/healthy-negative-candidates/contact_sheet_01.jpg` / `review.csv`, mark approved negatives as `ACCEPT_NEGATIVE`, run `prepare_yolo_v2_dataset.py` to package `oral-disease-v2.yolov11.zip`, and launch Modal v2 fine-tuning.

---

## Phase 11B-4 — Large Healthy-Negative Mining + V2 Dataset Preparation (FINAL)

**Date:** September 2026  
**Status:** IMPLEMENTED — FINAL LARGE HEALTHY POOL MINED, PENDING NATHAN AUDIT + V2 TRAINING

### Summary

- Audited external Roboflow dataset `dataset/Penyakit Gigi Skripsi.yolov11` (2,468 images across `train`: 1,974, `valid`: 247, `test`: 247).
- Verified metadata from local `data.yaml`: 3 classes (`0: calculus`, `1: caries`, `2: healthy`), license `CC BY 4.0`, project `penyakit-gigi-skripsi-i77mi`.
- Extracted all healthy-only images across all splits:
  - 338 healthy-only images (strictly Class 2 `healthy` boxes).
  - 1,342 mixed images excluded (`healthy` + `calculus`/`caries`).
  - 788 disease-only images excluded.
  - 0 empty-label files.
- Evaluated all 338 healthy-only images with `best.pt` (min confidence 0.30):
  - 129 `MODEL_FALSE_POSITIVE` images producing 934 false-positive bounding boxes.
  - Dominant failure mode: Tooth discoloration accounts for 89.3% (834/934) of false-positive detections on healthy teeth (104 images). Secondary: gingivitis (21 images / 87 boxes), caries (4 images / 13 boxes), calculus (0), ulcer (0).
  - 209 `CLEAN_CONTROL` images with zero detections $\ge 0.30$.
  - 55 auto-eligible controls passing physical quality filters (`review_status = AUTO_ELIGIBLE_CONTROL`).
- Implemented cryptographic and perceptual deduplication:
  - SHA-256: 338 unique hashes (0 exact duplicates).
  - 64-bit dHash: 233 near-duplicate image variants grouped into clusters. Primary instances retained; near duplicates labeled `REJECT_NEAR_DUPLICATE`.
- Evaluated physical quality metrics:
  - Excluded 49 unusable images: 41 severe blur (Laplacian variance $< 2.5$), 8 extreme overexposure ($> 35\%$ pixels $> 250$).
- Strict benchmark leakage protection:
  - SHA-256 cross-check against original `oral-disease.yolov11` valid (1,070) and test (1,070) splits confirms 0 matches (ZERO leakage).
- Generated candidate artifacts in `dataset/final-healthy-negative-candidates/`:
  - `review.csv`: 338 rows with full metadata, priority ranking, duplicate grouping, and quality scores.
  - `candidates.json`: complete machine-readable metadata.
  - `audit.json`: statistical audit summary.
  - `contact_sheet_fp_01.jpg` to `08.jpg`: 8 contact sheets displaying the top 120 false-positive candidates (16 tiles each, 4x4) ranked by clinical priority.
  - `contact_sheet_control_audit_01.jpg` to `04.jpg`: 4 contact sheets displaying a 50-image deterministic control audit sample (`seed=42`).
- Upgraded `scripts/prepare_yolo_v2_dataset.py`:
  - Added `--include-audited-controls` flag to opt-in `AUTO_ELIGIBLE_CONTROL` rows only after human audit.
  - Automatic class balance calculation: reports negative percentage of total v2 train set, alerts if $> 18\%$.
  - Large-pool repeat recommendation logic: recommends `repeat=1` if pool $\ge 500$, configurable if $< 200$.
- Verified `scripts/modal_train_yolo_v2.py` preserves the working A10G architecture, persistent volume, AdamW optimizer, `lr0=0.0005`, 12 epochs, and starting checkpoint `best_v1.pt`.

### Files Created

- `scripts/mine_large_healthy_pool.py`
- `dataset/final-healthy-negative-candidates/review.csv`
- `dataset/final-healthy-negative-candidates/candidates.json`
- `dataset/final-healthy-negative-candidates/audit.json`
- `dataset/final-healthy-negative-candidates/contact_sheet_fp_01.jpg` ... `08.jpg`
- `dataset/final-healthy-negative-candidates/contact_sheet_control_audit_01.jpg` ... `04.jpg`
- `docs/evaluation/yolo_final_large_negative_audit.md`
- `services/teeth_analyzer/tests/test_phase11b4_large_healthy_pool.py`

### Files Modified

- `scripts/prepare_yolo_v2_dataset.py`
- `docs/third-party-usage.md`
- `context.md`
- `docs/phase-log.md`
- `services/teeth_analyzer/tests/test_yolo_pipeline.py`

### Validation

- Unit Tests: 76 passed, 0 failed across all Phase 11 test suites (19 dedicated Phase 11B-4 tests).
- Dry-Run v2 Dataset Merge: verified successful loading of 14 existing approved negatives and 55 auto-eligible controls with zero leakage into validation or test splits.
- Strict Compliance: Zero browser, dev server, localhost, external API calls, or model training executed by agent.

### Next

Nathan visual review of top false positives (`contact_sheet_fp_*.jpg`) and 50-image control audit (`contact_sheet_control_audit_*.jpg`), v2 dataset generation with `prepare_yolo_v2_dataset.py`, and Modal v2 fine-tuning (`modal_train_yolo_v2.py`).

---

## Phase 11B Final — YOLO Final Model Freeze Configuration - IMPLEMENTED

**Date:** September 2026
**Status:** IMPLEMENTED — CONFIGURATION FROZEN (best_v2.pt), PENDING NATHAN TWO-IMAGE MANUAL ACCEPTANCE

### Summary

V2 model training and calibration have completed. In this phase, the detector configuration was frozen:
- Selected runtime model candidate: `services/teeth_analyzer/models/oral_disease/best_v2.pt`.
- Baseline retained as rollback checkpoint: `services/teeth_analyzer/models/oral_disease/best.pt` (V1 baseline physically preserved on disk, not deleted or overwritten).
- Environment configuration: `.env` and `.env.example` configured with `YOLO_DENTAL_MODEL_PATH=services/teeth_analyzer/models/oral_disease/best_v2.pt`.
- Model loader verification: The lazy singleton YOLO loader (`get_yolo_model()` in `services/teeth_analyzer/src/teeth_analyzer/yolo_detector.py`) resolves `settings.yolo_dental_model_path` against the repo root and will load `best_v2.pt` upon service start/restart.
- Engineering screening thresholds:
  - `calculus` (`tartar`): `0.35`
  - `caries` (`cavity_suspect`): `0.55`
  - `gingivitis` (`gingivitis_signs`): `0.50`
  - `tooth discoloration` (`discoloration`): `0.65`
  - `ulcer` (`oral_ulcer`): `0.65`
  - Global Fallback: `0.50`
- Centralized threshold resolver `get_confidence_threshold()` verified to return these exact per-class cutoffs for both raw and normalized clinical labels and fall back to 0.50 for unknown classes.
- Explicit non-medical disclaimer: These calibrated cutoffs represent engineering screening thresholds to balance sensitivity and false-positive suppression on intraoral screening photos; they do not constitute clinical validation claims or diagnostic guarantees.

### Files Modified

- `.env` — added `YOLO_DENTAL_MODEL_PATH=services/teeth_analyzer/models/oral_disease/best_v2.pt` and verified thresholds.
- `.env.example` — documented `YOLO_DENTAL_MODEL_PATH` and final engineering thresholds.
- `docs/architecture.md` — updated clinical perception pipeline stage 3 with `best_v2.pt` and class-specific thresholds.
- `docs/third-party-usage.md` — updated Ultralytics YOLO entry to reflect `best_v2.pt` frozen runtime and `best.pt` baseline retention.
- `docs/evaluation.md` — added Section 6 documenting model freeze configuration, baseline retention, and thresholds.
- `context.md` — recorded Phase 11B Final status, model freeze details, thresholds, and manual acceptance requirements.
- `docs/phase-log.md` — appended this chronological Phase 11B Final entry.
- `services/teeth_analyzer/tests/conftest.py` — added sibling module paths to `sys.path`.
- `services/teeth_analyzer/tests/test_calibration_and_negatives.py` — isolated fallback tests with `_env_file=None` and added tests 14 & 15 for Phase 11B frozen thresholds and model loader verification.

### Validation

- Unit Tests: 102 passed, 0 failed across all Phase 11 calibration, pipeline, and mining test suites (including 31 dedicated calibration/pipeline/loader tests in `test_calibration_and_negatives.py` and `test_yolo_pipeline.py`).
- Strict Compliance: Zero browser, dev server, localhost, live API calls, or model training executed by agent.

### Next

Nathan manual live verification of two acceptance test images after restarting services:
- **A. Known yellow/discolored teeth**: Tooth discoloration detection must survive threshold $\ge 0.65$.
- **B. Recently treated/clean teeth**: No unsupported discoloration or pathology prediction should be generated.

---

## Phase 11C — DentalTensor Vision v1.0 Model Branding & Identity Freeze

**Date:** September 2026  
**Status:** COMPLETE  

### Summary

Officially branded and froze the custom oral-vision model developed for DaantShaant as **DentalTensor Vision v1.0**, developed by **Nathan Asif**.
- **Model Product Separation**: DentalTensor is established as the standalone perception product / model family; DaantShaant is the product integration consuming DentalTensor.
- **Production Checkpoint**: `services/teeth_analyzer/models/oral_disease/dentaltensor_nathan_asif_v1.pt` created via byte-for-byte copy from `best_v2.pt`. SHA-256 verified identical (`42BF517DED4EB15EEBE6B5361EBF9E6AB21D8488098C4E3E4CCFE5912ECBBE27`). Previous checkpoints `best_v2.pt` and `best.pt` retained for rollback/history.
- **Runtime Model Path**: Configured `YOLO_DENTAL_MODEL_PATH=services/teeth_analyzer/models/oral_disease/dentaltensor_nathan_asif_v1.pt` in `.env`, `.env.example`, and `Settings` default.
- **Canonical Brand Metadata**: Added `DENTALTENSOR_MODEL_NAME = "DentalTensor Vision"`, `DENTALTENSOR_MODEL_VERSION = "1.0"`, `DENTALTENSOR_MODEL_DISPLAY_NAME = "DentalTensor Vision v1.0"`, and `DENTALTENSOR_DEVELOPER = "Nathan Asif"` centrally in `teeth_analyzer/config.py`.
- **Detection Metadata**: Updated diagnostic output metadata to identify `model = "DentalTensor Vision v1.0"` and `model_version = "dentaltensor-vision-v1.0"`.
- **Startup Logging**: Formatted startup/loading logs to cleanly report `Loading DentalTensor Vision v1.0`, `Developer: Nathan Asif`, and `Checkpoint: <resolved path>`.
- **Health Endpoint**: Added non-breaking fields `model_name`, `model_version`, and `developed_by` to `/health` in Teeth Analyzer.
- **Model Card**: Authored comprehensive model card `docs/dentaltensor-model-card.md` covering architecture (YOLO11n, 101 layers, 2.58M params, 6.4 GFLOPs), class mappings, dataset audit, 27 hard negatives (108 effective instances), Modal A10 training parameters, calibration improvements, screening limitations, and Nathan Asif ownership.
- **Safety Rule Enforced**: Internal identifiers (`services/teeth_analyzer/`, package name, imports, existing API routes, ports) strictly preserved. ML/triage behavior untouched.

### Files Created

- `docs/dentaltensor-model-card.md` — Professional model card for DentalTensor Vision v1.0.

### Files Modified

- `services/teeth_analyzer/src/teeth_analyzer/config.py` — Canonical brand metadata constants, settings attributes, and default checkpoint path.
- `services/teeth_analyzer/src/teeth_analyzer/yolo_detector.py` — DentalTensor branding comments, result dataclass metadata, loader logging, and detection result return values.
- `services/teeth_analyzer/src/teeth_analyzer/inference.py` — Docstring and perception pipeline comments updated.
- `services/teeth_analyzer/src/teeth_analyzer/main.py` — Added non-breaking model metadata to `/health`.
- `.env` — Set `YOLO_DENTAL_MODEL_PATH` to `dentaltensor_nathan_asif_v1.pt`.
- `.env.example` — Documented `dentaltensor_nathan_asif_v1.pt` and DentalTensor identity.
- `docs/architecture.md` — Updated pipeline diagram to reflect DentalTensor Vision v1.0 flow.
- `docs/third-party-usage.md` — Updated Ultralytics entry with DentalTensor Vision branding and model card link.
- `docs/evaluation.md` — Documented DentalTensor Vision v1.0 freeze in Section 6.
- `context.md` — Recorded Phase 11C status, model branding, and canonical identity.
- `docs/phase-log.md` — Appended this chronological entry.

### Validation

---

## Phase 12A Final — Central Dentist Reconstruction & Complete Hugging Face Removal

**Date:** September 2026  
**Status:** COMPLETE  

### Summary

Completely reconstructed the DaantShaant conversational assistant into **DaantShaant Central Dentist** and eliminated 100% of Hugging Face models, weights, embeddings, downloads, and runtime dependencies from the repository.

1. **Root Cause Resolution**: The 1–2 minute chat latency was diagnosed and eliminated. It was caused by `EmbeddingService._load_model()` attempting to download and execute `SentenceTransformer("all-MiniLM-L6-v2")` CPU embeddings inside the synchronous request lifecycle.
2. **Complete Hugging Face & FAISS Removal**:
   - Permanently deleted `orchestrator/src/orchestrator/rag/` (`embeddings.py`, `vector_store.py`, `chunker.py`, `ingest.py`, `retrieval_service.py`), `orchestrator/src/orchestrator/rag_endpoints.py`, and `data/rag/faiss_index.*`.
   - Removed `sentence-transformers`, `faiss-cpu`, `PyPDF2`, and `python-docx` from `orchestrator/pyproject.toml`.
   - Removed `RAG_EMBEDDING_MODEL` and FAISS index settings from `.env` and `.env.example`.
   - Cleaned `orchestrator/src/orchestrator/main.py` and `orchestrator/src/orchestrator/dentist_portal/routes_products.py`.
   - Verified zero Hugging Face or FAISS imports project-wide via AST tests.
3. **DaantShaant Central Dentist Engine (`orchestrator/src/orchestrator/central_dentist/`)**:
   - `nlp.py`: Pure lightweight deterministic NLP engine (<50ms, regex/tokenization/synonym mapping). 13 intents, entity extraction, temporal parsing, and fast-path identification without any neural models.
   - `retrieval.py`: Structured SQL RAG directly querying Supabase PostgreSQL repositories (`ScanRepository`, `AppointmentRepository`, `DentistRepository`) strictly scoped by authenticated `patient_id` UUID. Zero embeddings.
   - `knowledge.py`: Curated offline oral health guideline lookup based on keyword and finding keys.
   - `fast_path.py`: Deterministic response formatters that immediately answer factual questions (scan date, appointment date/time, confidence %, urgency level, greetings) bypassing Qwen entirely.
   - `prompts.py`: Central Dentist system persona, structured clinical context builder, and anti-slop / plain text response cleaner.
   - `graph.py`: Complete LangGraph pipeline orchestration with 10 deterministic nodes (`load_auth_context` -> `nlp_understanding` -> `plan_retrieval` -> `retrieve_patient_data` -> `retrieve_conversation_context` -> `retrieve_optional_knowledge` -> `build_grounded_context` -> `qwen_or_direct_answer` -> `validate_response` -> `persist_turn`).
4. **Tenant Isolation & Security**: Every patient data query is strictly scoped by the authenticated JWT session identity. Any user IDs or SQL injections in message text are ignored. Internal model weights, database schemas, and API keys are strictly excluded from context.
5. **DentalTensor Integrity Preserved**: DentalTensor Vision v1.0 in `services/teeth_analyzer/` (`torch`, `ultralytics`, `dentaltensor_nathan_asif_v1.pt`) was left untouched and fully verified with all 108 tests passing.

### Files Created

- `orchestrator/src/orchestrator/central_dentist/__init__.py`
- `orchestrator/src/orchestrator/central_dentist/nlp.py`
- `orchestrator/src/orchestrator/central_dentist/retrieval.py`
- `orchestrator/src/orchestrator/central_dentist/knowledge.py`
- `orchestrator/src/orchestrator/central_dentist/fast_path.py`
- `orchestrator/src/orchestrator/central_dentist/prompts.py`
- `orchestrator/src/orchestrator/central_dentist/graph.py`
- `orchestrator/tests/test_no_huggingface.py`
- `orchestrator/tests/test_central_dentist_nlp.py`
- `orchestrator/tests/test_central_dentist_data_isolation.py`
- `orchestrator/tests/test_central_dentist_query_aware_retrieval.py`
- `orchestrator/tests/test_central_dentist_grounding.py`
- `orchestrator/tests/test_central_dentist_fast_path.py`
- `orchestrator/tests/test_central_dentist_quality.py`
- `orchestrator/tests/test_central_dentist_graph.py`

### Files Deleted

- `orchestrator/src/orchestrator/rag/__init__.py`
- `orchestrator/src/orchestrator/rag/embeddings.py`
- `orchestrator/src/orchestrator/rag/vector_store.py`
- `orchestrator/src/orchestrator/rag/chunker.py`
- `orchestrator/src/orchestrator/rag/ingest.py`
- `orchestrator/src/orchestrator/rag/retrieval_service.py`
- `orchestrator/src/orchestrator/rag_endpoints.py`
- `data/rag/faiss_index.bin`
- `data/rag/faiss_index.meta.json`

### Files Modified

- `orchestrator/pyproject.toml`
- `orchestrator/src/orchestrator/main.py`
- `orchestrator/src/orchestrator/chat_service.py`
- `orchestrator/src/orchestrator/conversation_engine.py`
- `orchestrator/src/orchestrator/dentist_portal/routes_products.py`
- `.env` and `.env.example`
- `orchestrator/tests/test_chat_gateway_migration.py`
- `orchestrator/tests/test_chat_timing.py`
- `orchestrator/tests/test_recommendation_gateway_migration.py`
- `services/teeth_analyzer/tests/test_calibration_and_negatives.py`
- `docs/architecture.md`
- `docs/third-party-usage.md`
- `context.md`
- `docs/phase-log.md`

### Verification

- Orchestrator test suite: 375 passed, 1 skipped, 0 failures (including 42 new Central Dentist and HF removal tests).
- Teeth Analyzer test suite: 108 passed, 0 failures.
- Zero Hugging Face / FAISS runtime references confirmed via AST scan and import guards.

---

## Phase 12B — Central Dentist Live Latency, Deadlock & Chat Request Lifecycle Fix

**Date:** September 2026  
**Status:** COMPLETE

### Summary

- Diagnosed and fixed the live chat latency issues, UI deadlocks, and `asyncpg` connection hangs (`EAUTHTIMEOUT`).
- Added strict connection and socket timeouts to async SQLAlchemy engine (`pool_timeout=3.0`, `connect_args={"timeout": 3.0, "command_timeout": 3.0, "server_settings": {"statement_timeout": "3000"}}`).
- Reused a single request-scoped `AsyncSession` across authentication, patient data retrieval, and persistence, eliminating redundant queries and connection overhead.
- Implemented hard latency budgets:
  - Auth DB lookup: 2.0s
  - Structured patient retrieval: 2.0s
  - Persistence: 2.0s
  - Qwen generation: 8.0s (cancels provider call without multi-minute retry chains)
  - Global backend chat deadline: 12.0s (aborts and rolls back on timeout)
- Grounded deterministic fallback returning verified clinical scan/appointment data when provider calls time out.
- Generated unique `request_id` (e.g. `chat_7f92...`) and logged stage telemetry across the entire graph.
- Rewrote frontend chat UX (`ChatInterface.tsx`):
  - Instant input clearing and optimistic user message append on send.
  - Textarea remains editable for subsequent messages.
  - Functional Stop button (`⏹ Stop`) backed by `AbortController.abort()`.
  - Comprehensive `try / catch / finally` cleanup ensuring loading spinner never freezes.
  - Deduped submissions with submission ref guards.

### Files Created

- `orchestrator/tests/test_phase12b_latency_and_timeouts.py`

### Files Modified

- `orchestrator/src/orchestrator/config.py`
- `orchestrator/src/orchestrator/db/session.py`
- `orchestrator/src/orchestrator/dentist_portal/auth.py`
- `orchestrator/src/orchestrator/main.py`
- `orchestrator/src/orchestrator/central_dentist/graph.py`
- `orchestrator/src/orchestrator/chat_service.py`
- `apps/web/lib/chat-api.ts`
- `apps/web/components/ChatInterface.tsx`
- `apps/web/i18n/en.ts`
- `apps/web/i18n/ur.ts`
- `context.md`
- `docs/phase-log.md`

### Verification

- Full orchestrator test suite: 380 passed, 1 skipped, 0 failures (including all 5 new Phase 12B latency/timeout tests).
- Teeth Analyzer test suite: 108 passed, 0 failures.
- Frontend Next.js production build: 28/28 routes compiled cleanly, 0 TypeScript errors.
- Fast paths ("Hi", "What was the confidence?") verified to run in milliseconds without calling LLMs.

---

## Phase 12D — Urgent Auth & Session Resilience Fix

**Date:** September 2026  
**Status:** COMPLETE  

### Summary

Resolved intermittent Supabase/PostgreSQL connection timeouts that were triggering false invalid-credential errors and immediate frontend logouts:
- **Root Cause Resolution**:
  - Direct diagnostic testing confirmed that the initial TCP/TLS handshake from local machines to Supabase pooler (`aws-0-ap-northeast-2.pooler.supabase.com:5432`) takes between 6.2s and 11.4s. Aggressive connection timeouts (2-3s) caused `asyncpg` to abort with `TimeoutError`.
  - In `login_user`, unhandled DB timeouts returned HTTP 500, which the login UI misreported as `auth.invalid_credentials` ("Invalid email or password."). Password and credentials were never the issue.
  - On page load / dashboard mount, `fetchPortalProfile` called `/portal/auth/me`. When transient DB timeouts occurred, `fetchPortalProfile` threw `new Error("Session expired")`, causing `PortalDashboard` to redirect to `/patient/login` ~5 seconds after login.
- **Engine & Pool Optimization**:
  - `PostgresSettings`: `db_pool_size=5`, `db_max_overflow=10`, `db_pool_recycle_seconds=300` (proactive 5-minute recycling before Supavisor drops idle connections), `db_pool_timeout_seconds=15.0`, `db_connect_timeout_seconds=15.0`, `db_command_timeout_seconds=15.0`.
  - Single application engine with `pool_pre_ping=True` detecting stale pooled connections prior to query execution.
- **Transient DB Single Retry**:
  - Built `execute_with_single_retry(operation, *, op_name, backoff_seconds=0.2)` in `auth_utils.py`:
    - Catches `TimeoutError`, `OperationalError`, `DBAPIError`, and connection errors.
    - Waits 200ms and retries once. If failure persists, cleanly raises `HTTPException(503)`.
    - Never retries wrong passwords, invalid JWTs, or revoked refresh tokens.
  - Integrated across: `login_user`, `rotate_refresh_token`, `get_current_user`, and `get_user_profile`.
- **Refresh & /auth/me Resilience**:
  - A transient DB timeout during `/portal/auth/refresh` returns 503 and never deletes or revokes the client refresh cookie.
  - `/portal/auth/me` returns 503 on DB timeout instead of 401.
  - Frontend `refreshPortalSession`: on 503/network error, logs warning and returns `null` while preserving `activeUser` and suppressing `REFRESH_FAILED` broadcasts.
  - Frontend `authorizedFetch`: enforced single-refresh guard on 401 with in-flight deduplication across concurrent calls (zero recursion).
  - Frontend `fetchPortalProfile`: on 503/network error, preserves and returns current authenticated user snapshot so the user is never logged out.
  - `PortalDashboard`: only redirects to `/login` on genuine `SessionExpiredError`. Renders friendly retry UI if cold profile fetch encounters 503.
- **Login UI Error Classification**:
  - 401 -> `t("auth.invalid_credentials")` ("Invalid email or password.")
  - 503 -> `t("auth.service_unavailable")` ("Service is temporarily unavailable. Please try again in a moment.")
  - 500 / other -> `t("auth.server_error")` ("Unable to sign in right now. Please try again.")
  - 100% key parity across `en.ts` and `ur.ts`.
- **Observability Logging**:
  - Added sanitized telemetry: `[AUTH] login_attempt`, `[AUTH] login_db_timeout`, `[AUTH] login_invalid_credentials`, `[AUTH] login_success`, `[AUTH] refresh_success`, `[AUTH] refresh_invalid`, `[AUTH] refresh_db_unavailable`, `[AUTH] auth_me_db_unavailable`.
  - Zero passwords, raw tokens, or cookies exposed.
- **Token TTL Verification**:
  - Access token TTL: 30 minutes (`access_token_expire_minutes: 30`).
  - Refresh token TTL: 7 days (`refresh_token_expire_days: 7`, 604800s cookie max-age).

### Files Created

- `orchestrator/src/orchestrator/dentist_portal/auth_utils.py`
- `orchestrator/tests/test_auth_resilience.py`
- `apps/web/lib/__tests__/portal-auth-resilience.test.ts`

### Files Modified

- `orchestrator/src/orchestrator/config.py`
- `orchestrator/src/orchestrator/dentist_portal/auth.py`
- `orchestrator/src/orchestrator/dentist_portal/routes_auth.py`
- `orchestrator/src/orchestrator/dentist_portal/user_service.py`
- `apps/web/lib/portal-auth.ts`
- `apps/web/components/portal/LoginPage.tsx`
- `apps/web/components/portal/PortalDashboard.tsx`
- `apps/web/i18n/en.ts`
- `apps/web/i18n/ur.ts`
- `context.md`
- `docs/phase-log.md`

### Verification

- Backend resilience suite (`tests/test_auth_resilience.py`): 10 passed, 0 failed.
- Auth & security suite (`tests/test_auth_security.py` + `tests/test_phase10_5_portal_security_and_ops.py`): 20 passed, 0 failed.
- Latency & dashboard suites (`test_phase10_7_dashboards.py` + `test_phase12b_latency_and_timeouts.py`): 17 passed, 0 failed.
- Frontend auth resilience suite (`apps/web/lib/__tests__/portal-auth-resilience.test.ts`): 6 passed, 0 failed.
- Cross-tab auth suite (`apps/web/lib/__tests__/cross-tab-auth.test.ts`): 7 passed, 0 failed.
- TypeScript typecheck (`npx tsc --noEmit`): Exit code 0, 0 errors.
- Next.js production build (`npm run build`): 28/28 routes compiled successfully.

---

## Phase 12C — Qwen Live Latency & Provider Reliability Fix

**Date:** September 2026
**Status:** COMPLETE

### Summary

Investigated and resolved Central Dentist live latency and timeouts (15.0s hang with robotic `"I am currently having trouble reaching the AI assistant service..."` fallback):
- **Root Cause:**
  - `QwenProvider` and `GeminiProvider` instantiated a fresh `httpx.AsyncClient` per request, incurring recurring DNS, TCP 3-way handshake, and TLS 1.3 overhead across Singapore Model Studio endpoints.
  - Central Dentist prompt bloat (~1,850 chars) and empty placeholder sections dumped into context for general oral health queries.
  - Lack of a hard `asyncio.timeout` wrapper inside provider network requests.
  - Missing direct fast paths for high-frequency oral hygiene questions.
  - Fallback message exposed internal provider nomenclature to patients.
- **Provider Connection Pooling & Lifecycle:**
  - Implemented persistent, long-lived `httpx.AsyncClient` instances in `QwenProvider` and `GeminiProvider` with connection pooling (`Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=30.0)`).
  - Added clean shutdown hooks (`aclose()`) in providers and `AIGateway`, wired into FastAPI `lifespan`.
- **Latency & Timeout Budget:**
  - Enforced `chat_qwen_timeout_seconds=8.0` and `chat_request_timeout_seconds=12.0`.
  - Added hard `asyncio.timeout` guard in `QwenProvider` request execution.
  - Added remaining-budget awareness in `AIGateway`: skips secondary fallback if primary took $\ge 6.5\text{s}$, and bounds fallback timeout to remaining budget.
- **Prompt & Token Reductions:**
  - Central Dentist system prompt streamlined to core identity, grounding, screening vs diagnosis boundaries, and conciseness.
  - Context builder omits empty patient sections on general hygiene queries. Context window capped at 4 turns.
  - Output token ceiling capped at `max_tokens=300`.
- **Direct Fast-Paths & Curated Knowledge Fallbacks:**
  - Common hygiene questions (e.g. brushing, flossing) routed to instant (<1ms) deterministic fast paths.
  - Safe, curated knowledge fallback dictionary for high-frequency topics (brushing, flossing, mouthwash, checkups, sensitivity, bleeding gums, staining, bad breath).
  - Patient questions fall back to structured scan/appointment records.
  - Eradicated robotic "AI service" language; fallback returns natural, helpful phrasing.
- **Instrumentation & Telemetry:**
  - Granular timing metrics: `client_ready_ms`, `time_to_headers_ms`, `parse_ms`, `total_ms`.
  - Sanitized logging (`[QWEN][%s] request_started`, `prompt_chars=%d messages=%d approx_tokens=%d`). Zero prompts or secrets logged.

### Files Created

- `orchestrator/tests/test_phase12c_qwen_latency.py`

### Files Modified

- `orchestrator/src/orchestrator/config.py`
- `orchestrator/src/orchestrator/ai/schemas.py`
- `orchestrator/src/orchestrator/ai/qwen.py`
- `orchestrator/src/orchestrator/ai/gemini.py`
- `orchestrator/src/orchestrator/ai/gateway.py`
- `orchestrator/src/orchestrator/ai/factory.py`
- `orchestrator/src/orchestrator/main.py`
- `orchestrator/src/orchestrator/central_dentist/prompts.py`
- `orchestrator/src/orchestrator/central_dentist/nlp.py`
- `orchestrator/src/orchestrator/central_dentist/fast_path.py`
- `orchestrator/src/orchestrator/central_dentist/knowledge.py`
- `orchestrator/src/orchestrator/central_dentist/graph.py`
- `context.md`
- `docs/phase-log.md`

### Verification

- Phase 12C latency & provider unit suite (`orchestrator/tests/test_phase12c_qwen_latency.py`): 9 passed, 0 failed in 4.16s.
- Core AI & Phase 12B/12C suite (`test_no_huggingface.py`, `test_phase12b_latency_and_timeouts.py`, `test_phase12c_qwen_latency.py`, `test_qwen_provider.py`, `test_ai_gateway.py`, `test_ai_gateway_factory.py`, `test_gemini_provider.py`): 90 passed, 0 failed in 9.36s.
- Central Dentist suite (`fast_path`, `nlp`, `graph`, `grounding`, `data_isolation`, `quality`, `query_aware_retrieval`): 29 passed, 0 failed in 10.99s.
- Teeth Analyzer & DentalTensor Vision v1.0 suite (`services/teeth_analyzer/tests`): 105 passed, 0 failed in 17.86s.
- Diagnosis suite (`services/diagnosis/tests`): 27 passed, 0 failed in 1.60s.







