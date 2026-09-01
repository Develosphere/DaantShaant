# DaantShaant Run Guide

## Prerequisites

- Python 3.11+
- `uv`
- Node.js 20+
- A reachable Supabase PostgreSQL development database

No local document database is required.

## Configure

Copy `.env.example` to an untracked `.env` and configure at minimum:

```dotenv
DATABASE_URL=postgresql+asyncpg://...
DATABASE_MIGRATION_URL=postgresql+asyncpg://...
JWT_SECRET=...
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
AUTH_REFRESH_COOKIE_NAME=daantshaant_refresh
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_SAMESITE=lax
AUTH_COOKIE_PATH=/
```

Use a strong production secret and secure cookies under HTTPS. Optional `SUPABASE_*` variables are not used for normal CRUD.

## Install

```powershell
cd orchestrator
uv sync --group dev
cd ..\apps\web
npm ci
```

## Migrate and Validate PostgreSQL

```powershell
cd orchestrator
.\.venv\Scripts\python.exe -m alembic upgrade head
cd ..
.\orchestrator\.venv\Scripts\python.exe .\scripts\test_postgres_connection.py
.\orchestrator\.venv\Scripts\python.exe .\scripts\validate_postgres_cutover.py
```

The validation script creates and removes one temporary user and never prints credentials.

## Create an Admin

There is no public admin registration route. Create a development/admin account explicitly:

```powershell
.\orchestrator\.venv\Scripts\python.exe .\scripts\create_admin.py `
  --email admin@example.com --first-name Demo --last-name Admin
```

The password is requested without echo and stored only as an Argon2id hash.

## Run

Use the existing service launcher:

```powershell
.\scripts\start-services.ps1
```

Or run the services manually in separate terminals from their respective directories. Default ports are web `3000`, orchestrator `8000`, teeth analyzer `8001`, and diagnosis `8002`.

## Verify

- API docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health` (reports `postgresql`)
- Frontend: `http://localhost:3000`

Tests:

```powershell
cd orchestrator
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
$env:RUN_POSTGRES_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_postgres_cutover_integration.py

cd ..\apps\web
npm.cmd run build
```

## Troubleshooting

- Alembic requires `DATABASE_MIGRATION_URL` or `DATABASE_URL` in the repository-root `.env`.
- Runtime persistence requires `DATABASE_URL` using `postgresql://` or `postgresql+asyncpg://`.
- Authentication requires `JWT_SECRET`; there is no built-in default.
- If Supabase DNS briefly fails, rerun the connection script before changing credentials.
- Google font downloads may require network access during a clean Next.js production build.
- AI and map provider setup remains unchanged until their later migration phases.
