"""Async database engine and session factory for the Customer User Service.

Reads the ``DATABASE_URL`` connection string from the environment (via a
``.env`` file) and exposes:

- ``engine`` -- the async SQLAlchemy engine.
- ``AsyncSessionLocal`` -- the async session factory.
- ``get_db`` -- a FastAPI dependency that yields a live ``AsyncSession``.
"""

import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.logger import logger


load_dotenv()

_DATABASE_URL: str = os.getenv("DATABASE_URL", "")

if not _DATABASE_URL:
    logger.warning(
        "DATABASE_URL is not set.  Database calls will fail at runtime."
    )

engine = create_async_engine(
    _DATABASE_URL,
    echo=False,
    future=True,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for use as a FastAPI dependency.

    Opens a new ``AsyncSession`` for each request and closes it when the
    request is complete.  Roll-back on unhandled exceptions is handled
    by the context manager.

    Yields:
    AsyncSession -- an active SQLAlchemy async session.
    """
    async with AsyncSessionLocal() as session:
        logger.debug("Database session opened.")
        try:
            yield session
        finally:
            logger.debug("Database session closed.")
