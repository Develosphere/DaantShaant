"""Alembic environment configuration for DaantShaant PostgreSQL migrations."""

from asyncio import run as _async_run
import os
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all models so Base.metadata is populated
from orchestrator.db.base import Base
from orchestrator.db.models import (  # noqa: F401 — ensure models are registered
    User, AuthSession, PatientProfile,
    Dentist,
    Scan, ScanFinding, ClinicalReport,
    Conversation, Message,
    Product, ProductRecommendation, Order,
    DentistRecommendation, AppointmentRequest, CommissionRecord,
)

# Alembic Config object
config = context.config


def _migration_url() -> str:
    """Load the migration URL from the repository environment safely."""
    repository_root = Path(__file__).resolve().parents[2]
    load_dotenv(repository_root / ".env", override=False)

    value = os.getenv("DATABASE_MIGRATION_URL") or os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError(
            "Database URL is not configured. Set DATABASE_MIGRATION_URL or "
            "DATABASE_URL in the repository-root .env or process environment."
        )

    if value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif not value.startswith("postgresql+asyncpg://"):
        raise RuntimeError(
            "Unsupported database URL scheme. Expected postgresql:// or "
            "postgresql+asyncpg://."
        )
    return value


# ConfigParser treats percent signs as interpolation markers. Doubling them only
# affects Alembic's in-memory configuration and preserves percent-encoded URL
# characters when get_main_option() reads the value back.
config.set_main_option("sqlalchemy.url", _migration_url().replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL scripts without connecting to the database.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with an active connection."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    _async_run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
