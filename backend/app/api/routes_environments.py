"""Oracle environment routes (spec section 13)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..connector.errors import ConnectorError
from ..connector.factory import get_registry
from ..db.models import Project
from ..schemas.api import ConnectionResult, EnvironmentCreate, EnvironmentOut
from ..security.redaction import register_secret
from ..services import environments as svc
from ..services import projects as projects_svc
from .deps import authorize_project_id, get_current_owner, get_db, require_project

router = APIRouter(tags=["environments"])


def _require_environment(session: Session, owner: str, environment_id: str):
    """Load an environment and confirm the caller owns its project, or 404.

    By-id environment routes carry no project in the path, so — like the other
    by-id resources — they must resolve the environment, then re-check ownership
    of its project. Without this an attacker who knows (or guesses) an
    environment id could connect/test/disconnect/delete another owner's Oracle
    environment. 404 (not 403) so a foreign id is indistinguishable from a
    missing one. A no-op re-check when multi-user is off, so Demo is unchanged.
    """
    env = svc.get_environment(session, environment_id)
    if env is None:
        raise HTTPException(404, "environment not found")
    authorize_project_id(session, owner, env.project_id)
    return env


@router.get("/api/projects/{project_id}/environments", response_model=list[EnvironmentOut])
def list_environments(project: Project = Depends(require_project),
                      session: Session = Depends(get_db)) -> list[EnvironmentOut]:
    reg = get_registry()
    return [svc.to_out(e, connected=reg.is_connected(e.id)) for e in svc.list_environments(session, project.id)]


@router.post("/api/projects/{project_id}/environments", response_model=EnvironmentOut, status_code=201)
def create_environment(body: EnvironmentCreate, project: Project = Depends(require_project),
                       session: Session = Depends(get_db)) -> EnvironmentOut:
    env = svc.create_environment(session, project.id, name=body.name, base_url=body.base_url,
                                 username=body.username, auth_method=body.auth_method,
                                 oauth_token_url=body.oauth_token_url, oauth_client_id=body.oauth_client_id,
                                 oauth_scope=body.oauth_scope,
                                 classification=body.classification.value if hasattr(body.classification, "value") else body.classification,
                                 preferred_application=body.preferred_application, demo=body.demo)
    return svc.to_out(env)


@router.delete("/api/environments/{environment_id}", status_code=204)
def delete_environment(environment_id: str, session: Session = Depends(get_db),
                       owner: str = Depends(get_current_owner)) -> None:
    _require_environment(session, owner, environment_id)
    get_registry().disconnect(environment_id)
    svc.delete_environment(session, environment_id)


@router.post("/api/environments/{environment_id}/connect", response_model=ConnectionResult)
async def connect_environment(environment_id: str, body: dict, session: Session = Depends(get_db),
                              owner: str = Depends(get_current_owner)) -> ConnectionResult:
    env = _require_environment(session, owner, environment_id)
    # For OAuth environments the secret travels in `clientSecret`; it is
    # handled exactly like a password (process memory / encrypted store only).
    password = (body or {}).get("password") or (body or {}).get("clientSecret")
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
def disconnect_environment(environment_id: str, session: Session = Depends(get_db),
                           owner: str = Depends(get_current_owner)) -> None:
    _require_environment(session, owner, environment_id)
    get_registry().disconnect(environment_id)


@router.post("/api/environments/{environment_id}/test", response_model=ConnectionResult)
async def test_environment(environment_id: str, session: Session = Depends(get_db),
                           owner: str = Depends(get_current_owner)) -> ConnectionResult:
    env = _require_environment(session, owner, environment_id)
    reg = get_registry()
    try:
        connector = reg.get(environment_id) or reg.get_or_demo(env)
        result = await connector.test_connection()
        return ConnectionResult(connected=True, environment_id=environment_id,
                                message="Connection OK.", diagnostics=result)
    except ConnectorError as exc:
        return ConnectionResult(connected=False, environment_id=environment_id, message=exc.message,
                                diagnostics=exc.to_dict())
