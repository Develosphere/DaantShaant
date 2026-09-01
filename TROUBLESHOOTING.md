# DaantShaant Troubleshooting

## PostgreSQL connection fails

- Confirm `DATABASE_URL` is present in the repository-root `.env`.
- Use `postgresql://` or `postgresql+asyncpg://`.
- Run `scripts/test_postgres_connection.py` for safe host/version diagnostics.
- Supabase pooler DNS can fail transiently; retry connectivity before changing credentials.
- Never paste full connection URLs into logs or issues.

## Alembic fails

- Run Alembic from `orchestrator/`.
- Configure `DATABASE_MIGRATION_URL` (preferred) or `DATABASE_URL`.
- Run `.\.venv\Scripts\python.exe -m alembic current` and confirm head.
- Do not edit an already-applied migration; add a new revision.

## Authentication fails

- `JWT_SECRET` is required; the application has no insecure default.
- Confirm access JWTs are sent as Bearer tokens.
- Confirm the refresh cookie is allowed by browser CORS/cookie settings.
- Production HTTPS should use `AUTH_COOKIE_SECURE=true`.
- Disabled accounts intentionally receive a 403 response.

## Session disappears after reload

- The access token is intentionally memory-only.
- The frontend restores it through `POST /portal/auth/refresh` using the HttpOnly cookie.
- Check `credentials: include`, CORS origin, SameSite, domain, path, and HTTPS settings.

## Frontend build cannot download fonts

The existing Next.js font configuration downloads Google font assets during a clean production build. Allow outbound access for the build or use an existing build cache. Font redesign is outside the database phase.

## AI or maps fail

AI and map providers were preserved during the database cutover. Check the existing Gemini/OpenRouter/Google settings and service health. Their migrations belong to later phases.

## Tests

```powershell
cd orchestrator
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider

$env:RUN_POSTGRES_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_postgres_cutover_integration.py
```

The integration test uses a transaction and rolls back its data.
