"""Structlog configuration for the FinOps agent.

Produces JSON logs on Lambda / production and colourised console output when
running locally (detected via IS_LOCAL or LOG_LEVEL env vars).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import cast

import structlog
from structlog.stdlib import BoundLogger

__all__ = ["get_logger"]

_configured = False


def _configure() -> None:
    """One-time structlog setup; idempotent across repeated imports."""
    global _configured  # noqa: PLW0603
    if _configured:
        return

    is_local: bool = os.getenv("IS_LOCAL", "").lower() in ("1", "true", "yes")
    log_level_name: str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level: int = getattr(logging, log_level_name, logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if is_local:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Silence noisy third-party loggers that use stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    _configured = True


def get_logger(name: str) -> BoundLogger:
    """Return a structlog bound logger for the given name.

    Args:
        name: Logger name, typically the module ``__name__``.

    Returns:
        A structlog BoundLogger pre-bound with the given name.
    """
    _configure()
    return cast(BoundLogger, structlog.get_logger(name))
