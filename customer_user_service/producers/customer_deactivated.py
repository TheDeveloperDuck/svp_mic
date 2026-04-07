"""Kafka producer for the customer.deactivated event.

Exposes a single public coroutine:

- ``publish_customer_deactivated`` -- serialise and send the event payload.
"""

import json
import os
import uuid
from datetime import UTC, datetime

from aiokafka import AIOKafkaProducer
from dotenv import load_dotenv

from shared.exceptions import OutboxPublishError
from shared.logger import logger


load_dotenv()

_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
_TOPIC: str = "customer.deactivated"


async def publish_customer_deactivated(customer_id: str) -> None:
    """Publish a customer.deactivated event to Kafka.

    Builds a JSON payload containing a unique event ID, event type,
    the deactivated customer's ID, and a UTC timestamp, then sends it
    to the ``customer.deactivated`` topic.

    Raises ``OutboxPublishError`` if the message cannot be delivered.

    Arguments:
    customer_id -- string UUID of the customer that was deactivated.
    """
    payload: dict = {
        "event_id": str(uuid.uuid4()),
        "event_type": "customer.deactivated",
        "customer_id": customer_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    producer = AIOKafkaProducer(bootstrap_servers=_BOOTSTRAP_SERVERS)
    try:
        await producer.start()
        await producer.send_and_wait(
            _TOPIC,
            json.dumps(payload).encode("utf-8"),
        )
        logger.info(
            "Published customer.deactivated event for customer %s.",
            customer_id,
        )
    except Exception as exc:
        logger.error(
            "Failed to publish customer.deactivated event for customer %s: %s",
            customer_id,
            exc,
        )
        raise OutboxPublishError(
            f"Failed to publish customer.deactivated for customer {customer_id}."
        ) from exc
    finally:
        await producer.stop()
