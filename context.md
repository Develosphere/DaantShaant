# DaantShaant Context

> Current implementation state. Read this first in every engineering chat.
> Last updated: Phase 8-lite - Evaluation Harness + Demo Metrics, September 2026.

## Product

DaantShaant is an AI-assisted oral-health screening and care-navigation platform for Pakistan and the UAE. It is an awareness tool, not a licensed medical diagnosis system.

## Current Architecture

```text
Next.js 14 + MapLibre GL JS + OpenFreeMap
    |
FastAPI Orchestrator
    |-- Unified Clinical LangGraph screening pipeline (snapshot/upload/live)
    |-- Chat + FAISS RAG
    |-- Product recommendation LangGraph
    |-- Dentist recommendation LangGraph (OSM Overpass + PostgreSQL DB + Deterministic Ranking)
    |-- Geocoding & Autocomplete (OSM Nominatim)
    |-- Unified access/refresh authentication
    |
SQLAlchemy 2 async + asyncpg + Alembic
    |
Supabase PostgreSQL (sole application database)
```

The Teeth Analyzer and Diagnosis services remain separate HTTP services. Existing AI, RAG, LangGraph, live scan, and open mapping behavior are active. Google Maps / Places is permanently removed from active runtime paths.

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
- Clinical vision (Teeth Analyzer) now runs Qwen primary with a Gemini technical fallback (Phase 2C); rule-based diagnosis replaced by deterministic triage (Phase 3B-lite)
- Conversational chat now generates text through the shared AI gateway (Qwen primary, Gemini fallback); FAISS/sentence-transformers RAG behavior is unchanged
- Product descriptions now use the shared AI gateway (Qwen primary, Gemini fallback); the product recommendation LangGraph also generates its reranking and final patient-facing text through the shared gateway
- Product and dentist recommendation LangGraphs
- Google Maps/Places baseline (scheduled for later removal)

## AI Gateway

Phases 2A.1-2A.4 built and now run the shared, provider-neutral AI stack at `orchestrator/src/orchestrator/ai/`:

