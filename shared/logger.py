"""Shared logger module for the SVP microservices system.

Provides a single, pre-configured logger instance that all services
can import and use.  The logger is async-compatible because it relies
only on Python's built-in ``logging`` module, which is safe to call
from both synchronous and asynchronous contexts without blocking.
"""

import logging


# Module-level format string: timestamp, severity level, and message
_LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(message)s"

# Date/time format used in the timestamp portion of each log record
_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# Name used to identify this logger across all services
_LOGGER_NAME: str = "svp"


def _build_logger() -> logging.Logger:
    """Create and configure the shared SVP logger.

    Returns a ``logging.Logger`` instance with a single
    ``StreamHandler`` that writes formatted records to *stderr*.
    The log level is set to ``DEBUG`` so every record is captured
    during development; raise it to ``WARNING`` or higher in
    production by changing ``_LOG_LEVEL`` below.

    Return value:
    logging.Logger -- the configured logger instance.
    """
    # Retrieve (or create) the named logger
    logger: logging.Logger = logging.getLogger(_LOGGER_NAME)

    # Set the minimum severity that this logger will process
    logger.setLevel(logging.DEBUG)  # DEBUG for development; raise later

    # Avoid adding duplicate handlers if the logger already exists
    if not logger.handlers:
        handler: logging.StreamHandler = logging.StreamHandler()
        formatter: logging.Formatter = logging.Formatter(
            fmt=_LOG_FORMAT,
            datefmt=_DATE_FORMAT,
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)

    return logger


# Single shared logger instance — import this in every service
logger: logging.Logger = _build_logger()
