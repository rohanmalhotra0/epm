"""Diagnostics routes (spec section 41)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..ai.registry import resolve_active_provider
from ..config import get_settings
from ..connector.epm_automate import EpmAutomateRunner
from ..logging import recent_logs
from ..schemas.api import DiagnosticLogEntry, DiagnosticLogsOut, DiagnosticsReport, SubsystemStatus
from ..schemas.common import (
    CONTEXT_MANIFEST_SCHEMA_VERSION,
    DEPLOYMENT_PLAN_SCHEMA_VERSION,
    FORM_SPEC_SCHEMA_VERSION,
    RULE_SPEC_SCHEMA_VERSION,
)
from ..security.redaction import REDACTION, redact_text
from ..services import context_store, projects
from .deps import get_db

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


def _build_report(session: Session) -> DiagnosticsReport:
    settings = get_settings()
    subsystems: list[SubsystemStatus] = []

    # database
    try:
        session.execute(text("SELECT 1"))
        subsystems.append(SubsystemStatus(name="SQLite database", status="ok", detail=str(settings.db_path)))
    except Exception as exc:
        subsystems.append(SubsystemStatus(name="SQLite database", status="error", detail=str(exc)[:120]))

    subsystems.append(SubsystemStatus(name="Local API", status="ok", detail="FastAPI"))
    subsystems.append(SubsystemStatus(name="Storage", status="ok", detail=str(settings.data_dir)))

    # provider
    project = projects.get_default_project(session)
    profile, provider = resolve_active_provider(session, project.id if project else None)
    active_model = provider.config.default_model
    subsystems.append(SubsystemStatus(name="AI provider", status="ok",
                                      detail=f"{provider.name} ({active_model})"))

    # EPM Automate / Java
    diag = EpmAutomateRunner().diagnostics()
    subsystems.append(SubsystemStatus(name="Java runtime", status="ok" if diag["javaFound"] else "warn",
                                      detail=diag.get("javaPath") or "not found"))
    subsystems.append(SubsystemStatus(name="EPM Automate", status="ok" if diag["epmAutomateInstalled"] else "unavailable",
                                      detail=diag.get("epmAutomatePath") or "not installed (Demo Mode)"))

    # context
    if project is not None:
        cv = context_store.get_active_context(session, project.id)
        if cv is not None:
            subsystems.append(SubsystemStatus(name="Context", status="ok",
                                              detail=f"{cv.label} ({cv.mode})"))
        else:
            subsystems.append(SubsystemStatus(name="Context", status="warn", detail="No active context"))

    # redaction self-test
    redaction_ok = REDACTION in redact_text("password=supersecretvalue")
    subsystems.append(SubsystemStatus(name="Redaction", status="ok" if redaction_ok else "error",
                                      detail="self-test passed" if redaction_ok else "self-test FAILED"))

    return DiagnosticsReport(
        app_version=settings.version,
        subsystems=subsystems,
        storage_path=str(settings.data_dir),
        active_provider=provider.name,
        active_model=active_model,
        demo_mode=not diag["epmAutomateInstalled"],
        schema_versions={
            "formSpecification": FORM_SPEC_SCHEMA_VERSION,
            "ruleSpecification": RULE_SPEC_SCHEMA_VERSION,
            "contextManifest": CONTEXT_MANIFEST_SCHEMA_VERSION,
            "deploymentPlan": DEPLOYMENT_PLAN_SCHEMA_VERSION,
        },
        feature_flags={"realOracleDeployment": False, "oauth": False},
        redaction_healthy=redaction_ok,
    )


@router.get("", response_model=DiagnosticsReport)
def diagnostics(session: Session = Depends(get_db)) -> DiagnosticsReport:
    return _build_report(session)


@router.get("/logs", response_model=DiagnosticLogsOut)
def diagnostics_logs(limit: int = 200) -> DiagnosticLogsOut:
    """Recent in-memory log entries (already redacted), newest first."""
    return DiagnosticLogsOut(logs=[DiagnosticLogEntry(**entry) for entry in recent_logs(limit)])


@router.get("/bundle")
def diagnostics_bundle(session: Session = Depends(get_db)) -> Response:
    report = _build_report(session)
    body = redact_text(report.model_dump_json(by_alias=True, indent=2))
    return Response(content=body, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="epm-wizard-diagnostics.json"'})
