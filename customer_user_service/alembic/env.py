"""Alembic migration environment for the Customer User Service.

Configures an async SQLAlchemy engine so that Alembic uses the same
async driver (``asyncpg``) as the rest of the service.  The database URL
is read from the ``.env`` file via ``python-dotenv`` and overrides the
placeholder value in ``alembic.ini``.

Only online mode is supported; offline (SQL-script) mode is not implemented
because all migrations are applied directly against a live PostgreSQL instance.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine

from customer_user_service.models import Base


# ---------------------------------------------------------------------------
# Alembic config object — gives access to values in alembic.ini.
# ---------------------------------------------------------------------------

load_dotenv()

_config = context.config

if _config.config_file_name is not None:
    fileConfig(_config.config_file_name)

# Override the placeholder URL in alembic.ini with the real value from .env.
_DATABASE_URL: str = os.getenv("DATABASE_URL", "")
_config.set_main_option("sqlalchemy.url", _DATABASE_URL)

# Feed the ORM metadata to Alembic so it can detect model changes.
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------

def _do_run_migrations(connection) -> None:
    """Configure the Alembic context and run pending migrations.

    Called inside ``run_sync`` so that the synchronous Alembic API can
    operate on an already-open async connection.

    Arguments:
    connection -- a synchronous-compatible DBAPI connection provided by
                  SQLAlchemy's ``run_sync`` bridge.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    """Create an async engine and drive migrations over it.

    Opens a single async connection, delegates to ``_do_run_migrations``
    via ``run_sync``, then disposes the engine cleanly.
    """
    engine = create_async_engine(_DATABASE_URL, echo=False, future=True)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_do_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    """Entry point for online migration mode.

    Runs the async migration coroutine synchronously so Alembic's
    command-line runner can invoke it without being async-aware.
    """
    asyncio.run(_run_async_migrations())


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

run_migrations_online()
