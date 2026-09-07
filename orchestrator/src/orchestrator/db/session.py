"""Async SQLAlchemy engine, session factory, and FastAPI dependency."""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from orchestrator.config import settings

# Build async engine from DATABASE_URL.
# The URL should use the asyncpg driver, e.g.:
#   postgresql+asyncpg://user:password@host:5432/dbname
runtime_url = settings.get_runtime_url()
connect_args: dict[str, Any] = {}
if "asyncpg" in runtime_url:
    connect_args = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "timeout": settings.db_connect_timeout_seconds,
        "command_timeout": settings.db_command_timeout_seconds,
    }

engine = create_async_engine(
    runtime_url,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=settings.db_pool_recycle_seconds,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout_seconds,
    connect_args=connect_args,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
