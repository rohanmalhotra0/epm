"""Oracle environment routes (spec section 13)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..connector.errors import ConnectorError
from ..connector.factory import get_registry
from ..schemas.api import ConnectionResult, EnvironmentCreate, EnvironmentOut
from ..security.redaction import register_secret
from ..services import environments as svc
from ..services import projects as projects_svc
from .deps import get_db

router = APIRouter(tags=["environments"])


@router.get("/api/projects/{project_id}/environments", response_model=list[EnvironmentOut])
def list_environments(project_id: str, session: Session = Depends(get_db)) -> list[EnvironmentOut]:
    reg = get_registry()
    return [svc.to_out(e, connected=reg.is_connected(e.id)) for e in svc.list_environments(session, project_id)]


@router.post("/api/projects/{project_id}/environments", response_model=EnvironmentOut, status_code=201)
def create_environment(project_id: str, body: EnvironmentCreate, session: Session = Depends(get_db)) -> EnvironmentOut:
    env = svc.create_environment(session, project_id, name=body.name, base_url=body.base_url,
                                 username=body.username, auth_method=body.auth_method,
                                 classification=body.classification.value if hasattr(body.classification, "value") else body.classification,
                                 preferred_application=body.preferred_application, demo=body.demo)
    return svc.to_out(env)


@router.delete("/api/environments/{environment_id}", status_code=204)
def delete_environment(environment_id: str, session: Session = Depends(get_db)) -> None:
    get_registry().disconnect(environment_id)
    svc.delete_environment(session, environment_id)


@router.post("/api/environments/{environment_id}/connect", response_model=ConnectionResult)
async def connect_environment(environment_id: str, body: dict, session: Session = Depends(get_db)) -> ConnectionResult:
    env = svc.get_environment(session, environment_id)
    if env is None:
        raise HTTPException(404, "environment not found")
    password = (body or {}).get("password")
    remember = bool((body or {}).get("remember"))
    if password:
        register_secret(password)
    try:
        connector = await get_registry().connect(env, password=password, remember=remember)
        result = await connector.test_connection()
        svc.mark_connected(session, environment_id)

        # Adopt a real application name from the tenant. The seeded default may be
        # a placeholder (e.g. the demo app "MCWPCF") that doesn't exist on this
        # tenant — using it would 404 every metadata call. Normalise casing for a
        # valid entry, otherwise fall back to the first real application.
        apps: list[str] = [] if env.demo else list(result.get("applications", []))
        if apps:
            wanted = (env.preferred_application or "").lower()
            chosen = next((a for a in apps if a.lower() == wanted), None) or apps[0]
            env.preferred_application = chosen
            connector.info.application = chosen

        # Make the just-connected environment the project's active one.
        try:
            projects_svc.set_active_environment(session, env.project_id, env.id)
        except (KeyError, ValueError):
            pass
        return ConnectionResult(connected=True, environment_id=environment_id,
                                message=f"Connected to {env.name}"
                                        + (f" · application {env.preferred_application}" if apps else "") + ".",
                                application=env.preferred_application,
                                diagnostics={"demo": env.demo, **({} if env.demo else {"applications": apps})})
    except ConnectorError as exc:
        return ConnectionResult(connected=False, environment_id=environment_id, message=exc.message,
                                detail=exc.suggested_action, diagnostics=exc.to_dict())


@router.post("/api/environments/{environment_id}/disconnect", status_code=204)
def disconnect_environment(environment_id: str) -> None:
    get_registry().disconnect(environment_id)


@router.post("/api/environments/{environment_id}/test", response_model=ConnectionResult)
async def test_environment(environment_id: str, session: Session = Depends(get_db)) -> ConnectionResult:
    env = svc.get_environment(session, environment_id)
    if env is None:
        raise HTTPException(404, "environment not found")
    reg = get_registry()
    try:
        connector = reg.get(environment_id) or reg.get_or_demo(env)
        result = await connector.test_connection()
        return ConnectionResult(connected=True, environment_id=environment_id,
                                message="Connection OK.", diagnostics=result)
    except ConnectorError as exc:
        return ConnectionResult(connected=False, environment_id=environment_id, message=exc.message,
                                diagnostics=exc.to_dict())