- `AIProvider` abstract async interface (text/vision/structured), normalized `AIResult` and request schemas, and a small exception hierarchy.
- `AIGateway` routes by capability, enforces `AI_REQUEST_TIMEOUT_SECONDS`, normalizes provider/model/latency metadata, and performs controlled fallback only for explicitly typed technical failures (timeout, connection, 429, 5xx, malformed response). Configuration, structured-output, and unexpected programming errors (wrapped in `ProviderInternalError`) never silently fall back; both providers failing raises `AllProvidersFailedError`.
- `QwenProvider` (Phase 2A.2) implements the `AIProvider` contract against Alibaba Model Studio's OpenAI-compatible `/chat/completions` endpoint using plain `httpx` (no SDKs). It supports text, multimodal vision (base64 data URLs), and structured JSON output (`response_format=json_object` + parse into `AIResult.data`, `StructuredOutputError` on malformed output). Models come from `QWEN_*` configuration with optional per-request `model` override; provider/HTTP errors are mapped to the gateway exception hierarchy; API keys and image data never appear in errors or logs.
- `GeminiProvider` (Phase 2A.3) is the technical-fallback adapter. It targets Google's `v1beta` `generateContent` REST endpoint over plain `httpx` (no Google SDK introduced; the API key is sent in the `x-goog-api-key` header, never the URL). It supports text (system turns mapped to `systemInstruction`, `assistant`→`model`, ordering preserved), multimodal vision (`inlineData` mime_type + base64), and structured JSON output (`responseMimeType=application/json` + parse into `AIResult.data` + `jsonschema` validation, `StructuredOutputError` on invalid output) — behaviorally consistent with `QwenProvider` from the gateway caller's perspective. Models come from `GEMINI_MODEL` (optional `GEMINI_BASE_URL`) with per-request `model` override; errors map to the same gateway exception hierarchy; keys and image bytes never leak into errors/logs.
- `create_ai_gateway(settings)` / `get_ai_gateway()` in `ai/factory.py` (Phase 2A.4) are the production composition: `PRIMARY_AI_PROVIDER=qwen` and `FALLBACK_AI_PROVIDER=gemini` build `AIGateway(primary=QwenProvider, fallback=GeminiProvider, timeout_seconds=AI_REQUEST_TIMEOUT_SECONDS)`. Only `qwen` and `gemini` are supported (an empty fallback is allowed); unknown, empty-primary, or identical primary/fallback names raise `ProviderConfigurationError` - nothing is silently substituted. Adapter modules are imported inside the builders and providers are built on first use, so no provider instance, HTTP client, or network call exists at import time.
- First migrated real caller (Phase 2A.4): `conversation_engine.ConversationEngine` (the chat/conversational text-generation path behind `POST /v1/chat/message`) now calls `AIGateway.generate_text(TextRequest)` and reads only `AIResult.content`. The request carries no provider-specific model id: Qwen resolves `QWEN_CHAT_MODEL` (now actually used by `generate_text`) and the Gemini fallback resolves `GEMINI_MODEL`. RAG enhancement, conversation memory, state context, incomplete-tail completion, response cleaning, and the API response shape are unchanged; only the final provider invocation moved. Configuration and programming errors propagate (never masked by fallback); a technical failure of both providers, or an empty reply, falls back to the pre-existing deterministic issue-aware dental answer. Logging at this boundary is limited to `status/provider/model/latency_ms/fallback_used`.
- Second migrated real caller (Phase 2A.5a): `dentist_portal/description_generator.generate_product_description` (the last direct OpenRouter consumer) now calls `AIGateway.generate_text(TextRequest)` through the same shared gateway. The public function signature, the returned `{"ai_description": ..., "problems_solved": [...]}` dict, the system/user prompt content, temperature/max_tokens, markdown-fence stripping, and the deterministic fallback on failure are all preserved. Configuration and programming errors propagate; a full double-provider technical failure or an empty/unparseable reply degrades to the pre-existing deterministic product description. The module no longer imports `openrouter_client`.
- Third and fourth migrated real callers (Phase 2A.5b): the product recommendation AI path in `recommendation_ai_system/` now uses the shared gateway. `recommendation_agent.generate_response_node` (final patient-facing message) and `tools.rank_recommendations` (candidate reranking) each call `AIGateway.generate_text(TextRequest)` with `model=None` (Qwen resolves `QWEN_CHAT_MODEL`, Gemini fallback resolves `GEMINI_MODEL`). The gateway is resolved lazily via a module-level `_get_gateway()` handle and injected through an optional `gateway` kwarg for tests; neither module imports `llm_provider` or `openrouter_client`. The LangGraph topology (`START -> search_products -> conditional similarity -> get_details -> rank -> log_session -> generate_response -> END`), ranking/product-selection behavior, database queries, similarity behavior, session logging, and the public response contract are unchanged. Failure policy: technical double failure (`AllProvidersFailedError`) or empty gateway output degrades to the pre-existing deterministic template/ranking fallback; `ProviderConfigurationError`/`ProviderInternalError` propagate and are never masked. `rank_recommendations` still returns the JSON-array ranking the graph consumes, so it stayed on `generate_text` + existing parsing rather than being forced into `generate_structured` (the shared structured contract is a `dict`, and the array output would require restructuring).
- Legacy cleanup (Phase 2A.5c): `get_deterministic_fallback` relocated from `llm_provider.py` to `ai/fallbacks.py` (provider-independent, no AI/network dependency). `llm_provider.py` and `openrouter_client.py` deleted. Zero orchestrator runtime references to `LLMProvider`, `openrouter_client`, or `OPENROUTER_*` remain. The deterministic dental fallback table and behavior are fully preserved.
- Remaining legacy AI caller (not yet migrated, deliberately): the recommendation embedding service (Gemini text-embedding capability — not a chat/gateway concern). Clinical vision in the Teeth Analyzer was migrated in Phase 2C (Qwen primary + Gemini fallback; see below).
- No automated test makes a real AI API call; `scripts/test_qwen_connection.py` and `scripts/test_gemini_connection.py` remain manual, developer-run smoke tests.
- `AISettings` in `config.py` defines the Qwen-primary / Gemini-fallback contract; `.env`/`.env.example` carry the keys.

