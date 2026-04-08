"""Transactional outbox poller for the Planning Service.

Exposes a single async function:
- run_outbox_poller -- poll unpublished outbox rows and publish them.
"""

import asyncio

from sqlalchemy import select

from planning_service.database import AsyncSessionLocal
from planning_service.models import Outbox
from planning_service.producers.plan_events import publish_event
from shared.exceptions import OutboxPublishError
from shared.logger import logger


_POLL_INTERVAL_SECONDS: int = 5


async def run_outbox_poller() -> None:
    """Poll the outbox table and publish pending events to Kafka.

    Runs indefinitely as a background task, waking every
    ``_POLL_INTERVAL_SECONDS`` seconds.  For each row where
    ``published`` is ``False``:

    - Calls ``publish_event`` with the row's ``event_type`` and
      ``payload``.
    - On success, sets ``published = True`` and commits the session.
    - On ``OutboxPublishError``, logs the failure and leaves the row
      unpublished so it can be retried on the next poll cycle.

    Raises ``asyncio.CancelledError`` cleanly on shutdown; all other
    unhandled exceptions are logged without terminating the loop.
    """
    logger.info(
        "Outbox poller started (interval=%ds).", _POLL_INTERVAL_SECONDS
    )

    while True:
        try:
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            await _process_pending_rows()
        except asyncio.CancelledError:
            logger.info("Outbox poller cancelled; shutting down cleanly.")
            raise
        except Exception as exc:
            logger.error("Outbox poller encountered an unexpected error: %s.", exc)


async def _process_pending_rows() -> None:
    """Query and publish all unpublished outbox rows in a single session.

    Opens a new ``AsyncSession``, fetches every row where
    ``published`` is ``False``, attempts to publish each one, and
    commits successful rows individually so that a single publish
    failure does not block the rest.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Outbox).where(Outbox.published.is_(False))
        )
        rows = list(result.scalars().all())

        if not rows:
            logger.debug("Outbox poller: no pending rows.")
            return

        logger.debug("Outbox poller: found %d pending row(s).", len(rows))

        for row in rows:
            try:
                await publish_event(row.event_type, row.payload)
                row.published = True
                await db.commit()
                logger.info(
                    "Outbox row %s marked published (event_type='%s').",
                    row.id,
                    row.event_type,
                )
            except OutboxPublishError as exc:
                logger.error(
                    "Outbox row %s publish failed; will retry: %s.",
                    row.id,
                    exc,
                )
