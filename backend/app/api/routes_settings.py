"""Global application settings (demo mode toggle, etc.).

Kept intentionally small and un-typed against the artifact codegen: these are
local UI preferences, not artifact schemas, so they use plain dict payloads.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..connector.factory import get_registry
from ..db.models import EnvironmentProfile, Project
from ..services import environments as env_svc
from ..services import settings_svc as svc
from .deps import get_db

router = APIRouter(prefix="/api", tags=["settings"])

DEMO_ENABLED_KEY = "demo_enabled"


def _demo_enabled(session: Session) -> bool:
    return bool(svc.get_setting(session, DEMO_ENABLED_KEY, default=False))


def _ensure_demo_environment(session: Session) -> None:
    """Create a local demo environment in the default project if none exists."""
    project = session.query(Project).filter_by(is_default=True).first()
    if project is None:
        project = session.query(Project).order_by(Project.created_at.asc()).first()
    if project is None:
        return
    existing = (
        session.query(EnvironmentProfile)
        .filter_by(project_id=project.id, demo=True)
        .first()
    )
    if existing is None:
        env_svc.create_environment(
            session,
            project.id,
            name="MCW Demo (Local)",
            base_url=None,
            username="demo",
            auth_method="demo",
            classification="development",
            preferred_application="MCWPCF",
            demo=True,
        )


@router.get("/settings")
def get_settings_endpoint(session: Session = Depends(get_db)) -> dict:
    return {"demoEnabled": _demo_enabled(session)}


@router.patch("/settings")
def update_settings_endpoint(body: dict, session: Session = Depends(get_db)) -> dict:
    if "demoEnabled" in (body or {}):
        enabled = bool(body["demoEnabled"])
        svc.set_setting(session, DEMO_ENABLED_KEY, enabled)
        if enabled:
            _ensure_demo_environment(session)
        else:
            # Drop any live demo connections so the app can't stay in demo mode.
            registry = get_registry()
            for env in session.query(EnvironmentProfile).filter_by(demo=True).all():
                registry.disconnect(env.id)
    return {"demoEnabled": _demo_enabled(session)}