## Semantic Dental Relevance - PHASE 2B COMPLETE (WIRED INTO PRODUCTION SCAN)

Phase 2B.1 added `orchestrator/src/orchestrator/clinical/relevance.py`: `evaluate_dental_relevance(image_base64, content_type, gateway=None)` answers only "is this image semantically relevant enough for dental screening?" - it is separate from mechanical quality, clinical findings, and diagnosis/triage, and performs no diagnosis or treatment advice.

- Categories: `relevant` -> `continue`, `retake` -> `retake`, `unrelated` -> `reject` (deterministic mapping, no confidence thresholds; model confidence/relevance_score preserved for evaluation). External jaw/cheek swelling can be relevant without visible teeth; ordinary face selfies without oral/jaw relevance are unrelated.
- Returns a normalized `DentalRelevanceResult` (classification, is_dental_relevant, confidence, relevance_score, visible_regions, reason, retake_reason, recommended_action) built from `StructuredRequest` via `AIGateway.generate_structured` (Qwen primary, Gemini technical fallback, `model=None`). Uses `get_ai_gateway()` unless a gateway is injected; no concrete-provider imports.
- Provider failures propagate as typed errors and are never converted to `unrelated`; image base64 is never logged, persisted, or embedded in errors.
- Manual smoke: `scripts/test_dental_relevance.py --image <path>`.

### Production Integration (Phase 2B.2) - ACTIVE

All three production scan modes (snapshot, upload, live WebSocket) now gate clinical vision behind semantic relevance through ONE shared helper `pipeline.run_scan_with_relevance(request, gateway=None) -> ScanOutcome`. Snapshot and upload are the same HTTP endpoint (`POST /v1/teeth/analyze`, `response_model` moved to `ScanOutcome`); live `process_frame` calls the same helper. The helper routes on `recommended_action`/`classification` (never the `is_dental_relevant` boolean, so retake is distinct from unrelated):

- `relevant` -> `continue` -> calls the existing `run_teeth_analysis_pipeline` (unchanged Teeth Analyzer clinical vision) and returns status `analyzed` with full `analysis` + `diagnosis` (backward-compatible keys).
- `retake` -> stops before clinical vision; HTTP returns status `retake` (analysis/diagnosis null, `recommended_action="retake"`, `retake_reason`); live sends a lightweight `relevance.retake` status and keeps the session open.
- `unrelated` -> stops before clinical vision; HTTP returns status `rejected` (`recommended_action="reject"`); live sends a lightweight `relevance.rejected` status and keeps the session open so later frames can still be analyzed.
- Relevance provider technical failure propagates as a typed gateway error (route surfaces it; live falls to its safe analysis-error path and the session continues) - never reported as `unrelated`.
- Response exposes a minimal provider-neutral `RelevanceInfo` (classification, recommended_action, reason, retake_reason, confidence, relevance_score, visible_regions) with no provider/model/prompt/base64 exposure.
- Persistence: `ScanRepository.add_result(..., relevance=...)` now stores `relevance_score` and `relevance_result` (JSONB) for `analyzed` scan records; these columns already existed in the baseline migration (no new schema/migration). Retake/unrelated produce no scan record (no clinical analysis occurred).
- Logging: a safe `[RELEVANCE] classification=... action=... confidence=... scan_mode=... duration_ms=...` line; never image bytes, prompts, or keys.
- Mechanical-quality ordering limitation (temporary): the Teeth Analyzer still combines mechanical quality and clinical vision in one request, so relevance now runs at the earliest safe orchestrator point - BEFORE that combined call. Relevant images still get the analyzer's existing quality behavior; gated (retake/unrelated) images skip the analyzer entirely, so expensive clinical vision is never run for them. Phase 2C may reorganize the clinical vision/quality boundary.

