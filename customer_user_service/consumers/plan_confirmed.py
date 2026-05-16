"""Kafka consumer for the plan.confirmed topic.

Listens for ``plan.confirmed`` events and validates that every customer
referenced in the plan is still active.  If any customer has been
deactivated, a ``plan.rolled_back`` event is published to Kafka.

Exposes one public coroutine intended to run as a background task:

- ``consume_plan_confirmed`` -- start the consumer loop; runs until cancelled.
"""

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from dotenv import load_dotenv
from sqlalchemy import select

from customer_user_service.database import AsyncSessionLocal
from customer_user_service.models import Customer
from shared.exceptions import OutboxPublishError
from shared.logger import logger


load_dotenv()

_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
_GROUP_ID: str = os.getenv("KAFKA_GROUP_ID", "customer_user_service")
_CONSUME_TOPIC: str = "plan.confirmed"
_ROLLBACK_TOPIC: str = "plan.rolled_back"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _publish_plan_rolled_back(plan_id: str, reason: str) -> None:
    """Publish a plan.rolled_back event to Kafka.

    Raises ``OutboxPublishError`` if the message cannot be delivered.

    Arguments:
    plan_id -- string identifier of the plan being rolled back.
    reason  -- human-readable explanation for the rollback.
    """
    payload: dict = {
        "event_id": str(uuid.uuid4()),
        "event_type": "plan.rolled_back",
        "plan_id": plan_id,
        "reason": reason,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    producer = AIOKafkaProducer(bootstrap_servers=_BOOTSTRAP_SERVERS)
    try:
        await producer.start()
        await producer.send_and_wait(
            _ROLLBACK_TOPIC,
            json.dumps(payload).encode("utf-8"),
        )
        logger.info(
            "Published plan.rolled_back event for plan %s. Reason: %s",
            plan_id,
            reason,
        )
    except Exception as exc:
        logger.error(
            "Failed to publish plan.rolled_back event for plan %s: %s",
            plan_id,
            exc,
        )
        raise OutboxPublishError(
            f"Failed to publish plan.rolled_back for plan {plan_id}."
        ) from exc
    finally:
        await producer.stop()


async def _handle_plan_confirmed(data: dict) -> None:
    """Process a single plan.confirmed event payload.

    Queries the database for each customer ID in the event.  If any
    customer is deactivated, publishes a ``plan.rolled_back`` event.
    If all customers are active, logs a confirmation and returns.

    Arguments:
    data -- deserialised event payload dict.
    """
    plan_id: str = data.get("plan_id", "unknown")
    customer_ids: list = data.get("customer_ids", [])

    deactivated: list[str] = []

    async with AsyncSessionLocal() as session:
        for customer_id in customer_ids:
            try:
                cid = uuid.UUID(customer_id)
            except (ValueError, AttributeError):
                logger.warning(
                    "plan.confirmed event for plan %s contains invalid "
                    "customer_id %r; skipping.",
                    plan_id,
                    customer_id,
                )
                continue

            result = await session.execute(
                select(Customer).where(Customer.id == cid)
            )
            customer = result.scalar_one_or_none()

            if customer is None:
                logger.warning(
                    "plan.confirmed event for plan %s references unknown "
                    "customer %s; skipping.",
                    plan_id,
                    customer_id,
                )
                continue

            if not customer.is_active:
                deactivated.append(customer_id)
                logger.warning(
                    "Customer %s is deactivated; plan %s will be rolled back.",
                    customer_id,
                    plan_id,
                )

    if deactivated:
        reason = (
            f"Plan {plan_id} rolled back: deactivated customer(s): "
            + ", ".join(deactivated)
        )
        try:
            await _publish_plan_rolled_back(plan_id, reason)
        except OutboxPublishError:
            logger.error(
                "Could not publish plan.rolled_back for plan %s.", plan_id
            )
    else:
        logger.info(
            "plan.confirmed event for plan %s: all %d customer(s) are active.",
            plan_id,
            len(customer_ids),
        )


# ---------------------------------------------------------------------------
# Public consumer loop
# ---------------------------------------------------------------------------

async def consume_plan_confirmed() -> None:
    """Run the plan.confirmed consumer loop as a background task.

    Connects to Kafka using the bootstrap servers and group ID from the
    environment, then processes messages from the ``plan.confirmed`` topic
    until the task is cancelled.  Exceptions raised by individual messages
    are caught and logged so the loop continues running.
    """
    while True:
        consumer = AIOKafkaConsumer(
            _CONSUME_TOPIC,
            bootstrap_servers=_BOOTSTRAP_SERVERS,
            group_id=_GROUP_ID,
            auto_offset_reset="earliest",
        )
        try:
            await consumer.start()
            logger.info(
                "plan.confirmed consumer started (group=%s, topic=%s).",
                _GROUP_ID,
                _CONSUME_TOPIC,
            )
            async for msg in consumer:
                try:
                    data = json.loads(msg.value.decode("utf-8"))
                    logger.debug(
                        "Received plan.confirmed message at offset %s.",
                        msg.offset,
                    )
                    await _handle_plan_confirmed(data)
                except Exception as exc:
                    logger.error(
                        "Error processing plan.confirmed message"
                        " at offset %s: %s",
                        msg.offset,
                        exc,
                    )
        except asyncio.CancelledError:
            logger.info("plan.confirmed consumer shutting down.")
            await consumer.stop()
            return
        except Exception as exc:
            logger.warning(
                "plan.confirmed consumer connection failed, retrying in 5s: %s",
                exc,
            )
            await consumer.stop()
            await asyncio.sleep(5)
        else:
            await consumer.stop()
            logger.info("plan.confirmed consumer stopped.")
