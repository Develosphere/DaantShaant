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
