"""/rollback skill — restore the most recent reversible deployment."""

from __future__ import annotations

from ...connector.demo import DemoConnector, register_deployed_form
from ...schemas.tools import SkillSpec
from ...services import artifacts as artifacts_svc
from ...services import deployments as deployments_svc
from ...services import settings_svc
from .. import blocks
from .base import Emitter, Skill, SkillContext, SkillResult


class RollbackSkill(Skill):
    spec = SkillSpec(name="/rollback", description="Roll back the most recent deployment.",
                     intent_examples=["roll back", "undo the last deployment"], approval_required=True)

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        deps = deployments_svc.list_deployments(ctx.session, ctx.project.id)
        candidate = next((d for d in deps if d.rollback_available and d.backup_artifact_id), None)
        if candidate is None:
            await emit.block(blocks.markdown(
                "There's no reversible deployment to roll back. Rollback is available when a deployment "
                "overwrote an existing artifact (a backup was captured)."))
            return SkillResult(skill="rollback")

        backup = artifacts_svc.get_artifact(ctx.session, candidate.backup_artifact_id)
        if backup is None or not backup.payload:
            await emit.block(blocks.markdown("The backup artifact for that deployment is missing."))
            return SkillResult(skill="rollback")

        actions = [
            blocks.action("confirm", f"Roll back {candidate.artifact_name}", f"confirm rollback {candidate.id}", "danger"),
            blocks.action("cancel", "Cancel", "cancel", "ghost"),
        ]
        if f"confirm rollback {candidate.id}" not in ctx.user_text:
            await emit.block(blocks.confirmation(
                f"Roll back **{candidate.artifact_name}** on **{candidate.environment_name}** to the captured backup?",
                actions, detail="This restores the previous version of the artifact.", severity="warning"))
            return SkillResult(skill="rollback")

        emit.set_steps(blocks.steps("Restoring backup", "Verifying"))
        await emit.step_running(0)
        if isinstance(ctx.connector, DemoConnector):
            register_deployed_form(ctx.application, backup.payload)
        await emit.step_done(0)
        await emit.step_running(1)
        form = await ctx.connector.verify_form(ctx.application, candidate.artifact_name)
        await emit.step_done(1)
        settings_svc.record_audit(ctx.session, action="rollback", operation_class="destructive",
                                  target=candidate.artifact_name, environment=candidate.environment_name,
                                  project_id=ctx.project.id, detail={"deploymentId": candidate.id})
        await emit.block(blocks.markdown(
            f"↩️ Rolled back **{candidate.artifact_name}** to the previous version"
            + (" (demo)." if isinstance(ctx.connector, DemoConnector) else ".")
            + (f" Verified: {form is not None}." if form is not None else "")))
        return SkillResult(skill="rollback")
