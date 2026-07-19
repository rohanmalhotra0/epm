"""Structured logging with mandatory secret redaction.

Every rendered log event passes through the redaction processor so credentials
can never leak into logs (spec section 12). A bounded in-memory ring buffer
additionally captures the most recent (already redacted) events for the
diagnostics API — nothing is ever persisted to disk.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections import deque
from datetime import UTC, datetime

import structlog

from .security.redaction import redact_mapping, redact_text, redact_value

# --- In-memory ring buffer of recent log events (diagnostics, spec section 41)

LOG_BUFFER_SIZE = 500
_RESERVED_KEYS = {"timestamp", "level", "event", "logger_name"}

_log_buffer: deque[dict] = deque(maxlen=LOG_BUFFER_SIZE)
_buffer_lock = threading.Lock()


def _record(entry: dict) -> None:
    with _buffer_lock:
        _log_buffer.append(entry)


def recent_logs(limit: int = 200) -> list[dict]:
    """The most recent captured log entries, newest first."""
    limit = max(1, min(limit, LOG_BUFFER_SIZE))
    with _buffer_lock:
        entries = list(_log_buffer)
    return list(reversed(entries))[:limit]


def clear_log_buffer() -> None:
    with _buffer_lock:
        _log_buffer.clear()


def _jsonable(value):  # noqa: ANN001
    """Coerce arbitrary log values into JSON-safe structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return str(value)


def _buffer_processor(_logger, _name, event_dict: dict) -> dict:
    """Capture each (already redacted) structlog event into the ring buffer."""
    event = event_dict.get("event")
    _record({
        "ts": event_dict.get("timestamp"),
        "level": event_dict.get("level"),
        "event": str(event) if event is not None else None,
        "logger": event_dict.get("logger_name"),
        # key-aware redaction on top of the pattern-based redaction processor,
        # so a top-level password=... kwarg can never surface via the API
        "data": redact_mapping({k: _jsonable(v) for k, v in event_dict.items() if k not in _RESERVED_KEYS}),
    })
    return event_dict


class _BufferHandler(logging.Handler):
    """Mirror stdlib logging records (uvicorn, libraries) into the ring buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = redact_text(record.getMessage())
        except Exception:  # pragma: no cover - defensive: never break logging
            message = "<unformattable log record>"
        _record({
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "event": message,
            "logger": record.name,
            "data": {},
        })


def _redact_processor(_logger, _name, event_dict: dict) -> dict:
    for key, value in list(event_dict.items()):
        if key == "event" and isinstance(value, str):
            event_dict[key] = redact_text(value)
        else:
            event_dict[key] = redact_value(value)
    return event_dict


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=getattr(logging, level.upper(), logging.INFO))
    root = logging.getLogger()
    if not any(isinstance(h, _BufferHandler) for h in root.handlers):
        root.addHandler(_BufferHandler())
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_processor,
        _buffer_processor,
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
    # ``logger_name`` is bound so the diagnostics ring buffer can attribute
    # each event to its source logger ("logger" is reserved by structlog).
    return structlog.get_logger(name, logger_name=name)
