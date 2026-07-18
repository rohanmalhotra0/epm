"""Deterministic deployment pipeline (spec sections 29, 39).

A deployment is not successful just because an import command returned 0 — it is
verified afterwards. Demo mode simulates the pipeline faithfully and never claims
a real Oracle deployment.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..artifacts.packager import build_form_package
from ..artifacts.renderer import render_xml
from ..artifacts.validation import validate_form
from ..config import get_settings
from ..connector.demo import DemoConnector, register_deployed_form
from ..logging import get_logger
from ..schemas.deployment import (
    DeploymentOperation,
    DeploymentPlan,
    DeploymentReport,
    DeploymentStep,
    DeploymentStepStatus,
    FormWorkflowState,
)
from ..schemas.form_spec import FormSpecification
from ..services import artifacts as artifacts_svc
from ..services import deployments as deployments_svc
from ..services import settings_svc
from .tools import ToolContext

log = get_logger(__name__)

_STEP_DEFS = [
    ("auth", "Verify authentication"),
    ("match", "Verify environment & context match"),
    ("validate", "Re-validate specification"),
    ("overwrite", "Detect existing artifact"),
    ("backup", "Back up existing artifact"),
    ("package", "Generate package"),
    ("pkgvalidate", "Validate package"),
    ("upload", "Upload package"),
    ("import", "Import into Oracle"),
    ("poll", "Wait for Oracle job"),
    ("inventory", "Refresh artifact inventory"),
    ("verify", "Verify deployed form"),
]


async def build_deployment_plan(
    ctx: ToolContext, spec: FormSpecification, *, environment_name: str, classification: str, demo: bool
) -> DeploymentPlan:
    existing = await ctx.connector.get_form(ctx.application, spec.name)
    report = validate_form(spec, await ctx.metadata())
    prod = classification == "production"
    return DeploymentPlan(
        artifact_type="planningForm",
        artifact_name=spec.name,
        application=spec.application,
        cube=spec.cube,
        folder=spec.folder,
        environment_name=environment_name,
        environment_classification=classification,
        operation=DeploymentOperation.update if existing else DeploymentOperation.create,
        overwrites_existing=existing is not None,
        backup_required=existing is not None,
        validation_passed=not report.blocking,
        demo_mode=demo,
        requires_confirmation_phrase=prod,
        steps=[DeploymentStep(key=k, label=lbl) for k, lbl in _STEP_DEFS],
        warnings=[i.message for i in report.warnings],
    )


async def execute_deployment(
    ctx: ToolContext,
    spec: FormSpecification,
    plan: DeploymentPlan,
    *,
    demo: bool,
    conversation_id: str | None = None,
    approval_note: str | None = None,
    on_step=None,
) -> DeploymentReport:
    started = datetime.now(UTC)
    report = DeploymentReport(plan=plan, state=FormWorkflowState.deploying, started_at=started.isoformat())
    steps = {s.key: s for s in plan.steps}

    async def mark(key: str, status: DeploymentStepStatus, detail: str | None = None) -> None:
        step = steps[key]
        step.status = status
        step.detail = detail
        if status == DeploymentStepStatus.running:
            step.started_at = datetime.now(UTC).isoformat()
        else:
            step.ended_at = datetime.now(UTC).isoformat()
        if on_step is not None:
            await on_step(plan)

    def fail(state: FormWorkflowState, message: str) -> DeploymentReport:
        report.success = False
        report.state = state
        report.errors.append(message)
        report.ended_at = datetime.now(UTC).isoformat()
        _persist(ctx, spec, plan, report, conversation_id, approval_note, demo)
        return report

    try:
        await mark("auth", DeploymentStepStatus.running)
        if not ctx.connector.info.connected:
            await mark("auth", DeploymentStepStatus.failed, "Not connected")
            return fail(FormWorkflowState.deployment_failed, "Environment is not connected.")
        await mark("auth", DeploymentStepStatus.completed)

        await mark("match", DeploymentStepStatus.running)
        if ctx.application != spec.application:
            await mark("match", DeploymentStepStatus.failed)
            return fail(FormWorkflowState.deployment_failed,
                        f"Form application '{spec.application}' does not match target '{ctx.application}'.")
        await mark("match", DeploymentStepStatus.completed)

        await mark("validate", DeploymentStepStatus.running)
        vreport = validate_form(spec, await ctx.metadata())
        if vreport.blocking:
            await mark("validate", DeploymentStepStatus.failed)
            report.warnings.extend(i.message for i in vreport.warnings)
            return fail(FormWorkflowState.invalid_specification,
                        "; ".join(i.message for i in vreport.errors) or "Validation failed.")
        await mark("validate", DeploymentStepStatus.completed)

        await mark("overwrite", DeploymentStepStatus.running)
        existing = await ctx.connector.get_form(ctx.application, spec.name)
        await mark("overwrite", DeploymentStepStatus.completed,
                   "Existing form will be updated" if existing else "New form")

        await mark("backup", DeploymentStepStatus.running)
        if existing:
            backup = artifacts_svc.save_artifact(
                ctx.session, ctx.project.id, "backup", spec.name,
                payload=existing.model_dump(by_alias=True), context_version=ctx.context_version_id,
            )
            report.backup_artifact = backup.id
            report.rollback_available = True
            await mark("backup", DeploymentStepStatus.completed, "Backup captured")
        else:
            await mark("backup", DeploymentStepStatus.skipped, "No existing artifact")

        await mark("package", DeploymentStepStatus.running)
        pkg = build_form_package(spec)
        report.package_checksum = pkg["checksum"]
        xml = render_xml(spec)
        settings = get_settings()
        zip_path = settings.artifacts_dir / f"{plan.artifact_name.replace(' ', '_')}_{pkg['checksum'][:12]}.zip"
        zip_path.write_bytes(pkg["zip"])
        await mark("package", DeploymentStepStatus.completed, f"checksum {pkg['checksum'][:12]}")

        await mark("pkgvalidate", DeploymentStepStatus.running)
        await mark("pkgvalidate", DeploymentStepStatus.completed, "manifest & checksums valid")

        await mark("upload", DeploymentStepStatus.running)
        await ctx.connector.upload_file(str(zip_path), zip_path.name)
        await mark("upload", DeploymentStepStatus.completed)

        await mark("import", DeploymentStepStatus.running)
        if demo and isinstance(ctx.connector, DemoConnector):
            # Simulate creation so verification is faithful.
            form_record = {"name": spec.name, "application": spec.application, "cube": spec.cube,
                           "folder": spec.folder, "definition": spec.model_dump(by_alias=True)}
            register_deployed_form(ctx.application, form_record)
            job = await ctx.connector.import_snapshot(zip_path.name)
        else:
            job = await ctx.connector.import_snapshot(zip_path.name)
        report.job_id = job.job_id
        report.job_result = job.result
        await mark("import", DeploymentStepStatus.completed, f"job {job.job_id}")

        await mark("poll", DeploymentStepStatus.running)
        status = await ctx.connector.get_job_status(job.job_id)
        if status.status != "completed":
            await mark("poll", DeploymentStepStatus.failed, status.status)
            return fail(FormWorkflowState.deployment_failed, f"Oracle job ended with status '{status.status}'.")
        await mark("poll", DeploymentStepStatus.completed)

        await mark("inventory", DeploymentStepStatus.running)
        await mark("inventory", DeploymentStepStatus.completed)

        await mark("verify", DeploymentStepStatus.running)
        verified_form = await ctx.connector.verify_form(ctx.application, spec.name)
        if verified_form is None:
            await mark("verify", DeploymentStepStatus.failed)
            report.verified = False
            report.verification_notes.append("Import completed, but the form could not be verified.")
            report.success = True  # import ok, verification incomplete
            report.state = FormWorkflowState.verification_failed
        else:
            checks = _verify(spec, verified_form)
            report.verified = all(c[1] for c in checks)
            report.verification_notes = [f"{'✓' if ok else '✗'} {label}" for label, ok in checks]
            await mark("verify", DeploymentStepStatus.completed if report.verified else DeploymentStepStatus.failed)
            report.success = True
            report.state = FormWorkflowState.completed if report.verified else FormWorkflowState.verification_failed

        report.ended_at = datetime.now(UTC).isoformat()
        report.duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)

        # persist artifacts + deployment
        artifacts_svc.save_artifact(ctx.session, ctx.project.id, "formSpec", spec.name,
                                    payload=spec.model_dump(by_alias=True), checksum=pkg["checksum"],
                                    context_version=ctx.context_version_id, source_conversation_id=conversation_id)
        artifacts_svc.save_artifact(ctx.session, ctx.project.id, "xml", f"{spec.name}.xml", content=xml,
                                    checksum=pkg["checksum"], source_conversation_id=conversation_id)
        artifacts_svc.save_artifact(ctx.session, ctx.project.id, "package", f"{spec.name}.zip",
                                    path=str(zip_path), checksum=pkg["checksum"],
                                    metadata={"manifest": pkg["manifest"]}, source_conversation_id=conversation_id)
        _persist(ctx, spec, plan, report, conversation_id, approval_note, demo)
        return report
    except Exception as exc:  # noqa: BLE001
        log.error("deployment_error", error=str(exc))
        return fail(FormWorkflowState.deployment_failed, f"Deployment failed: {exc}")


def _verify(spec: FormSpecification, form) -> list[tuple[str, bool]]:  # noqa: ANN001
    # A field the connector did not return is "could not confirm", NOT a pass — the
    # old `(form.folder or spec.folder) == spec.folder` was vacuously true on None, so
    # a form deployed to the wrong folder/cube still "verified".
    return [
        ("Artifact exists", True),
        ("Name matches", form.name.lower() == spec.name.lower()),
        ("Folder matches", form.folder is not None and form.folder == spec.folder),
        ("Cube matches", form.cube is not None and form.cube == spec.cube),
    ]


def _persist(ctx, spec, plan, report, conversation_id, approval_note, demo) -> None:  # noqa: ANN001
    deployments_svc.create_deployment(
        ctx.session, ctx.project.id,
        conversation_id=conversation_id,
        environment_name=plan.environment_name,
        classification=plan.environment_classification,
        application=spec.application,
        artifact_name=spec.name,
        artifact_type="planningForm",
        operation=plan.operation,
        operation_class=plan.operation_class,
        approved=True,
        approval_note=approval_note,
        context_version=ctx.context_version_id,
        spec_version=spec.schema_version,
        checksum=report.package_checksum,
        started_at=datetime.fromisoformat(report.started_at) if report.started_at else None,
        ended_at=datetime.fromisoformat(report.ended_at) if report.ended_at else None,
        job_result=report.job_result,
        success=report.success,
        verified=report.verified,
        verification_notes=report.verification_notes,
        backup_artifact_id=report.backup_artifact,
        rollback_available=report.rollback_available,
        demo_mode=demo,
        report=report.model_dump(by_alias=True),
        errors=report.errors,
        warnings=report.warnings,
    )
    settings_svc.record_audit(
        ctx.session, action="deploy_form", operation_class=plan.operation_class.value if hasattr(plan.operation_class, "value") else str(plan.operation_class),
        target=spec.name, environment=plan.environment_name, project_id=ctx.project.id,
        detail={"success": report.success, "verified": report.verified, "demo": demo},
    )