## Clinical Vision Provider Policy - PHASE 2C COMPLETE (TEETH ANALYZER)

The Teeth Analyzer service (`services/teeth_analyzer/`, :8001) now runs clinical vision through a SERVICE-LOCAL provider policy: **Qwen PRIMARY -> Gemini TECHNICAL FALLBACK**. It does NOT call the orchestrator and shares no code with the orchestrator gateway (no circular dependency); it mirrors the same proven design in a self-contained stack under `src/teeth_analyzer/`:

- `backends/errors.py` - typed exception hierarchy. `ProviderTechnicalError` subclasses (timeout, unavailable, rate-limit, server, invalid-response) carry `fallback_eligible=True`; `ProviderConfigurationError` / `ProviderInternalError` are non-fallback and propagate. `AllProvidersFailedError` when both providers fail technically.
- `backends/vision_common.py` - ONE shared clinical-vision prompt + `parse_findings` normalizer, so both providers return the SAME internal shape (`VisualFinding[]`). Output is structured VISUAL SCREENING (oral_regions_visible, findings[finding_code/observation/region/tooth_reference/confidence/visibility], overall_observation, limitations), explicitly "NOT a definitive diagnosis and NOT treatment advice". Finding codes are preserved for downstream Diagnosis but worded as possible/suspected.
- `backends/qwen.py` - `analyze_with_qwen` (async, plain httpx): Alibaba Model Studio OpenAI-compatible `{QWEN_BASE_URL}/chat/completions`, `Authorization: Bearer {DASHSCOPE_API_KEY}`, multimodal (text + `data:image/jpeg;base64,...`), `response_format=json_object`.
- `backends/gemini.py` - `analyze_with_gemini` (async, plain httpx; Google SDK removed): `v1beta` `{model}:generateContent`, `x-goog-api-key` header, `inlineData` base64, `responseMimeType=application/json`. Technical fallback only.
- `provider_policy.py` - `run_clinical_vision(jpeg_bytes, locale) -> ClinicalVisionOutcome(findings, provider, model, latency_ms, fallback_used)`. Tries Qwen; on a `fallback_eligible` technical error tries Gemini once; non-fallback (config/programming) errors propagate immediately and are NEVER masked; both-technical-failure raises `AllProvidersFailedError`. Emits `[CLINICAL_VISION] provider=... model=... fallback_used=... latency_ms=...` (never base64/keys/Authorization).
- `inference.py` - `analyze_image` is now async. The mechanical-quality gate is PRESERVED and runs BEFORE any AI call (a low-quality image is rejected without calling Qwen/Gemini). `backend="stub"` forces the offline deterministic backend; `AllProvidersFailedError` degrades to the stub ONLY if `TEETH_ANALYZER_FALLBACK_TO_STUB` is explicitly enabled (dev), else surfaces `VisionBackendError` (HTTP 503).
- `config.py` - shared-first env via `AliasChoices`: `DASHSCOPE_API_KEY`, `QWEN_BASE_URL`, `QWEN_VISION_MODEL` (default `qwen3.7-plus`), `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_BASE_URL`, `AI_REQUEST_TIMEOUT_SECONDS` (default 60). `TEETH_ANALYZER_*` aliases preserved. `backend` default changed `stub -> qwen`. OpenRouter config fields removed.

Preserved: image preprocessing / mechanical-quality logic (untouched), the public `AnalyzeResponse` contract (`findings: VisualFinding[]`, with provider/model/fallback metadata kept internal and never leaked into the public scan API), and Diagnosis (:8002) compatibility - Diagnosis still derives its finding-label list from the analyzer findings; disease/severity mapping was NOT rewritten (that is Phase 3B). OpenRouter is PERMANENTLY ABANDONED: `backends/openrouter.py` deleted, `TEETH_ANALYZER_OPENROUTER_*` config removed, ZERO active runtime references project-wide (only historical doc mentions and the test asserting its absence remain).

