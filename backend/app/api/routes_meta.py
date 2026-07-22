"""Health, skill/tool catalogs and schema serving."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends

from ..agent import TOOL_SPECS, skill_specs
from ..agent.skills import skill_catalog
from ..config import get_settings
from ..schemas.api import SkillCatalogOut
from .deps import get_current_owner

router = APIRouter(prefix="/api", tags=["meta"])
_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "frontend" / "src" / "schemas" / "schemas.json"


@router.get("/health")
def health() -> dict:
    s = get_settings()
    return {"ok": True, "app": s.app_name, "version": s.version}


@router.get("/whoami")
def whoami(owner: str = Depends(get_current_owner)) -> dict:
    """Who the current (session/gate-authenticated) caller is. Behind the login
    gate on hosted deploys, so the extension's "Test connection" uses it to
    confirm integrated (cookie) auth is working; returns 401 via the gate when
    the session has lapsed."""
    s = get_settings()
    return {"ok": True, "owner": owner, "multiUser": s.multi_user}


@router.get("/skills")
def skills() -> dict:
    return {"skills": skill_specs()}


@router.get("/meta/skills", response_model=SkillCatalogOut)
def meta_skills() -> SkillCatalogOut:
    return SkillCatalogOut(skills=skill_catalog())


@router.get("/tools")
def tools() -> dict:
    return {"tools": [t.model_dump(by_alias=True) for t in TOOL_SPECS.values()]}


@router.get("/schema")
def schema() -> dict:
    if _SCHEMA_PATH.exists():
        return json.loads(_SCHEMA_PATH.read_text())
    from ..codegen import build_json_schema
    return build_json_schema()
