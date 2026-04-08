"""Kafka event publisher for the Planning Service.

Exposes a single async function:
- publish_event -- send a plan domain event to the appropriate
  Kafka topic.
"""

import json
import os

from aiokafka import AIOKafkaProducer
from dotenv import load_dotenv

from shared.exceptions import OutboxPublishError
from shared.logger import logger


load_dotenv()

_KAFKA_BOOTSTRAP_SERVERS: str = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
)

_VALID_TOPICS: frozenset[str] = frozenset(
    {"plan.confirmed", "plan.rolled_back"}
)


async def publish_event(event_type: str, payload: dict) -> None:
    """Publish a plan domain event to the matching Kafka topic.

    The ``event_type`` string is used directly as the topic name.
    A new ``AIOKafkaProducer`` is created, used, and stopped for
    each call.

    Arguments:
    event_type -- the event type string; must be one of
                  ``plan.confirmed`` or ``plan.rolled_back``.
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