Validation: `services/teeth_analyzer/tests/test_clinical_vision.py` - 19 passed (16 required + 3 extra), zero real AI calls (httpx.MockTransport + fakes + a stubbed quality gate).

## Deterministic Clinical Triage - PHASE 3B-LITE COMPLETE

Phase 3B-lite replaced the legacy hard-coded disease/severity mapping in the Diagnosis service with a deterministic, rule-based triage engine (`services/diagnosis/src/diagnosis/triage.py`). NO LLM call is introduced — the same input always produces the same output.

### Triage Engine

- One explicit `TriageRule` per canonical finding code (healthy_tissue, plaque_detected, tartar, cavity_suspect, cavity_advanced, gingivitis_signs, gum_disease_severe, discoloration, missing_or_damaged_teeth) plus an UNKNOWN fallback rule for unrecognised codes.
- Each rule maps to: verdict, possible_concerns, urgency_level (routine/soon/urgent/emergency), recommended_actions, recommended_specialist, visit_timeframe, and limitations.
- Urgency ordering: routine < soon < urgent < emergency. Multiple findings → highest urgency wins. Concerns, actions, limitations and supporting findings are deduplicated.
- Low confidence or limited visibility only add a limitation statement — they never increase diagnostic certainty and never escalate urgency.
- Wording is deliberately non-definitive: "possible concern", "may be consistent with", "AI screening suggests", "should be confirmed by a licensed dentist". No rule claims a confirmed disease, says "you have X", prescribes treatment, or guarantees an outcome.

### Safety Fixes

- `missing_or_damaged_teeth` previously mapped to `ConditionLabel.ADVANCED_CAVITY`. It now routes to the new `ConditionLabel.MISSING_OR_DAMAGED_TOOTH` with urgency `soon` and a restorative evaluation recommendation. Legacy aliases (`broken_teeth`, `missing_teeth`, `damaged_teeth`) are corrected the same way.
- `cavity_advanced` internal finding code is preserved for compatibility, but patient-facing output says "Possible significant tooth decay / structural damage", never "Advanced Cavity" or "you have advanced cavity".

### Schema Additions (additive/optional)

- `UrgencyLevel` enum: `routine`, `soon`, `urgent`, `emergency`.
- `TriageResult` model: verdict, condition_summary, possible_concerns, urgency_level, recommended_actions, recommended_specialist, visit_timeframe, limitations, supporting_findings, rule_ids, confidence, disclaimer.
- `DiagnoseResponse.triage: TriageResult | None` — additive field; existing consumers that only read legacy fields keep working unchanged.
- `VisualFinding.visibility: str | None` — additive field passed through from clinical vision.
- `ConditionLabel.MISSING_OR_DAMAGED_TOOTH` — new enum member.

### API / Frontend Compatibility

- The legacy `DiagnoseResponse` contract (condition_label, severity, confidence, confidence_threshold, meets_threshold, action_trigger, disclaimer, diagnosed_at) is preserved unchanged. The `triage` field is additive and optional.
- `classifier.py` now delegates finding→concern mapping to `triage.py` and adapts the `TriageDecision` back into the legacy response fields.
- Frontend `DiagnosisReport.tsx` prefers the safer triage wording when the backend provides it (condition_summary as headline, triage verdict/concerns/actions/limitations rendered in a new block). Falls back gracefully when `triage` is null. Label changed from "AI Diagnosis" to "AI Screening Report"; "Detected condition" to "AI screening — possible concern".
- Frontend `types.ts` adds `TriageResult`, `UrgencyLevel`, and the optional `triage` field on `DiagnosisResult`.

### Validation

- `services/diagnosis/tests/test_triage.py`: 27 passed. Zero external AI calls. Covers: per-finding urgency, safety wording, missing_or_damaged_teeth safety fix, multiple findings highest-urgency, deduplication, limited visibility/low confidence limitations, specialist routing, visit timeframe, API endpoint compatibility, low quality legacy path, below-threshold confidence, unrecognised finding, no provider/network call, determinism, safe observability logging.

