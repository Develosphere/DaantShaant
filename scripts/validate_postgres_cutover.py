"""Safe, small validation of the configured Supabase PostgreSQL cutover."""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, text

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT / "orchestrator" / "src"))

from orchestrator.db.models import User  # noqa: E402
from orchestrator.db.session import async_session_factory, engine  # noqa: E402
from orchestrator.dentist_portal.auth import hash_password  # noqa: E402
from orchestrator.repositories import UserRepository  # noqa: E402

EXPECTED_TABLES = {
    "users",
    "auth_sessions",
    "patient_profiles",
    "dentists",
    "scans",
    "scan_findings",
    "clinical_reports",
    "conversations",
    "messages",
    "products",
    "product_recommendations",
    "orders",
    "dentist_recommendations",
    "appointment_requests",
    "commission_records",
}


async def validate() -> None:
    email = f"cutover-check-{uuid4()}@example.invalid"
    user_id = None
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT 1")) == 1
            table_result = await connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            actual_tables = set(table_result.scalars())
            missing = EXPECTED_TABLES - actual_tables
            assert not missing, f"Missing application tables: {sorted(missing)}"
        async with async_session_factory() as session:
            async with session.begin():
                user = await UserRepository(session).add(
                    User(
                        email=email,
                        password_hash=hash_password(str(uuid4())),
                        role="patient",
                    )
                )
                user_id = user.id
            loaded = await UserRepository(session).get(user_id)
            assert loaded and loaded.email == email
            async with session.begin():
                await session.execute(delete(User).where(User.id == user_id))
        print(
            "SUCCESS: 15 application tables verified; "
            "SELECT/create/read/delete validation completed."
        )
    finally:
        if user_id:
            async with async_session_factory() as cleanup:
                async with cleanup.begin():
                    await cleanup.execute(delete(User).where(User.id == user_id))
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(validate())
