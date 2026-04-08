"""Kafka consumer for the expense.decided topic.

Listens for ``expense.decided`` events and logs the decision outcome.
No database action is taken; this module is the notification hook for
future use.

Exposes one public coroutine intended to run as a background task:

- run_expense_decisions_consumer -- start the consumer loop.
"""

import asyncio
import json
import os

from aiokafka import AIOKafkaConsumer
from dotenv import load_dotenv

from shared.logger import logger


load_dotenv()

_BOOTSTRAP_SERVERS: str = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
)
_GROUP_ID: str = os.getenv("KAFKA_GROUP_ID", "expense_service")
_CONSUME_TOPIC: str = "expense.decided"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _handle_expense_decided(data: dict) -> None:
    """Log the decision outcome for a received ``expense.decided`` event.

    Parses ``expense_id`` and ``decision`` from ``data`` and logs the
    outcome.  No database action is taken at this stage.

    Arguments:
    data -- deserialised event payload dict.
    """
    expense_id = data.get("expense_id")
    decision = data.get("decision")

    if not expense_id or not decision:
        logger.warning(
            "expense.decided event missing required fields; skipping. data=%r",
            data,
        )
        return

    logger.info(
        "expense.decided received: expense_id=%s decision=%s.",
        expense_id,
        decision,
    )


# ---------------------------------------------------------------------------
# Public consumer loop
# ---------------------------------------------------------------------------

async def run_expense_decisions_consumer() -> None:
    """Run the expense.decided consumer loop as a background task.

    Connects to Kafka using the bootstrap servers and group ID from
    the environment, then processes messages from the
    ``expense.decided`` topic until the task is cancelled.
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
        await consumer.start()
        logger.info(
            "expense.decided consumer started (group=%s).", _GROUP_ID
        )
        async for msg in consumer:
            try:
                data = json.loads(msg.value.decode("utf-8"))
                logger.debug(
                    "Received expense.decided message at offset %s.",
                    msg.offset,
                )
                await _handle_expense_decided(data)
            except Exception as exc:
                logger.error(
                    "Error processing expense.decided message"
                    " at offset %s: %s",
                    msg.offset,
                    exc,
                )
    except asyncio.CancelledError:
        logger.info("expense.decided consumer shutting down.")
    except Exception as exc:
        logger.error(
            "expense.decided consumer fatal error: %s.", exc
        )
        raise
    finally:
        await consumer.stop()
        logger.info("expense.decided consumer stopped.")