## Unified Clinical LangGraph — PHASE 4-LITE COMPLETE

Phase 4-lite unified the end-to-end clinical screening flow into a single, deterministic StateGraph (`orchestrator/src/orchestrator/clinical/graph.py`).

- **Topology**: `START → intake → relevance → [route] → clinical_vision → triage → report → persist → END`
- **Relevance routing**: `retake` and `unrelated` short-circuit directly to `END` before expensive clinical vision; `continue` proceeds to `clinical_vision`.
- **Boundaries**:
  - `relevance_node` delegates to `evaluate_dental_relevance()`.
  - `clinical_vision_node` delegates to `run_teeth_analysis_pipeline()` (Teeth Analyzer HTTP boundary). Mechanical image quality remains inside Teeth Analyzer for MVP.
  - `triage_node` reads `DiagnoseResponse.triage` returned by the Diagnosis HTTP service (does not duplicate rules or import diagnosis internals).
  - `persist_node` uses `ScanRepository.add_result()` when `db_session` is provided.
- **Shared Path**: `pipeline.run_scan_with_relevance(...)` is the single integration point calling `run_clinical_graph(...)`, preserving the `ScanOutcome` contract across snapshot, upload, and live WebSocket modes.
- **Observability**: Safe node execution trace (`node`, `status`, `duration_ms`) appended without image bytes, prompts, or API keys.

## Dentist Discovery & Open Mapping — PHASE 6 FAST TRACK COMPLETE

Phase 6 Fast Track replaced Google Maps / Places runtime dependencies across frontend and backend with an open mapping and discovery stack:

- **External Dentist Discovery**: OpenStreetMap via Overpass API (`orchestrator/src/orchestrator/dentist_recommendation/osm_dentists.py`) queries `amenity=dentist` and `healthcare=dentist` using geographic search coordinates. No patient clinical data is transmitted. Gracefully handles timeouts and failures by returning database platform dentists without crashing.
- **Local Distance Calculation**: Haversine formula calculates great-circle distances locally without third-party APIs.
- **Deterministic Multi-Factor Ranking** (`ranking.py`): Prioritizes:
  1. Specialist relevance match (from clinical screening triage `recommended_specialist` / issue)
  2. Verified registered platform dentists (`is_verified=True` and `source="platform"`)
  3. Distance proximity
  4. Partner status (small tiebreaker ONLY — never overrides clinical specialist relevance)
- **LangGraph Integration**: StateGraph in `dentist_agent.py` (`query_platform → query_osm → merge_rank → log_session → END`) orchestrates platform and OSM discovery and persists recommendations to Supabase PostgreSQL.
- **Address Autocomplete & Geocoding**: Proxies to OpenStreetMap Nominatim (`autocomplete_service.py`, `geocoding.py`) with DaantShaant User-Agent header; Google Places autocomplete removed.
- **Frontend Map & Geolocation**: Next.js client component (`DentistMapView.tsx`) uses `MapLibre GL JS` with `OpenFreeMap` Liberty style vector tiles. Browser GPS uses `navigator.geolocation`. Directions link to OpenStreetMap routing. Consultation booking is restricted to verified platform dentists (`d.tier === 'platform' && d.dentist_id`), while external OSM clinics display direct contact information.
- **Attribution**: Proper attribution for OpenStreetMap contributors and OpenFreeMap is visibly rendered on the map.
- **Google Maps / Places**: ZERO active runtime callers.

## Evaluation Harness & Demo Metrics — PHASE 8-LITE COMPLETE

Phase 8-lite added a reproducible clinical evaluation harness and metrics calculation engine (`orchestrator/src/orchestrator/evaluation/`):

