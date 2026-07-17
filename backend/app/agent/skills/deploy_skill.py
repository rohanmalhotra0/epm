"""/deploy skill — standalone verify/status (form deploys run inside /forms)."""

from __future__ import annotations

import re

from ...schemas.tools import SkillSpec
from ...services import deployments as deployments_svc
from .. import blocks
from .base import Emitter, Skill, SkillContext, SkillResult


class DeploySkill(Skill):
    spec = SkillSpec(name="/deploy", description="Verify deployments and show status.",
                     intent_examples=["verify that it was created", "deploy the form"])

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        text = ctx.user_text
        md = await ctx.tool_ctx.metadata()
        if re.search(r"\bverify\b", text, re.I):
            name = next((f.name for f in md.forms.values() if f.name.lower() in text.lower()), None)
            if name is None:
                recent = deployments_svc.list_deployments(ctx.session, ctx.project.id)
                name = recent[0].artifact_name if recent else None
            if name is None:
                await emit.block(blocks.markdown("There's nothing to verify yet. Build and deploy a form with `/forms`."))
                return SkillResult(skill="deploy")
            emit.set_steps(blocks.steps("Verifying artifact"))
            await emit.step_running(0)
            form = await ctx.connector.verify_form(ctx.application, name)
            await emit.step_done(0)
            if form is not None:
                await emit.block(blocks.markdown(
                    f"✅ Verified **{form.name}** exists in **{ctx.application}** "
                    f"(cube {form.cube or '—'}, folder {form.folder or '—'})."))
            else:
                await emit.block(blocks.markdown(f"⚠️ I could not verify a form named **{name}**."))
            return SkillResult(skill="deploy")

        await emit.block(blocks.markdown(
            "To deploy, start a form with `/forms`, review the preview, then say **deploy**. "
            "I'll show an approval card before anything touches Oracle."))
        return SkillResult(skill="deploy")
