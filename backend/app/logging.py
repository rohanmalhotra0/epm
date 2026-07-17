"""Structured logging with mandatory secret redaction.

Every rendered log event passes through the redaction processor so credentials
can never leak into logs (spec section 12).
"""

from __future__ import annotations

import logging
import sys

import structlog

from .security.redaction import redact_text, redact_value


def _redact_processor(_logger, _name, event_dict: dict) -> dict:
    for key, value in list(event_dict.items()):
        if key == "event" and isinstance(value, str):
            event_dict[key] = redact_text(value)
        else:
            event_dict[key] = redact_value(value)
    return event_dict


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=getattr(logging, level.upper(), logging.INFO))
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_processor,
    ]
    processors.append(
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper(), logging.INFO)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "epmwizard"):
    return structlog.get_logger(name)
