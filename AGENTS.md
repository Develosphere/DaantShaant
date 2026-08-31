# AGENTS.md — Qoder Agent Rules for DaantShaant

> These rules govern all Qoder chat sessions working on this repository.

---

## 1. Core Workflow Rules

1. **Read `/context.md` first.** Every chat starts by reading current state.
2. **Never scan the whole repo** unless explicitly required by the phase.
3. **Inspect only module-relevant files.** Minimize token usage.
4. **One bounded phase per fresh chat.** Do not bleed into the next phase.
5. **Do not implement future phases.** Stay within the current phase scope.
6. **Do not change unrelated working modules.** If it works and is not in scope, leave it alone.
7. **Current source code is implementation truth.** If docs disagree with code, code wins.
8. **New PRD supersedes old plans.** The active PRD is the authority.
9. **Do not rebuild existing working features unnecessarily.**

---

## 2. Model / Credit Strategy

Preferred Qoder model tiers (cheapest capable first):

| Tier | Model | Cost | When to use |
|------|-------|------|-------------|
| Documentation only | Lite | 0.0x | Phase 0, docs, config |
| Deterministic backend/frontend | Qwen3.7-Plus | ~0.04x | Routine code changes |
| Moderate integration | Qwen3.8-Flash / Qwen3.7-Max | ~0.1x | Cross-module changes |
| Complex AI / graph / refactor | Qwen3.8-Max | ~0.25x | Architecture, LangGraph, AI gateway |

**DO NOT default to:** Auto, Performance, Ultimate, or Experts.

Use a stronger model only when complexity demonstrably warrants it.

---

## 3. Documentation Rules

- **`/context.md`** = current state. Updated at each phase completion.
- **`/docs/phase-log.md`** = chronological history. Appended at each phase completion.
- **`/docs/architecture.md`** = current and target architecture reference.
- **`/docs/third-party-usage.md`** = technology inventory with CURRENT/TARGET/LEGACY labels.
- **New third-party dependency or service** must be documented in `third-party-usage.md`.

---

## 4. Code Quality Rules

- Add focused tests for meaningful source changes.
- Do not expose secrets (API keys, tokens, passwords).
- Do not commit `.env` files (already in `.gitignore`).
- Follow spec-driven development: OpenAPI specs in `specs/` are the contract source of truth.
- Shared schemas live in `packages/dantshaant_common/`.

---

## 5. Chat Strategy

Each implementation phase uses a NEW chat:

```
Fresh chat
  -> read context.md
  -> inspect relevant files only
  -> max 6-8 step plan
  -> execute immediately
  -> tests
  -> update context.md
  -> append to phase-log.md
  -> close chat
```

If a phase partially fails:
- DO NOT rerun the entire phase.
- Use: new chat + context.md + current Git diff + exact blocker + relevant files only.

---

## 6. Source of Truth Hierarchy

1. Current source code (implementation truth)
2. `/context.md` (compact current-state memory)
3. Active PRD (product/roadmap truth)
4. `docs/architecture.md` and API docs
5. `docs/phase-log.md` (chronological history)
6. Archived/old PRDs (historical reference only)

Old PRDs must never silently override the current plan.
