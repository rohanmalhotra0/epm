"""Artifact + deployment + rule-execution routes (spec sections 37, 38)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..schemas.api import ArtifactOut, DeploymentOut, RuleExecutionOut
from ..services import artifacts as artifacts_svc
from ..services import deployments as deployments_svc
from ..services import rule_executions as rule_svc
from .deps import get_db

router = APIRouter(tags=["artifacts"])


@router.get("/api/projects/{project_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts(project_id: str, kind: str | None = None, session: Session = Depends(get_db)) -> list[ArtifactOut]:
    return [artifacts_svc.to_out(a) for a in artifacts_svc.list_artifacts(session, project_id, kind)]


@router.get("/api/artifacts/{artifact_id}", response_model=ArtifactOut)
def get_artifact(artifact_id: str, session: Session = Depends(get_db)) -> ArtifactOut:
    a = artifacts_svc.get_artifact(session, artifact_id)
    if a is None:
        raise HTTPException(404, "artifact not found")
    return artifacts_svc.to_out(a, include_payload=True)


@router.get("/api/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str, session: Session = Depends(get_db)) -> Response:
    a = artifacts_svc.get_artifact(session, artifact_id)
    if a is None:
        raise HTTPException(404, "artifact not found")
    if a.path and Path(a.path).exists():
        data = Path(a.path).read_bytes()
        return Response(content=data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{a.name}"'})
    if a.content is not None:
        return Response(content=a.content, media_type="text/plain",
                        headers={"Content-Disposition": f'attachment; filename="{a.name}"'})
    if a.payload is not None:
        import json
        return Response(content=json.dumps(a.payload, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{a.name}.json"'})
    raise HTTPException(404, "artifact has no downloadable content")


@router.delete("/api/artifacts/{artifact_id}", status_code=204)
def delete_artifact(artifact_id: str, session: Session = Depends(get_db)) -> None:
    artifacts_svc.delete_artifact(session, artifact_id)


@router.get("/api/projects/{project_id}/deployments", response_model=list[DeploymentOut])
def list_deployments(project_id: str, classification: str | None = None, artifact_name: str | None = None,
                     success: bool | None = None, session: Session = Depends(get_db)) -> list[DeploymentOut]:
    return [deployments_svc.to_out(d) for d in
            deployments_svc.list_deployments(session, project_id, classification, artifact_name, success)]


@router.get("/api/deployments/{deployment_id}", response_model=DeploymentOut)
def get_deployment(deployment_id: str, session: Session = Depends(get_db)) -> DeploymentOut:
    d = deployments_svc.get_deployment(session, deployment_id)
    if d is None:
        raise HTTPException(404, "deployment not found")
    return deployments_svc.to_out(d)


@router.get("/api/projects/{project_id}/rule-executions", response_model=list[RuleExecutionOut])
def list_rule_executions(project_id: str, rule_name: str | None = None, session: Session = Depends(get_db)) -> list[RuleExecutionOut]:
    return [rule_svc.to_out(r) for r in rule_svc.list_executions(session, project_id, rule_name)]
