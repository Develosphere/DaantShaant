# DaantShaant Setup Checklist

## Environment

- [ ] Python 3.11+ and `uv` installed
- [ ] Node.js 20+ installed
- [ ] Repository-root `.env` created from `.env.example`
- [ ] `DATABASE_URL` configured for SQLAlchemy runtime access
- [ ] `DATABASE_MIGRATION_URL` configured for Alembic
- [ ] Strong `JWT_SECRET` configured
- [ ] Existing AI/map keys configured as needed

## Database

- [ ] `.\orchestrator\.venv\Scripts\python.exe -m alembic upgrade head` succeeds from `orchestrator/`
- [ ] Alembic reports `002_domain_compatibility (head)` or a later revision
- [ ] `scripts/test_postgres_connection.py` succeeds
- [ ] `scripts/validate_postgres_cutover.py` succeeds and cleans up its test user

## Dependencies

- [ ] `uv sync --group dev` completed in `orchestrator/`
- [ ] `npm ci` completed in `apps/web/`
- [ ] Dental knowledge ingested if RAG data is not already present

## Auth

- [ ] Patient registration/login works
- [ ] Dentist registration/login works
- [ ] Refresh restores a session through the HttpOnly cookie
- [ ] Logout revokes the refresh session
- [ ] Admin created only with `scripts/create_admin.py`

## Verification

- [ ] Backend tests pass
- [ ] Opt-in Supabase transactional integration test passes
- [ ] Next.js production build passes
- [ ] `/health` reports PostgreSQL status
- [ ] Snapshot, upload, live scan, chat, products, recommendations, orders, and appointments smoke-tested
