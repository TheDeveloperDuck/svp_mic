"""Entry point for the Planning Service.

Initialises the FastAPI application, registers middleware, and mounts
all routers.  The service exposes a health-check endpoint at ``/health``
and runs on ``0.0.0.0:8000``.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from shared import exceptions  # noqa: F401 (re-used across the service)
from shared.logger import logger

from planning_service.consumers.customer_events import (
    run_customer_events_consumer,
)
from planning_service.outbox.poller import run_outbox_poller
from planning_service.routers import plans


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown tasks.

    Starts the transactional outbox poller and the customer.deactivated
    Kafka consumer as background tasks on startup and cancels both
    cleanly on shutdown.

    Yields:
    None -- control is handed back to FastAPI while the app is running.
    """
    logger.info("Planning Service starting up.")
    poller_task = asyncio.create_task(run_outbox_poller())
    consumer_task = asyncio.create_task(run_customer_events_consumer())
    try:
        yield
    finally:
        for task in (poller_task, consumer_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("Planning Service shutting down.")


app = FastAPI(title="Planning Service", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", response_class=JSONResponse)
async def health_check() -> dict:
    """Return a simple liveness signal for the service.

    Return value:
    dict -- JSON object with a single ``status`` key set to ``"ok"``.
    """
    logger.debug("Health check called.")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(plans.router)


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "planning_service.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
