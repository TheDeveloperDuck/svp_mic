"""Entry point for the Customer User Service.

Initialises the FastAPI application, registers middleware, and mounts
all routers.  The service exposes a health-check endpoint at ``/health``
and runs on ``0.0.0.0:8000``.

On startup the ``plan.confirmed`` Kafka consumer is started as an
``asyncio`` background task and cancelled cleanly on shutdown.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from shared import exceptions  # noqa: F401  (imported for re-use across the service)
from shared.logger import logger
from shared.tracing import extract_tracing_headers

from customer_user_service.consumers.plan_confirmed import consume_plan_confirmed
from customer_user_service.database import engine
from customer_user_service.models import Base
from customer_user_service.routers import customers, users


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown tasks.

    Starts the ``plan.confirmed`` Kafka consumer as a background task on
    startup and cancels it gracefully when the application shuts down.

    Yields:
    None -- control is handed back to FastAPI while the app is running.
    """
    logger.info("Creating database tables from SQLAlchemy models.")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready.")
    consumer_task = asyncio.create_task(consume_plan_confirmed())
    logger.info("plan.confirmed consumer background task created.")
    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
        logger.info("plan.confirmed consumer background task stopped.")


app = FastAPI(title="Customer User Service", lifespan=lifespan)


@app.middleware("http")
async def log_trace_id(request: Request, call_next):
    headers = extract_tracing_headers(request)
    if trace_id := headers.get("x-b3-traceid"):
        logger.info("trace_id=%s", trace_id)
    return await call_next(request)


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

app.include_router(customers.router)
app.include_router(users.router)


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "customer_user_service.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