- **Dataset Manifest (`schemas.py`)**: Format supporting `expected_relevance`, `expected_findings`, `expected_urgency`, `expected_specialist`, and provenance metadata (`source`, `license`, `attribution`). No patient images are committed; raw datasets stay external to Git.
- **Evaluation Metrics (`metrics.py`)**:
  - Semantic relevance accuracy & confusion matrix
  - Multi-label clinical findings set-based precision, recall, F1, and exact-match rate
  - Deterministic triage urgency accuracy and specialist match accuracy
  - Safety phrasing violation detection (flags definitive diagnosis language)
  - Latency distribution statistics (mean, median, p95, min, max)
  - AI provider fallback rate monitoring
- **Dentist Ranking Benchmark**: Validates specialist clinical relevance priority over commercial partner status across standard scenarios.
- **CLI Runner (`scripts/run_evaluation.py`)**: Offline mock simulation mode (default, zero external network calls) and explicit `--real` mode; outputs human-readable console tables and demo summary JSON.

## Final UI Integration & Demo UX — PHASE 10 FAST TRACK COMPLETE

Phase 10 Fast Track unified and polished the frontend user experience across the primary patient demo journey:

- **Scan Page & Loading Experience**:
  - Safe multi-stage client-side progress tracker (Preparing image → Checking dental relevance → Analyzing oral findings → Evaluating screening urgency → Building report).
  - Live elapsed timer (`⏱️ Ns elapsed`) and phased reassurance messages at 15s and 35s to eliminate uncertainty during long-running inference.
  - Prevention of duplicate analyze clicks while preserving the selected image.
  - Built-in "Try sample demo scan" helper for instant evaluation without uploading local files.
- **AI Screening & Triage Report**:
  - Triage-first presentation: "AI Screening Verdict" headline with "Possible Concerns" list and semantic urgency badges (`urgency-routine`, `urgency-soon`, `urgency-urgent`, `urgency-emergency`).
  - Human-readable visual finding names (e.g. "Possible decay-related visual finding", "Visible tartar / calculus", "Visible signs of gum inflammation", "Missing or visibly damaged tooth structure").
  - Confidence explicitly presented as "AI visual confidence" rather than diagnostic certainty.
  - Prominent non-medical screening safety statement: *"DaantShaant provides AI-assisted screening, not a medical diagnosis. A licensed dentist should confirm concerns and treatment needs."*
- **Dentist Discovery & MapLibre OpenFreeMap Integration**:
  - Seamless interactive link between dentist cards and OpenFreeMap vector map (clicking a card focuses and pans the map; clicking a pin selects the card).
  - Clear distinction between verified platform dentists (with consultation booking) and external OpenStreetMap clinic listings (with direct call/directions, no fake booking).
  - Graceful geolocation permission denial fallback with friendly guidance and instant location search modal.
  - Visible OpenStreetMap contributors and OpenFreeMap attribution maintained.
- **Chat Safety Identity & Error Handling**:
  - AI assistant identity set to "DaantShaant AI Assistant" / "Your AI oral-health companion" without claiming to be a licensed human dentist.
  - Intercepts raw backend JSON errors (`downstream_unavailable`, `downstream_error`, timeout, relevance reject/retake) into clean, friendly user-facing messages.

## Bilingual English/Urdu + Light/Dark Theme + Public Copy Hardening — PHASE 10.1 COMPLETE

Phase 10.1 implemented full bilingual capabilities, light/dark theme support, and hardened patient-facing copy across the webapp:

- **Bilingual i18n System (`apps/web/i18n/`)**:
  - Full English (DEFAULT) and Urdu dictionaries with 100% key parity (190 keys each).
  - Context provider with localStorage persistence (`daantshaant_locale`), dynamic `lang="en" | "ur"`, and `dir="ltr" | "rtl"`.
  - Urdu typography fallback stack (`"Noto Nastaliq Urdu"`, `"Noto Sans Arabic"`).
  - Synchronized geocoding language: address autocomplete and reverse geocoding pass the active `lang` / `Accept-Language` (`en` or `ur`) so English mode never returns Urdu text and vice versa.
