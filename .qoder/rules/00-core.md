# Qoder Core Rules — DaantShaant

> These rules apply to every Qoder chat session on this repository.

---

## Startup

1. Read `/context.md` FIRST — this is current state, not history.
2. Read `/docs/phase-log.md` for chronological context.
3. Inspect ONLY files relevant to the current phase.
4. DO NOT recursively scan the repository.

---

## Phase Boundaries

5. One bounded phase per fresh chat.
6. Do not implement future phases.
7. Do not change unrelated working modules.
8. Do not rebuild existing working features unnecessarily.

---

## Implementation Truth

9. Current source code is implementation truth.
10. `/context.md` is current state (not a development diary).
11. `/docs/phase-log.md` is chronological history.
12. New PRD supersedes old plans.
13. Old PRDs are historical reference only.

---

## Token Optimization

14. Never scan the whole repo unless explicitly required.
15. Inspect only module-relevant files.
16. Prefer cheapest capable model for the task complexity.
17. Do not use Auto by default.
18. Do not use Performance/Ultimate/Experts by default.

---

## Security

19. Do not expose secrets (API keys, tokens, passwords).
20. Do not commit `.env` files.

---

## Quality

21. New third-party dependency or service must be documented in `docs/third-party-usage.md`.
22. Add focused tests for meaningful source changes.
23. Update `context.md` at phase completion.
24. Append to `docs/phase-log.md` at phase completion.

---

## Model Selection Guide

| Task Type | Recommended Model | Approximate Cost |
|-----------|------------------|-----------------|
| Documentation, config | Lite | 0.0x |
| Deterministic code changes | Qwen3.7-Plus | ~0.04x |
| Cross-module integration | Qwen3.8-Flash / Qwen3.7-Max | ~0.1x |
| Complex AI / graph / architecture | Qwen3.8-Max | ~0.25x |
