# DaantShaant

DaantShaant is an AI-assisted oral-health screening and care-navigation platform. It combines snapshot/upload/live dental scans, chat with persistent case memory, dental RAG, dentist discovery, appointments, and a dentist product marketplace.

DaantShaant is an awareness tool, not a licensed medical diagnosis system.

## Architecture

```text
Next.js 14
  -> FastAPI Orchestrator
      -> Teeth Analyzer (OpenCV + Gemini)
      -> Diagnosis service
      -> FAISS dental RAG
      -> Product + dentist LangGraphs
      -> SQLAlchemy async repositories
  -> Supabase PostgreSQL
```

Supabase PostgreSQL is the sole application database. Application CRUD uses SQLAlchemy 2 + asyncpg and schema migrations use Alembic.

## Identity and Authentication

- One canonical `users.id` UUID owns patient and dentist data.
- Argon2id password hashes.
- Short-lived access JWT held in browser memory.
- Opaque rotating refresh token in an HttpOnly cookie.
- Only refresh-token hashes are stored in `auth_sessions`.
- Public admin registration is absent.

## Quick Start

See [docs/GUIDE.md](docs/GUIDE.md) for full setup.

```powershell
cd orchestrator
uv sync --group dev
.\.venv\Scripts\python.exe -m alembic upgrade head

cd ..\apps\web
npm ci

cd ..\..
.\scripts\start-services.ps1
```

Required environment values include `DATABASE_URL`, `DATABASE_MIGRATION_URL`, and `JWT_SECRET`. Copy safe placeholders from `.env.example`; never commit a real `.env`.

## Validation

```powershell
.\orchestrator\.venv\Scripts\python.exe .\scripts\test_postgres_connection.py
.\orchestrator\.venv\Scripts\python.exe .\scripts\validate_postgres_cutover.py

cd orchestrator
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider

cd ..\apps\web
npm.cmd run build
```

## Current Roadmap

- Phase 0: complete
- Phase 1A PostgreSQL foundation: complete
- Phase 1B full PostgreSQL/identity/auth/domain cutover: complete
- Next: Phase 2A shared Qwen-primary AI gateway

See `context.md`, `prd.md`, and `docs/phase-log.md` for current engineering state.
