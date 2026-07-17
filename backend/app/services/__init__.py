"""Persistence services. Each function takes an explicit SQLAlchemy Session so
routes control the transaction boundary."""

from __future__ import annotations

from datetime import datetime


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