- **Theme System (`apps/web/theme/`)**:
  - Light (DEFAULT) and Dark themes with `data-theme="light"` and `data-theme="dark"` on `<html>`.
  - Contrast tokens: high-contrast dark text on light surfaces (`#0f172a`, `#334155`) in Light mode; crisp readable light text on dark surfaces (`#f8fafc`, `#e2e8f0`) in Dark mode. No low-contrast or white-on-white text issues.
- **Public-Facing Copy Hardening**:
  - Implementation/stack technical terminology (`OSM`, `Nominatim`, `OpenStreetMap`, `OpenFreeMap`, `MapLibre`, `Qwen`, `Gemini`, `LangGraph`, `Supabase`, `Python`, `API`, model providers) removed from public user-facing UI while retaining proper map attribution on map canvas.
  - "Oral scan", "Oral Health Screening", "Screening Verdict", "Visual Findings", "Screening Confidence" standardized.
  - Professional dental assistant identity: "DaantShaant Oral Health Assistant", "Your oral-health companion".
- **Header Controls**:
  - Responsive language toggle (`EN | اردو`) and theme toggle (☀️ / 🌙) on portal and public headers.

## Known Remaining Issues

- AI usage is less fragmented but not fully unified: chat text generation, product descriptions, and the product recommendation graph go through the shared orchestrator gateway, and Teeth Analyzer clinical vision now runs a service-local Qwen-primary / Gemini-fallback policy (Phase 2C). Clinical RAG and the recommendation embedding service still use direct Gemini paths. OpenRouter has ZERO active runtime references project-wide.
- Deep evidence grounding (Phase 3A RAG) not yet started — triage rules carry lightweight metadata only (rule_id, rationale), no citations or guideline references.
- The frontend dependency audit currently reports three high-severity advisories; dependency upgrades require a separate compatibility/security phase.

## Completed Phases

| Phase | Name | Status |
|---|---|---|
| 0 | Hackathon Rebaseline | COMPLETE |
| 1A | Supabase PostgreSQL Foundation | COMPLETE |
| 1B | Full Supabase PostgreSQL Cutover (identity/auth/domain migration) | COMPLETE |
| 2A.1 | Shared AI Gateway Core (provider-neutral, no callers migrated) | COMPLETE |
| 2A.2 | Alibaba Qwen Provider Adapter (gateway-level, no callers migrated) | COMPLETE |
| 2A.3 | Gemini Fallback Provider Adapter (gateway-level, no callers migrated) | COMPLETE |
| 2A.4 | AI Gateway Composition + First Caller Migration (chat text generation) | COMPLETE |
| 2A.5a | Migrate Product Description Generator Off OpenRouter | COMPLETE |
| 2A.5b | Migrate Recommendation AI Off Legacy LLM Provider | COMPLETE |
| 2A.5c | Remove Legacy OpenRouter / LLM Infrastructure | COMPLETE |
| 2B.1 | Semantic Dental Relevance Core (standalone, not yet wired) | COMPLETE |
| 2B.2 | Production Semantic Relevance Integration (snapshot + upload + live) | COMPLETE |
| 2C | Qwen Clinical Vision (Teeth Analyzer Qwen primary + Gemini fallback; OpenRouter removed) | COMPLETE |
| 3B-lite | Deterministic Clinical Triage (rule-based screening triage, safety fixes, no LLM) | COMPLETE |
| 4-lite | Unified Clinical LangGraph (deterministic scan-to-care pipeline orchestration) | COMPLETE |
| 6 Fast Track | Dentist Discovery + OSM/Overpass + MapLibre/OpenFreeMap | COMPLETE |
| 8-lite | Evaluation Harness + Demo Metrics | COMPLETE |
| 10 Fast Track | Final UI Integration + Demo UX Polish | COMPLETE |
| 10.1 | Bilingual English/Urdu + Light/Dark Theme + Public Copy Hardening | COMPLETE |

The former Phase 1C is obsolete because its domain migration scope was merged into Phase 1B.

## Next Phase

**Phase 11 — Deployment Fast Track**.

