"""Kafka event publisher for the Expense Service.

Exposes two async functions:
- publish_expense_submitted -- publish an ``expense.submitted`` event.
- publish_expense_decided   -- publish an ``expense.decided`` event.
"""

import json
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from aiokafka import AIOKafkaProducer
from dotenv import load_dotenv

from shared.exceptions import OutboxPublishError
from shared.logger import logger


load_dotenv()

_KAFKA_BOOTSTRAP_SERVERS: str = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
)


async def publish_expense_submitted(
    expense_id: UUID,
    rep_id: UUID,
    plan_id: UUID,
    amount: Decimal,
    category: str,
) -> None:
    """Publish an ``expense.submitted`` event to the matching Kafka topic.

    Builds the event payload and sends it to the ``expense.submitted``
    topic.  A new ``AIOKafkaProducer`` is created, used, and stopped
    for each call.

    Arguments:
    expense_id -- UUID of the submitted expense.
    rep_id     -- UUID of the submitting sales rep.
    plan_id    -- UUID of the associated day plan.
    amount     -- claimed amount; cast to string for JSON serialisation.
    category   -- expense category string.

    Raises:
    OutboxPublishError -- when the Kafka producer raises any exception
        during startup, send, or shutdown.
    """
    event_type: str = "expense.submitted"
    payload: dict = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "expense_id": str(expense_id),
        "rep_id": str(rep_id),
        "plan_id": str(plan_id),
        "amount": str(amount),
        "category": category,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await _publish(event_type, payload)


async def publish_expense_decided(
    expense_id: UUID,
    rep_id: UUID,
    decision: str,
    decided_by: UUID,
) -> None:
    """Publish an ``expense.decided`` event to the matching Kafka topic.

    Builds the event payload and sends it to the ``expense.decided``
    topic.  A new ``AIOKafkaProducer`` is created, used, and stopped
    for each call.

    Arguments:
    expense_id -- UUID of the decided expense.
    rep_id     -- UUID of the submitting sales rep.
    decision   -- outcome string; either ``"approved"`` or ``"rejected"``.
    decided_by -- UUID of the manager who made the decision.

    Raises:
    OutboxPublishError -- when the Kafka producer raises any exception
        during startup, send, or shutdown.
    """
    event_type: str = "expense.decided"
    payload: dict = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "expense_id": str(expense_id),
        "rep_id": str(rep_id),
        "decision": decision,
        "decided_by": str(decided_by),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await _publish(event_type, payload)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _publish(event_type: str, payload: dict) -> None:
    """Send a serialised event payload to the Kafka topic named by ``event_type``.

    Arguments:
    event_type -- the event type string; used as the Kafka topic name.
    payload    -- the event payload to serialise as JSON.

    Raises:
    OutboxPublishError -- when the Kafka producer raises any exception
        during startup, send, or shutdown.
    """
    topic: str = event_type
    producer = AIOKafkaProducer(bootstrap_servers=_KAFKA_BOOTSTRAP_SERVERS)
    try:
        await producer.start()
        encoded: bytes = json.dumps(payload).encode("utf-8")
        await producer.send_and_wait(topic, encoded)
        logger.info(
            "Published event '%s' to topic '%s'.", event_type, topic
        )
    except Exception as exc:
        logger.error(
            "Failed to publish event '%s' to topic '%s': %s.",
            event_type,
            topic,
            exc,
        )
        raise OutboxPublishError(
            f"Failed to publish event '{event_type}' to topic '{topic}': {exc}"
        ) from exc
    finally:
        await producer.stop()
