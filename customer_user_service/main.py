"""Entry point for the Customer User Service.

Initialises the FastAPI application, registers middleware, and mounts
all routers.  The service exposes a health-check endpoint at ``/health``
and runs on ``0.0.0.0:8000``.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from shared import exceptions  # noqa: F401  (imported for re-use across the service)
from shared.logger import logger

from customer_user_service.routers import customers, users


app = FastAPI(title="Customer User Service")


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
