"""Global application settings.

Kept intentionally small and un-typed against the artifact codegen: these are
local UI preferences, not artifact schemas, so they use plain dict payloads.
Demo mode has been removed — the app only ever connects to a real Oracle EPM
tenant, so there are no demo-related settings here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .deps import get_db

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
def get_settings_endpoint(session: Session = Depends(get_db)) -> dict:
    return {}


@router.patch("/settings")
def update_settings_endpoint(body: dict, session: Session = Depends(get_db)) -> dict:
    # No user-configurable global settings at present. Accept and ignore any
    # payload so older clients don't error.
    return {}
