"""Authentication utility functions: resilient database retry and error handling."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError

logger = logging.getLogger(__name__)

T = TypeVar("T")

TRANSIENT_DB_ERRORS = (
    TimeoutError,
    asyncio.TimeoutError,
    OperationalError,
    DBAPIError,
    SQLAlchemyError,
    ConnectionError,
    OSError,
)


async def execute_with_single_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    op_name: str,
    backoff_seconds: float = 0.2,
) -> T:
    """Execute a critical auth DB read with at most ONE retry on transient connection failure.

    If the first attempt fails due to a transient DB error (e.g. timeout, handshake,
    or dropped connection), waits backoff_seconds and retries once.
    If the retry also fails, raises HTTPException(503).
    """
    try:
        return await operation()
    except TRANSIENT_DB_ERRORS as first_exc:
        logger.warning(
            "[AUTH] %s transient DB failure on attempt 1 (%s: %s), retrying in %dms...",
            op_name,
            type(first_exc).__name__,
            first_exc,
            int(backoff_seconds * 1000),
        )
        await asyncio.sleep(backoff_seconds)
        # Attempt to roll back the session if bound in closure, preventing PendingRollbackError
        try:
            if hasattr(operation, "__closure__") and operation.__closure__:
                for cell in operation.__closure__:
                    obj = cell.cell_contents
                    if hasattr(obj, "rollback") and callable(obj.rollback):
                        await obj.rollback()
                        break
                    elif hasattr(obj, "session") and hasattr(obj.session, "rollback"):
                        await obj.session.rollback()
                        break
        except Exception:
            pass
        try:
            return await operation()
        except TRANSIENT_DB_ERRORS as second_exc:
            logger.error(
                "[AUTH] %s failed after retry due to DB unavailable (%s: %s)",
                op_name,
                type(second_exc).__name__,
                second_exc,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service is temporarily unavailable. Please retry in a moment.",
            ) from second_exc
