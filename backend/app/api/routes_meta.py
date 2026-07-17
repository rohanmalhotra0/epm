"""Health, skill/tool catalogs and schema serving."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from ..agent import TOOL_SPECS, skill_specs
from ..config import get_settings

router = APIRouter(prefix="/api", tags=["meta"])
_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "frontend" / "src" / "schemas" / "schemas.json"


@router.get("/health")
def health() -> dict:
    s = get_settings()
    return {"ok": True, "app": s.app_name, "version": s.version}


@router.get("/skills")
def skills() -> dict:
    return {"skills": skill_specs()}


@router.get("/tools")
def tools() -> dict:
    return {"tools": [t.model_dump(by_alias=True) for t in TOOL_SPECS.values()]}


@router.get("/schema")
def schema() -> dict:
    if _SCHEMA_PATH.exists():
        return json.loads(_SCHEMA_PATH.read_text())
    from ..codegen import build_json_schema
    return build_json_schema()
