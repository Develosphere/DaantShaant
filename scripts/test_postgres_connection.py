"""Test PostgreSQL connection to Supabase.

Usage:
    python scripts/test_postgres_connection.py

This script:
1. Loads DATABASE_URL from environment or .env
2. Creates a PostgreSQL async engine
3. Executes SELECT 1
4. Reads PostgreSQL version
5. Reports SUCCESS / FAILURE with safe metadata only

NEVER prints database password or complete DATABASE_URL.
"""

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse


def _load_env() -> None:
    """Load .env from project root if present (no pydantic needed)."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value


async def test_connection() -> bool:
    """Test PostgreSQL connection and print safe diagnostics."""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text

        _load_env()

        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            print("FAILURE: DATABASE_URL is not configured.")
            print("Set DATABASE_URL in your .env file.")
            return False

        # Ensure async driver for runtime connection
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif not db_url.startswith("postgresql+"):
            print(f"FAILURE: Unsupported URL scheme: {db_url.split(':')[0]}")
            return False

        # Print safe connection info (mask password)
        parsed = urlparse(db_url)
        safe_host = f"{parsed.hostname}:{parsed.port or 5432}"
        safe_db = parsed.path.lstrip("/") if parsed.path else "(unknown)"
        print(f"Connecting to: {parsed.scheme}://{parsed.hostname}:**@{safe_host}/{safe_db}")

        engine = create_async_engine(db_url, echo=False)

        async with engine.connect() as conn:
            # Test basic connectivity
            result = await conn.execute(text("SELECT 1"))
            row = result.scalar()
            assert row == 1, f"Expected 1, got {row}"

            # Read PostgreSQL version
            version_result = await conn.execute(text("SELECT version()"))
            pg_version = version_result.scalar()

        await engine.dispose()

        print(f"PostgreSQL version: {pg_version}")
        print("SUCCESS: PostgreSQL connection established.")
        return True

    except Exception as e:
        print(f"FAILURE: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)
