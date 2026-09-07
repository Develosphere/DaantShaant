# DaantShaant Context

> Current implementation state. Read this first in every engineering chat.
> Last updated: Phase 12A Final — DaantShaant Central Dentist Reconstruction & Complete Hugging Face Removal, September 2026.

## Product

DaantShaant is an AI-assisted oral-health screening and care-navigation platform for Pakistan and the UAE. It is an awareness tool, not a licensed medical diagnosis system.

## Current Architecture

```text
Next.js 14 + MapLibre GL JS + OpenFreeMap
    |
FastAPI Orchestrator
    |-- Unified Clinical LangGraph screening pipeline (snapshot/upload/live)
    |-- DaantShaant Central Dentist (LangGraph + Central Patient Data + Structured RAG + Qwen)
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
| 10.2 | Nearby Dentist Repair + Product Marketplace Integrity | COMPLETE |
| 10.3 | Live Nearby Dentist Discovery Integration (Current Location + Adaptive Radius + Multi-Source) | COMPLETE |
| 10.4 | Production Live Dentist Discovery + Map Integration (Registered Dentists + Public Discovery + Adaptive Ranking) | IMPLEMENTED — PENDING NATHAN MANUAL LIVE ACCEPTANCE |
| 10.4.1 | Optional Scan Context Resilience (Stale/Missing/Unowned scan_id Never Blocks Discovery) | COMPLETE |
| 10.4.3 | Final Map Baselayer Repair + Dentist Listing UI Simplification | COMPLETE |
| 10.5 | Portal Security + Brand Consistency + Dentist Operations | COMPLETE |
| 10.6 | Final Design Cleanup + Cross-Tab Session Hardening | COMPLETE |
| 10.7 | Real Data-Driven Patient + Dentist Dashboards | COMPLETE |
| 11A | Specialized YOLO Dental Pathology Perception Pipeline | IMPLEMENTED — PENDING NATHAN MANUAL ACCEPTANCE |
| 11B-1 | YOLO Detector Calibration + Hard-Negative Preparation | IMPLEMENTED — CALIBRATION/HARD-NEGATIVE TOOLING READY, PENDING NATHAN DATA REVIEW AND V2 TRAINING |
| 11B-2 | Hard-Negative Mining + YOLO v2 Refinement Pipeline | IMPLEMENTED — HARD-NEGATIVE MINING + V2 TRAINING PIPELINE READY, PENDING NATHAN MANUAL REVIEW AND MODAL TRAINING |
| 11B-3 | Mine Healthy Hard Negatives from Roboflow Dataset | COMPLETE |
| 11B-4 | Large Healthy-Negative Mining + V2 Dataset Preparation | COMPLETE |
| 11B Final | YOLO Final Model Freeze Configuration | COMPLETE |
| 11C | DentalTensor Vision v1.0 Model Branding & Freeze (Nathan Asif) | COMPLETE |
| 12A Final | Central Dentist Reconstruction & Hugging Face Removal | COMPLETE |
| 12B Final | Central Dentist Live Latency, Deadlock & Chat Request Lifecycle Fix | COMPLETE |
| 12C | Final Chat Identity Cleanup (DaantShaant Public Identity Freeze) | COMPLETE |
| 12D | Urgent Auth & Session Resilience Fix (Transient DB Timeout & Logout Hardening) | COMPLETE |

## Phase 10.7 Summary — Real Data-Driven Patient + Dentist Dashboards

- **Implementation Status**:
  - PHASE 10.7 IMPLEMENTED — PENDING NATHAN MANUAL ACCEPTANCE
- **Authenticated Aggregate Dashboard Endpoints**:
  - `GET /portal/patient/dashboard`: Aggregate endpoint deriving current patient from authenticated access token via `get_current_patient`. Replaces multiple uncoordinated frontend requests with a single fast, indexed read.
  - `GET /portal/dentist/dashboard`: Aggregate endpoint deriving current dentist from authenticated access token via `get_current_dentist`. Strictly scopes products, orders, and appointments by verified dentist owner user ID.
- **Patient Dashboard Data Pipeline**:
  - `stats.scan_count`: Computed directly from persisted `Scan` table (`patient_user_id == user_id`) using `func.count()`. Honest zero returned if patient has no scans.
  - `stats.order_count`: Computed directly from persisted `Order` table (`patient_user_id == user_id`) using `func.count()`.
  - `stats.oral_status`: Derived deterministically from latest persisted screening / deterministic triage urgency (`routine`, `soon`, `urgent`, `emergency`). If no scans exist, returns `null` ("No Screening Yet"), eliminating hardcoded "Good Standing".
  - `latest_screening`: Resolves the latest persisted screening and clinical report ordered deterministically by canonical timestamp (`created_at.desc()`). Exposes human-readable verdict, summary, urgency, AI visual confidence, recommended specialist, and major visible observations.
  - `recommended_products`: Clinically relevant active dentist products matching patient's screening findings (or persisted recommendations). No AI calls, no hallucinations, no fake marketplace products. Returns honest empty state if no matching products exist.
  - `recent_orders`: Up to 4 recent orders from patient history with item names, clinic names, quantities, amounts, and statuses.
  - `recent_activity`: Assembled from real persisted scan, order, and appointment events merged and sorted by canonical timestamp.
- **Dentist Dashboard Data Pipeline**:
  - `product_count`: Scoped to products owned by the authenticated dentist (`Product.dentist_id == dentist.id`).
  - `order_count`: Reflects orders containing products uploaded by this dentist. Multi-seller orders never leak or inflate other seller data.
  - `pending_order_count` & `completed_order_count`: Accurate counts based on real order lifecycle statuses.
  - `appointment_count` & `pending_appointment_count`: Consultations requested with this dentist, hydrated with patient details.
  - Fake business metrics (fake revenue, fake conversion rate, fake growth percentages) removed in favor of honest counts.
- **Frontend Architecture, Skeletons & i18n**:
  - `apps/web/lib/dashboard-api.ts`: Typed fetch helpers using `authorizedFetch` with automatic session refresh and cross-tab lock integration.
  - Skeletons and neutral loading states (`.skeletonPulse`, `.skeletonBlock`): Eliminates flash of zero counts or premature "Good Standing" while data resolves.
  - Clean error states with retry actions that preserve the user's session.
  - 100% key parity across `en.ts` and `ur.ts` for all oral wellness states, error messages, and dashboard labels.
- **Automated Validation**:
  - Pytest Suite: 26 passed, 0 failed across all portal security, session, patient dashboard (13 scenarios), and dentist dashboard (8 scenarios) tests.
  - TypeScript Check (`npx tsc --noEmit`): Exit code 0, 0 errors.
  - Next.js Production Build (`npm run build`): Exit code 0, 28/28 static/dynamic routes compiled.
  - Strict compliance: NO browser, dev server, localhost, or live testing performed by agent.

## Phase 11A Summary — Specialized YOLO Dental Pathology Perception Pipeline

- **Implementation Status**:
  - PHASE 11A IMPLEMENTED — PENDING NATHAN MANUAL ACCEPTANCE
- **Core Decoupling**:
  - YOLO11n handles local visual perception only.
  - Deterministic clinical rules in Diagnosis service handle triage and urgency.
  - Qwen in Orchestrator handles patient-friendly report text generation strictly from structured evidence (receives NO raw image).
- **Class Map (LOCKED)**:
  - `calculus` -> `tartar`
  - `caries` -> `cavity_suspect`
  - `gingivitis` -> `gingivitis_signs`
  - `tooth discoloration` -> `discoloration`
  - `ulcer` -> `oral_ulcer`
- **Safety & Discoloration Heuristic**:
  - Discoloration is NEVER mapped to calculus/tartar.
  - Spatial aggregation identifies generalized discoloration across the dentition to prevent yellow teeth from being reported as tartar buildup.
  - Concurrent calculus and discoloration are preserved as separate findings.
  - Discoloration limitation included: visual screening cannot determine the underlying cause of discoloration.
- **Oral Ulcer Finding**:
  - `ConditionLabel.ORAL_ULCER` ("Oral Ulcer") with cautious non-definitive wording: "Visible oral ulcer / sore".
  - Recommends dental evaluation if persistent beyond 10-14 days without claiming cancer or systemic disease.
- **Technical Safety**:
  - Missing weights or inference failure raises typed pipeline error — never fabricates healthy teeth.
  - Clean scans with no detections return non-definitive statement: "No supported visible pathology was detected by this screening model."
- **Model Path**:
  - Configured to `services/teeth_analyzer/models/oral_disease/best.pt` (`YOLO_DENTAL_MODEL_PATH`, gitignored).
- **Validation**:
  - Pytest Suite: 62 passed, 0 failed across all perception, triage, and legacy fallback tests.
  - Next.js Build: 28/28 routes compiled successfully.
  - Strict compliance: NO browser, dev server, localhost, live inference, or weight downloads performed by agent.

## Phase 11B-1 Summary — YOLO Detector Calibration + Hard-Negative Preparation

- **Implementation Status**:
  - PHASE 11B-1 IMPLEMENTED — CALIBRATION/HARD-NEGATIVE TOOLING READY, PENDING NATHAN DATA REVIEW AND V2 TRAINING
- **Dataset Audit Findings (`docs/evaluation/yolo_dataset_audit.md`)**:
  - Total Images: 10,698 across train (8,558), valid (1,070), test (1,070).
  - True Negative Images: 570 empty label files (5.33% of dataset). 94.7% of images contain disease boxes (18:1 imbalance).
  - Total Boxes: 62,720. Tooth discoloration dominates (26,424 boxes / 42.1%), explaining high false positive prior on clean teeth.
- **Class-Specific Threshold Architecture**:
  - Global fallback: `YOLO_DENTAL_CONFIDENCE_THRESHOLD=0.50`.
  - Class-specific overrides: `YOLO_CALCULUS_CONFIDENCE_THRESHOLD`, `YOLO_CARIES_CONFIDENCE_THRESHOLD`, `YOLO_GINGIVITIS_CONFIDENCE_THRESHOLD`, `YOLO_DISCOLORATION_CONFIDENCE_THRESHOLD`, `YOLO_ULCER_CONFIDENCE_THRESHOLD`.
  - Centralized resolver: `get_confidence_threshold(class_name)` accepts raw YOLO names or normalized clinical codes.
- **Diagnostic Spatial Metadata**:
  - `AggregatedFinding` enhanced with internal diagnostic metrics: `max_confidence`, `mean_confidence`, `horizontal_coverage`, `aggregate_area_ratio`, `image_third_coverage`.
  - Kept internal for evaluation; not leaked into patient UI.
- **Image Quality vs Detector Confidence Separation**:
  - Fixed bug where moderate detector confidence displayed "Low visual clarity".
  - Image quality alerts now derive ONLY from physical image quality (`overall_quality_score < 0.5` or `action_trigger == "REQUEST_CLEARER_PHOTO"`).
  - Detector confidence produces honest message: "Moderate screening confidence — professional confirmation is recommended."
- **Hard-Negative Pipeline & v2 Tooling**:
  - `scripts/audit_yolo_dataset.py`: High-speed dataset audit utility.
  - `scripts/evaluate_yolo_calibration.py`: Offline confidence threshold sweep (0.30–0.80) & confusion matrix tool.
  - `scripts/prepare_yolo_v2_dataset.py`: Merges original dataset with `dataset/hard-negatives/` into `dataset/oral-disease-v2.yolov11/` with 0-byte labels (80/10/10 deterministic split, zero mutation of original).
  - `scripts/compare_yolo_models.py`: Side-by-side evaluation harness comparing `best.pt` vs `best_v2.pt`.
- **Validation**:
  - Pytest Suite: 89 passed, 0 failed (including 13 new dedicated Phase 11B-1 calibration and hard-negative tests).
  - Next.js Build: 28/28 routes compiled successfully.
  - Strict compliance: Zero browser, dev server, localhost, live API calls, or model training executed.

## Phase 11B-2 Summary — Hard-Negative Mining + YOLO v2 Refinement Pipeline

- **Implementation Status**:
  - PHASE 11B-2 IMPLEMENTED — HARD-NEGATIVE MINING + V2 TRAINING PIPELINE READY, PENDING NATHAN MANUAL REVIEW AND MODAL TRAINING
- **Hard-Negative Mining on Empty-Label Images**:
  - `scripts/mine_yolo_hard_negatives.py` executed against all 457 empty-label training images in `dataset/oral-disease.yolov11/train/`.
  - Discovered 36 false-positive images producing 86 total false-positive boxes (47 tooth discoloration, 22 caries, 16 calculus, 1 ulcer).
  - 421/457 (92.1%) empty-label images had zero detections at confidence >= 0.30.
  - Generated `dataset/hard-negative-candidates/review.csv` (initialized to `UNREVIEWED`), `candidates.json`, and visual review contact sheets `contact_sheet_01.jpg` and `contact_sheet_02.jpg`.
- **v2 Dataset Strategy & Strict Leakage Protection**:
  - `scripts/prepare_yolo_v2_dataset.py`: Only Nathan-approved negatives (`review_status == 'ACCEPT_NEGATIVE'`) enter the `train` split.
  - Original `valid` and `test` benchmark splits are preserved 100% UNTOUCHED (zero leakage).
  - SHA-256 hash validation aborts loudly if any approved training negative matches a validation or test sample.
  - Controlled oversampling enabled via `--negative-repeat N` (default: 1, recommended: 2).
  - Original dataset `dataset/oral-disease.yolov11` is never mutated.
- **Modal v2 Fine-Tuning Infrastructure**:
  - `scripts/modal_train_yolo_v2.py`: Remote execution using the existing working Modal pattern.
  - Uploads `oral-disease-v2.zip` and base checkpoint `best.pt` (`/root/best_v1.pt`).
  - Fine-tunes starting from `/root/best_v1.pt` (NOT `yolo11n.pt`) with AdamW `lr0=0.0005`, 12 epochs, batch 16, A10G GPU, saving to `daantshaant-yolo-v2-output` volume.
- **Validation**:
  - Pytest Suite: 43 passed, 0 failed across all perception, calibration, and hard-negative mining tests (14 dedicated Phase 11B-2 tests).
  - Strict compliance: Zero browser, dev server, localhost, live API calls, or model training executed by agent.

## Phase 11B-3 Summary — Mine Healthy Hard Negatives from Roboflow Dataset

- **Implementation Status**:
  - PHASE 11B-3 IMPLEMENTED — CANDIDATES & CONTACT SHEETS GENERATED, MULTI-CSV MERGE READY, PENDING NATHAN REVIEW
- **Dataset Audit & Partitioning (`dataset/Dental Data Set.yolov11/`)**:
  - Total images: 427 across `train` (427 labels). Valid and test dirs absent from local export.
  - Class names (nc: 7): `['8', 'Calculus', 'CalculusCavities', 'CalculusHealthy Teeth', 'Cavities', 'Gingivitis', 'Healthy Teeth']`.
  - Healthy teeth candidate class: Class 6 (`Healthy Teeth`).
  - Healthy-only images: 15 images (all boxes correspond solely to Class 6).
  - Mixed images: 144 images (contain Class 6 + disease boxes — strictly excluded).
  - Disease-only images: 268 images (strictly excluded).
- **Detector Mining against `best.pt` ($\ge 0.30$)**:
  - Model false positives (`candidate_type = MODEL_FALSE_POSITIVE`): 9 images producing 56 false-positive boxes (54 tooth discoloration, 1 caries, 1 gingivitis).
  - Normal clean controls (`candidate_type = CLEAN_CONTROL`): 6 images producing 0 detections.
  - Internal candidate deduplication: 15 unique SHA-256 hashes (0 duplicates).
  - Benchmark isolation: 0 hash overlap with original benchmark `valid` and `test` splits.
- **Review Artifacts Generated**:
  - `dataset/healthy-negative-candidates/review.csv`: 15 candidate rows initialized to `UNREVIEWED` with full metadata and priority ranking.
  - `dataset/healthy-negative-candidates/candidates.json`: Full machine-readable candidate metadata.
  - `dataset/healthy-negative-candidates/contact_sheet_01.jpg`: 1440x1440 4x4 visual review grid with bounding boxes, confidences, and tile numbers.
- **Multi-CSV v2 Preparation Tooling**:
  - `scripts/prepare_yolo_v2_dataset.py` upgraded with UTF-8-BOM support, resilient candidate path resolution, and multiple review CSV support via repeated `--review-csv` CLI options.
  - Successfully dry-run verified merging both `dataset/review_ai_recommended.csv` (8 approved) and `dataset/healthy-negative-candidates/review.csv` (0 approved currently).
  - Enforces empty (0-byte) `.txt` labels in v2 `train` for all approved negatives.
  - Strict SHA-256 hash assertions protect benchmark `valid` and `test` splits from any data leakage.
- **Validation**:
  - Pytest Suite: 57 passed, 0 failed across all Phase 11 test suites (14 dedicated Phase 11B-3 tests).
  - Strict compliance: Zero browser, dev server, localhost, external API calls, or model training executed.

## Phase 11B-4 Summary — Large Healthy-Negative Mining + V2 Dataset Preparation

- **Implementation Status**:
  - PHASE 11B-4 IMPLEMENTED — FINAL LARGE HEALTHY POOL MINED, PENDING NATHAN AUDIT + V2 TRAINING
- **Dataset Audit & Partitioning (`dataset/Penyakit Gigi Skripsi.yolov11/`)**:
  - Total source images: 2,468 across `train` (1,974), `valid` (247), `test` (247).
  - Class names ($nc=3$): `['calculus', 'caries', 'healthy']` (IDs: calculus=0, caries=1, healthy=2).
  - Healthy-only images: 338 images (all boxes exclusively Class 2 `healthy`).
  - Mixed images: 1,342 images (healthy + disease — strictly excluded).
  - Disease-only images: 788 images (strictly excluded).
  - Empty-label images: 0.
  - License: CC BY 4.0; Roboflow project: `penyakit-gigi-skripsi-i77mi` (workspace: `nathan-asif-blm21`).
- **Comprehensive Detector Mining against `best.pt` ($\ge 0.30$)**:
  - Model false positives (`candidate_type = MODEL_FALSE_POSITIVE`): 129 images producing 934 false-positive boxes.
  - Dominant failure mode: Tooth discoloration accounts for 89.3% (834/934) of false-positive detections on healthy teeth (104 images). Secondary: gingivitis (21 images / 87 boxes), caries (4 images / 13 boxes), calculus (0), ulcer (0).
  - Clean normal controls (`candidate_type = CLEAN_CONTROL`): 209 images with 0 detections $\ge 0.30$.
  - Auto-eligible clean controls: 55 unique primary variants passing physical quality filters (`review_status = AUTO_ELIGIBLE_CONTROL`).
- **Cryptographic & Perceptual Deduplication**:
  - SHA-256: 338 unique hashes (0 exact duplicates).
  - 64-bit dHash: 233 near-duplicate image variants grouped into clusters. Only primary instances are eligible for automatic control status; near duplicates labeled `REJECT_NEAR_DUPLICATE`.
- **Physical Image Quality Filtering**:
  - Excluded 49 unusable images: 41 severe blur (Laplacian variance $< 2.5$), 8 extreme overexposure ($> 35\%$ pixels $> 250$).
- **Benchmark Leakage Protection**:
  - SHA-256 cross-check against original `oral-disease.yolov11` valid (1,070) and test (1,070) splits confirms 0 matches (ZERO leakage).
- **Review Artifacts Generated (`dataset/final-healthy-negative-candidates/`)**:
  - `review.csv`: 338 rows with full metadata, priority ranking, duplicate grouping, and quality scores.
  - `candidates.json`: Machine-readable metadata and full prediction records.
  - `audit.json`: Statistical audit summary.
  - `contact_sheet_fp_01.jpg` to `08.jpg`: 8 contact sheets displaying the top 120 false-positive candidates (16 tiles each, 4x4) ranked by clinical priority.
  - `contact_sheet_control_audit_01.jpg` to `04.jpg`: 4 contact sheets displaying a 50-image deterministic control audit sample (`seed=42`).
- **V2 Dataset Tooling (`scripts/prepare_yolo_v2_dataset.py`)**:
  - Added explicit `--include-audited-controls` CLI flag to opt-in `AUTO_ELIGIBLE_CONTROL` rows only after human audit.
  - Automatic class balance tracking: displays negative percentage of total v2 train set, alerts if $> 18\%$.
  - Large-pool repeat logic: recommends `repeat=1` if pool $\ge 500$, configurable if $< 200$.
- **Validation**:
  - Pytest Suite: 76 passed, 0 failed across all Phase 11 test suites (19 dedicated Phase 11B-4 tests).
  - Strict compliance: Zero browser, dev server, localhost, external API calls, or model training executed.

## Phase 11B Final Summary — YOLO Final Model Freeze Configuration

- **Implementation Status**:
  - PHASE 11B FINAL IMPLEMENTED — CONFIGURATION FROZEN, PENDING NATHAN MANUAL TWO-IMAGE ACCEPTANCE
- **Model Freezing Strategy**:
  - Selected runtime candidate: `services/teeth_analyzer/models/oral_disease/best_v2.pt`
  - Baseline retained (rollback checkpoint): `services/teeth_analyzer/models/oral_disease/best.pt` (V1 baseline physically preserved, never deleted or overwritten)
- **Configuration & Environment**:
  - Config key `YOLO_DENTAL_MODEL_PATH` set to `services/teeth_analyzer/models/oral_disease/best_v2.pt` in `.env` and documented in `.env.example`.
  - Lazy singleton YOLO loader (`get_yolo_model()` in `yolo_detector.py`) honors `YOLO_DENTAL_MODEL_PATH` and loads `best_v2.pt` upon service start/restart.
- **Calibrated Engineering Screening Thresholds**:
  - `YOLO_DENTAL_CONFIDENCE_THRESHOLD=0.50` (global fallback)
  - `YOLO_CALCULUS_CONFIDENCE_THRESHOLD=0.35` (`calculus` -> `tartar`)
  - `YOLO_CARIES_CONFIDENCE_THRESHOLD=0.55` (`caries` -> `cavity_suspect`)
  - `YOLO_GINGIVITIS_CONFIDENCE_THRESHOLD=0.50` (`gingivitis` -> `gingivitis_signs`)
  - `YOLO_DISCOLORATION_CONFIDENCE_THRESHOLD=0.65` (`tooth discoloration` -> `discoloration`)
  - `YOLO_ULCER_CONFIDENCE_THRESHOLD=0.65` (`ulcer` -> `oral_ulcer`)
  - Centralized resolver `get_confidence_threshold()` verifies raw and normalized labels map to exact values and unknown classes fall back to 0.50.
- **Medical Disclaimer**:
  - Calibrated cutoff values represent engineering screening thresholds chosen to balance sensitivity and false-positive suppression on intraoral screening photos. They do **not** constitute clinical validation claims or diagnostic guarantees.
- **Automated Validation**:
  - Pytest Suite: 102 passed, 0 failed across all Phase 11 calibration, pipeline, and mining test suites (including 31 dedicated calibration/pipeline/loader tests).
  - Strict compliance: Zero browser, dev server, localhost, external API calls, or model training executed.

## DentalTensor Vision v1.0 — Model Branding & Identity Freeze (COMPLETE)

- **Implementation Status**:
  - DENTALTENSOR BRANDING FREEZE COMPLETE — DEVELOPED BY NATHAN ASIF
- **Canonical Model Identity**:
  - Product / Model Family: `DentalTensor`
  - Full Model Name: `DentalTensor Vision`
  - Version: `1.0`
  - Display Version: `DentalTensor Vision v1.0`
  - Developer & Author: `Nathan Asif`
  - Model Type: YOLO11n-based oral pathology computer-vision detector
  - Origin: Conceived and engineered by Nathan Asif while leading and building DaantShaant for the Alibaba Cloud Bano Qabil Hackathon 2026.
  - Integration: DentalTensor is the standalone vision model; DaantShaant is the product integration consuming DentalTensor.
- **Production Checkpoint**:
  - Branded production weight: `services/teeth_analyzer/models/oral_disease/dentaltensor_nathan_asif_v1.pt`
  - Byte-for-byte verified copy of `best_v2.pt` (SHA-256: `42BF517DED4EB15EEBE6B5361EBF9E6AB21D8488098C4E3E4CCFE5912ECBBE27`).
  - Rollback checkpoints `best_v2.pt` and `best.pt` preserved on disk.
- **Runtime Model Path & Configuration**:
  - Config key `YOLO_DENTAL_MODEL_PATH=services/teeth_analyzer/models/oral_disease/dentaltensor_nathan_asif_v1.pt` set in `.env`, `.env.example`, and `Settings` default.
  - Central metadata attributes: `dentaltensor_model_name`, `dentaltensor_model_version`, `dentaltensor_model_display_name`, `dentaltensor_developer` in `Settings`.
- **Architectural Safety & Identity Separation**:
  - Internal Python and runtime identifiers (`services/teeth_analyzer/`, package name, imports, API routes, ports) strictly preserved without broad refactoring.
  - Medical/ML behavior untouched: thresholds, CLAHE fix, bounding-box logic, spatial aggregation, triage rules, and clinical wording are 100% unchanged.
- **Pipeline Architecture**:
  ```text
  DaantShaant Oral Scan
          ↓
  DentalTensor Vision v1.0
          ↓
  normalized evidence
          ↓
  deterministic triage
          ↓
  clinical report
  ```
- **Documentation**:
  - Comprehensive model card created at `docs/dentaltensor-model-card.md`.

## Phase 12A Final — DaantShaant Central Dentist Reconstruction & Complete Hugging Face Removal (COMPLETE)

- **Implementation Status**:
  - PHASE 12A IMPLEMENTED — DAANTSHAANT CENTRAL DENTIST RECONSTRUCTED, HUGGING FACE COMPLETELY REMOVED, LANGGRAPH + STRUCTURED RAG + QWEN + PATIENT CONTEXT READY.
- **Root Cause of Chat Latency Resolved**:
  - The historical 1–2 minute delay was caused by `EmbeddingService._load_model()` attempting to download and initialize `SentenceTransformer("all-MiniLM-L6-v2")` and running PyTorch CPU encoding on every message turn.
- **Complete Hugging Face & FAISS Removal**:
  - Deleted obsolete modules: `orchestrator/src/orchestrator/rag/` (`embeddings.py`, `vector_store.py`, `chunker.py`, `ingest.py`, `retrieval_service.py`), `orchestrator/src/orchestrator/rag_endpoints.py`, and `data/rag/faiss_index.*`.
  - Removed `sentence-transformers`, `faiss-cpu`, `PyPDF2`, `python-docx` from `orchestrator/pyproject.toml`.
  - Removed `RAG_EMBEDDING_MODEL` from `.env` and `.env.example`.
  - Cleaned `orchestrator/src/orchestrator/main.py` and `orchestrator/src/orchestrator/dentist_portal/routes_products.py`.
  - Verified zero Hugging Face or FAISS imports project-wide via AST tests (`test_no_huggingface.py`).
- **DaantShaant Central Dentist Subsystem (`orchestrator/src/orchestrator/central_dentist/`)**:
  - `nlp.py`: Ultra-fast deterministic NLP engine (<50ms, regex/tokenization/synonyms). Handles 13 clinical intents, entity extraction, temporal parsing, and fast-path identification with zero models or PyTorch runtime cost.
  - `retrieval.py`: Structured SQL RAG directly querying Supabase PostgreSQL repositories (`ScanRepository`, `AppointmentRepository`, `DentistRepository`) strictly scoped by authenticated `patient_id` UUID. Zero embeddings.
  - `knowledge.py`: Curated offline oral health guideline lookup based on keyword and finding keys.
  - `fast_path.py`: Direct response formatters answering factual questions (scan date, appointment date/time, confidence %, urgency level, greetings) immediately without calling Qwen or any LLM.
  - `prompts.py`: Central Dentist system persona, grounded clinical context builder, and anti-slop / plain text response cleaner.
  - `graph.py`: StateGraph pipeline connecting 10 deterministic nodes (`load_auth_context` -> `nlp_understanding` -> `plan_retrieval` -> `retrieve_patient_data` -> `retrieve_conversation_context` -> `retrieve_optional_knowledge` -> `build_grounded_context` -> `qwen_or_direct_answer` -> `validate_response` -> `persist_turn`).

## Phase 12B Final — Central Dentist Live Latency, Deadlock & Chat Request Lifecycle Fix (COMPLETE)

- **Implementation Status**:
  - PHASE 12B IMPLEMENTED — CENTRAL DENTIST LIVE LATENCY, DEADLOCK AND CHAT REQUEST LIFECYCLE FIXED, READY FOR MANUAL ACCEPTANCE.
- **Root Cause of Live Multi-Minute Hangs Identified**:
  - Live logs revealed `asyncpg.exceptions.ConnectionFailureError: (EAUTHTIMEOUT) timeout while waiting for message`.
  - SQLAlchemy's `create_async_engine` lacked low connection/socket timeouts in `connect_args`. In flaky network or slow TLS handshakes to Supabase, `asyncpg` defaulted to internal OS TCP socket timeouts (multiple minutes), freezing the event loop during auth user lookup or DB queries.
  - Redundant SQL history queries were being executed inside `graph.py` even when rows had already been fetched by `chat_service.py`.
- **Database Engine & Connection Timeout Configuration**:
  - Configured `PostgresSettings`: `db_pool_timeout_seconds=3.0`, `db_connect_timeout_seconds=3.0`, `db_command_timeout_seconds=3.0`.
  - Injected `connect_args={"timeout": 3.0, "command_timeout": 3.0, "server_settings": {"statement_timeout": "3000"}}` and `pool_timeout=3.0` into `create_async_engine`.
  - Single request-scoped `AsyncSession` reused across auth, retrieval, and persistence with fail-fast exception handling (HTTP 503 instead of hanging).
- **Hard Latency Budgets & Global Deadline**:
  - Bounded chat request pipeline to strict budgets in `config.py`:
    - Auth timeout: 2.0s
    - Structured retrieval timeout: 2.0s
    - Persistence timeout: 2.0s
    - Qwen AI Gateway timeout: 8.0s (cancels call without multi-minute retry chains)
    - Global chat request timeout: 12.0s (wrapped in `asyncio.timeout(12.0)` with safe session rollback and graceful fallback)
  - Grounded deterministic fallback activated when provider times out or fails: answers factual clinical queries from loaded scan/appointment records instead of spinning.
- **Request Trace IDs & Stage Telemetry**:
  - Generated `request_id` (e.g. `chat_7f92...`) for every message turn.
  - Granular telemetry emitted across all stages: `request_started`, `auth_done`, `nlp_done`, `retrieval_done`, `qwen_started`, `qwen_done`, `persistence_done`, `request_complete total_ms=...`.
- **Frontend Optimistic UX & Functional Stop Button (`apps/web`)**:
  - `ChatInterface.tsx` refactored with explicit request states: `idle`, `sending`, `stopped`, `error`.
  - Optimistic send: user message captured and appended immediately, input cleared immediately, auto-scroll to bottom, typing bubble spawned. Textarea remains editable for subsequent messages.
  - Functional Stop button (`⏹ Stop`) backed by `AbortController.abort()`: immediately cancels fetch, removes typing bubble, marks generation stopped, and recovers Send button.
  - Full `try / catch / finally` lifecycle cleanup guarantees loading state is never locked permanently.
  - Guarded against double submissions with `isSubmittingRef`.
- **Verification Results**:
  - Orchestrator tests: 380 passed, 1 skipped, 0 failed.
  - Performance & timeout tests: 5/5 passed in `test_phase12b_latency_and_timeouts.py`.
  - Teeth Analyzer tests: 108 passed, 0 failed.
  - Next.js Web App: Clean production build (28/28 routes compiled, 0 errors).
  - Zero Hugging Face / FAISS references. DentalTensor Vision v1.0 completely untouched.

## Final Chat Identity Cleanup — Public Conversational Identity Freeze (COMPLETE)

- **Public Conversational Identity**: `DaantShaant`
  - Chat header: `DaantShaant`
  - Visible assistant sender label: `DaantShaant`
  - User sender label: `YOU`
  - Greeting wording: "Hello! I'm DaantShaant. How can I help with your oral health, scan results, or appointments today?"
  - Urdu UI: Uses unified brand name `DaantShaant` for chat title and sender label rather than translating product name.
- **Internal Orchestration Architecture**:
  - `Central Dentist` / `central_dentist`
  - Architecture, LangGraph pipeline (`central_dentist_graph`), module paths (`central_dentist/`), and `[CENTRAL_DENTIST]` telemetry logging are 100% preserved.
- **Functional Integrity**:
  - No functional behavior changed. LangGraph, structured RAG, Qwen, NLP, patient retrieval, timeout logic, AbortController, Stop behavior, and request lifecycle remain identical and fast.

## Phase 12D Final — Urgent Auth & Session Resilience Fix (COMPLETE)

- **Implementation Status**:
  - PHASE 12D IMPLEMENTED — TRANSIENT DATABASE FAILURES NO LONGER CAUSE FALSE INVALID-CREDENTIAL ERRORS OR IMMEDIATE LOGOUTS.
- **Root Cause Verified**:
  - Cross-region TCP/TLS handshakes from local host to Supabase PostgreSQL pooler (`aws-0-ap-northeast-2.pooler.supabase.com:5432` in Seoul) take 6.2s–11.4s on initial connection creation or reconnect.
  - When connection timeouts were set to aggressive thresholds (2s-3s) or network experienced transient stalls, asyncpg raised `TimeoutError`.
  - `login_user` previously lacked exception handling for DB connectivity/timeouts, leaking unhandled `TimeoutError` into HTTP 500.
  - The login frontend caught generic errors and blindly mapped all failures (500, 503, network) to `auth.invalid_credentials` ("Invalid email or password."). Passwords and credentials were never the issue.
  - On page load / dashboard mount, `fetchPortalProfile` called `/portal/auth/me`. If a transient DB timeout occurred (503/500), `fetchPortalProfile` threw `new Error("Session expired")`, and `PortalDashboard` called `router.replace('/${role}/login')` ~5 seconds after login.
  - `/portal/auth/refresh` would fail or rotate tokens concurrently, and any failed refresh cleared local authenticated state even when caused by temporary 503 DB hiccups.
- **Engine & Pool Configuration**:
  - `PostgresSettings`: `db_pool_size=5`, `db_max_overflow=10`, `db_pool_recycle_seconds=300` (proactive 5-minute recycling before Supabase Supavisor pooler drops idle connections), `db_pool_timeout_seconds=15.0`, `db_connect_timeout_seconds=15.0`, `db_command_timeout_seconds=15.0`.
  - Single application engine with `pool_pre_ping=True` detecting stale pooled connections prior to checkout.
- **Transient DB Connect Single-Retry (`auth_utils.py`)**:
  - Implemented `execute_with_single_retry(operation, *, op_name, backoff_seconds=0.2)`:
    - Attempt 1: on transient connection/timeout/DBAPI/OperationalError, logs warning and waits 200ms.
    - Attempt 2: retries once. If failure persists, cleanly raises controlled `HTTPException(503, detail="Authentication service is temporarily unavailable. Please retry in a moment.")`.
    - Never retries wrong passwords, invalid JWTs, or revoked refresh tokens.
  - Integrated across: `login_user` (user lookup and session insertion), `rotate_refresh_token` (session lookup, user lookup, token rotation), `get_current_user`, and `get_user_profile`.
- **Clean Error Classification & Status Mapping**:
  - Wrong credentials / role mismatch / inactive user -> HTTP 401 ("Invalid email or password.").
  - Database temporarily unavailable (TimeoutError, asyncpg connection errors, SQLAlchemy OperationalError / DBAPIError) -> controlled HTTP 503 ("Authentication service is temporarily unavailable. Please retry in a moment.").
  - Unexpected server bugs -> HTTP 500.
- **Refresh & /auth/me Resilience**:
  - A single transient DB error during `/portal/auth/refresh` returns 503 and never deletes or revokes the client refresh cookie.
  - `/portal/auth/me` returns 503 on DB timeout instead of 401.
  - Frontend `refreshPortalSession`: on 503 or network error, logs warning and returns `null` while strictly preserving `activeUser` in memory and suppressing `REFRESH_FAILED` broadcasts. Only genuine 401 clears session.
  - Frontend `authorizedFetch`: single-refresh-per-request guard. On 401, attempts ONE refresh and retries with new token once (zero refresh loops). Simultaneous 401s deduplicated to a single in-flight refresh promise.
  - Frontend `fetchPortalProfile`: on 503, preserves and returns current authenticated user snapshot so user is never signed out on transient backend hiccups.
  - `PortalDashboard`: catches errors and only redirects to `/${role}/login` on genuine `SessionExpiredError` (never on 503 or network failure). Renders friendly retry UI if cold profile fetch encounters 503.
- **Login UI Error Mapping**:
  - `LoginPage.tsx` handles structured `AuthApiError`:
    - 401 -> `t("auth.invalid_credentials")` ("Invalid email or password.")
    - 503 -> `t("auth.service_unavailable")` ("Service is temporarily unavailable. Please try again in a moment.")
    - 500 / other -> `t("auth.server_error")` ("Unable to sign in right now. Please try again.")
  - 100% key parity across `en.ts` and `ur.ts`.
- **Observability Logging**:
  - Added concise sanitized telemetry: `[AUTH] login_attempt`, `[AUTH] login_db_timeout`, `[AUTH] login_invalid_credentials`, `[AUTH] login_success`, `[AUTH] refresh_success`, `[AUTH] refresh_invalid`, `[AUTH] refresh_db_unavailable`, `[AUTH] auth_me_db_unavailable`. Zero passwords, raw tokens, or cookies exposed.
- **Token TTL Verification**:
  - Access token TTL: 30 minutes (`access_token_expire_minutes: 30`).
  - Refresh token TTL: 7 days (`refresh_token_expire_days: 7`, 604800s cookie max-age).
  - Cookie attributes: `HttpOnly=True`, `Path=/`, `SameSite=lax`.
  - Verified no accidental 5-second TTL exists.
- **Validation**:
  - Backend resilience suite (`tests/test_auth_resilience.py`): 10 passed, 0 failed.
  - Auth & security suite (`tests/test_auth_security.py` + `tests/test_phase10_5_portal_security_and_ops.py`): 20 passed, 0 failed.
  - Frontend auth resilience suite (`apps/web/lib/__tests__/portal-auth-resilience.test.ts`): 6 passed, 0 failed.
  - Cross-tab auth suite (`apps/web/lib/__tests__/cross-tab-auth.test.ts`): 7 passed, 0 failed.
  - TypeScript typecheck (`npx tsc --noEmit`): Exit code 0, 0 errors.
  - Next.js production build (`npm run build`): 28/28 routes compiled successfully.

## Phase 12C — Qwen Live Latency & Provider Reliability Fix - ACTIVE

- **Root Cause of Live 15.0s Timeout**:
  - `QwenProvider` previously instantiated a fresh `httpx.AsyncClient` inside `generate_text()`, `generate_vision()`, and `generate_structured()` for every request turn, repeatedly paying connection overhead (DNS, TCP 3-way handshake, TLS 1.3 negotiation to Singapore Model Studio endpoint `*.ap-southeast-1.maas.aliyuncs.com` from local host).
  - Central Dentist system prompt was ~1,850 chars with duplicated safety/style bullet points, and `build_grounded_context` dumped empty placeholder sections (`Latest Scan: No scans on record yet.`, `Appointments: No appointments on record yet.`) even for general oral health questions.
  - Lack of a hard `asyncio.timeout` guard inside the provider client call, causing stalls when socket/transport hung.
  - Central Dentist previously lacked direct fast-paths for common hygiene queries (`brushing_guide`, `flossing_guide`) and defaulted to a generic robotic failure message (`"I am currently having trouble reaching the AI assistant service..."`) exposing internal architecture.
- **Provider HTTP Connection Reuse & Lifecycle**:
  - `QwenProvider` and `GeminiProvider` now maintain persistent `httpx.AsyncClient` instances initialized with pooled connection limits (`httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=30.0)`).
  - Implemented `async def aclose()` on `QwenProvider`, `GeminiProvider`, and `AIGateway`.
  - Added `close_ai_gateway()` in `ai/factory.py` wired into FastAPI `lifespan` in `orchestrator/src/orchestrator/main.py` ensuring clean shutdown and zero connection leaks.
- **Strict Latency & Timeout Budget Enforced**:
  - `QWEN_TIMEOUT_SECONDS`: Default 8.0s (`chat_qwen_timeout_seconds=8.0`).
  - Total Chat Request Timeout: Default 12.0s (`chat_request_timeout_seconds=12.0`).
  - Sub-task budgets: Auth 2.0s, Retrieval 2.0s, Persistence 2.0s.
  - Wrapped `QwenProvider` HTTP POST in `async with asyncio.timeout(self._timeout):` ensuring hard client cancellation if transport or server inference stalls.
- **Adaptive Fallback & Retry Strategy**:
  - `AIGateway` tracks primary provider elapsed time. If primary took $\ge 6.5\text{s}$ before failing, secondary (Gemini) fallback is skipped to avoid breaching the 12.0s ceiling.
  - When fallback is permitted, its timeout is bounded to the remaining budget: `min(timeout, max(2.0, 10.0 - elapsed_time))`.
  - Zero long retries or backoff chains on model generation timeouts; immediate handoff to deterministic fallback.
- **Prompt & Output Optimization**:
  - System prompt streamlined in `prompts.py`: stripped duplicate instructions, focused on core DaantShaant identity, grounding, screening vs diagnosis distinction, conciseness, and plain text.
  - `build_grounded_context` only includes patient clinical records if they actually exist, omitting empty placeholders for general hygiene queries.
  - Conversation context window capped at 4 turns (8 messages max).
  - Output token ceiling set to `max_tokens=300` in `graph.py` for interactive chat turns.
- **Direct Fast-Path & Knowledge Fallback Expansion**:
  - Common general hygiene queries (e.g., "How should I brush my teeth?", "How often should I floss?") recognized in `nlp.py` and routed to instant (<1ms) deterministic fast paths (`brushing_guide`, `flossing_guide`).
  - Safe, curated knowledge fallback dictionary for high-frequency oral health topics: brushing, flossing, mouthwash basics, checkup frequency, tooth sensitivity, gum bleeding, teeth staining, and bad breath.
  - Patient-record fallback: if Qwen times out on a patient-specific question, deterministic fallback uses structured scan findings or appointment status rather than a generic error.
  - Public error language completely cleaned: eradicated all robotic phrasing ("AI assistant service", "Qwen", "provider", "model unavailable"). Fallback returns natural, helpful text: `"I couldn't complete that answer just now. Please try again."`
- **Instrumentation & Telemetry**:
  - Added detailed timing breakdown: `client_ready_ms`, `time_to_headers_ms`, `parse_ms`, and `total_ms`.
  - Sanitized logging: `[QWEN][%s] request_started`, `prompt_chars=%d messages=%d approx_tokens=%d`, `request_success total_ms=...`, or `timeout total_ms=...`. Zero patient data or API keys logged.
- **Canonical Model Studio Endpoint Configuration**:
  - Canonical base URL: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
  - Canonical model: `qwen-plus` (OpenAI-compatible `/chat/completions`)
  - No conflicting duplicate environment variables.

## Next Phase / Manual Acceptance

Nathan manual live verification:
- Central Dentist chat: ask general hygiene questions ("How should I brush my teeth?", "What is the best way to brush my teeth?", "How often should I floss?") -> verify instant response or 3-8s completion without timeouts.
- Central Dentist chat: ask patient scan questions ("What did my last scan show?") -> verify grounded structured response.
- Verify logs output sanitized telemetry `[QWEN][chat_...] request_started` and `total_ms` without exposing secrets or patient prompts.





