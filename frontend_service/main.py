"""Entry point for the Frontend Service.

Initialises the FastAPI application, mounts static files, registers the
Jinja2 template engine, and wires up the pages router.  The service
exposes a health-check endpoint at ``/health`` and runs on
``0.0.0.0:8000``.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shared.logger import logger

from frontend_service.routers import pages


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown logging.

    Yields:
    None -- control is handed back to FastAPI while the app is running.
    """
    logger.info("Frontend Service starting up.")
    yield
    logger.info("Frontend Service shutting down.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="Frontend Service", lifespan=lifespan)

app.mount(
    "/static",
    StaticFiles(directory="frontend_service/static"),
    name="static",
)

templates = Jinja2Templates(directory="frontend_service/templates")

# Share the templates instance with the pages router.
pages.templates = templates

app.include_router(pages.router)


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
# Application entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "frontend_service.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
