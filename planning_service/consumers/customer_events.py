"""Kafka consumer for the customer.deactivated topic.

Listens for ``customer.deactivated`` events and rolls back any
confirmed or active plans that reference the deactivated customer.
Plans are reverted to ``draft`` and a ``plan.rolled_back`` outbox
event is written within the same transaction.

Exposes one public coroutine intended to run as a background task:

- run_customer_events_consumer -- start the consumer loop.
"""

import asyncio
import json
import os
import uuid

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError
from dotenv import load_dotenv
from sqlalchemy import select

from planning_service.database import AsyncSessionLocal
from planning_service.models import (
    Call,
    DayPlan,
    DayPlanStatus,
    Outbox,
    Visit,
)
from shared.logger import logger


load_dotenv()

_BOOTSTRAP_SERVERS: str = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
)
_GROUP_ID: str = "planning_service"
_CONSUME_TOPIC: str = "customer.deactivated"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _handle_customer_deactivated(data: dict) -> None:
    """Roll back confirmed and active plans for a deactivated customer.

    Parses ``customer_id`` from ``data``, fetches every confirmed or
    active plan that references that customer in its visits or calls,
    transitions each to ``draft``, writes a ``plan.rolled_back``
    outbox row per plan, and commits everything in one transaction.

    Arguments:
    data -- deserialised event payload dict.
    """
    customer_id_raw = data.get("customer_id")
    if not customer_id_raw:
        logger.warning(
            "customer.deactivated event missing customer_id; skipping."
        )
        return

    try:
        customer_id = uuid.UUID(str(customer_id_raw))
    except (ValueError, AttributeError):
        logger.warning(
            "customer.deactivated has invalid customer_id %r; skipping.",
            customer_id_raw,
        )
        return

    async with AsyncSessionLocal() as db:
        visit_pids = await db.execute(
            select(Visit.plan_id).where(
                Visit.customer_id == customer_id
            )
        )
        call_pids = await db.execute(
            select(Call.plan_id).where(
                Call.customer_id == customer_id
            )
        )
        affected_ids = (
            set(visit_pids.scalars().all())
            | set(call_pids.scalars().all())
        )

        if not affected_ids:
            logger.info(
                "No plans found for deactivated customer %s.",
                customer_id,
            )
            return

        plans_result = await db.execute(
            select(DayPlan).where(
                DayPlan.id.in_(affected_ids),
                DayPlan.status.in_([
                    DayPlanStatus.confirmed,
                    DayPlanStatus.active,
                ]),
            )
        )
        plans = list(plans_result.scalars().all())

        if not plans:
            logger.info(
                "No confirmed/active plans to roll back for customer %s.",
                customer_id,
            )
            return

        for plan in plans:
            plan.status = DayPlanStatus.draft
            db.add(Outbox(
                event_type="plan.rolled_back",
                aggregate_id=plan.id,
                payload={
                    "plan_id": str(plan.id),
                    "customer_id": str(customer_id),
                },
            ))
            logger.debug(
                "Queued rollback for plan %s (customer %s).",
                plan.id,
                customer_id,
            )

        await db.commit()
        logger.info(
            "Rolled back %d plan(s) for deactivated customer %s.",
            len(plans),
            customer_id,
        )


# ---------------------------------------------------------------------------
# Public consumer loop
# ---------------------------------------------------------------------------

async def run_customer_events_consumer() -> None:
    """Run the customer.deactivated consumer loop as a background task.

    Connects to Kafka using the bootstrap servers and group ID from
    the environment, then processes messages from the
    ``customer.deactivated`` topic until the task is cancelled.
    Exceptions raised by individual messages are caught and logged
    so the loop continues running.
    """
    consumer = AIOKafkaConsumer(
        _CONSUME_TOPIC,
        bootstrap_servers=_BOOTSTRAP_SERVERS,
        group_id=_GROUP_ID,
        auto_offset_reset="earliest",
    )
    try:
        while True:
            try:
                await consumer.start()
                break
            except KafkaConnectionError as exc:
                logger.warning(
                    "customer.deactivated consumer connection failed,"
                    " retrying in 5s: %s",
                    exc,
                )
                await asyncio.sleep(5)
            except Exception as exc:
                logger.error(
                    "customer.deactivated consumer failed to start,"
                    " retrying in 5s: %s",
                    exc,
                )
                await asyncio.sleep(5)

        logger.info(
            "customer.deactivated consumer started (group=%s).",
            _GROUP_ID,
        )
        async for msg in consumer:
            try:
                data = json.loads(msg.value.decode("utf-8"))
                logger.debug(
                    "Received customer.deactivated message at offset %s.",
                    msg.offset,
                )
                await _handle_customer_deactivated(data)
            except Exception as exc:
                logger.error(
                    "Error processing customer.deactivated message"
                    " at offset %s: %s",
                    msg.offset,
                    exc,
                )
    except asyncio.CancelledError:
        logger.info("customer.deactivated consumer shutting down.")
    finally:
        await consumer.stop()
        logger.info("customer.deactivated consumer stopped.")
