"""/rules and /run-rule skill (spec sections 30-32)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from ...connector.demo import DemoConnector
from ...connector.errors import ConnectorError
from ...connector.validation import validate_prompt_value
from ...schemas.form_spec import FormSpecification
from ...schemas.tools import SkillSpec
from ...services import rule_executions, settings_svc
from .. import blocks
from ..form_nlu import _match_rule
from .base import Emitter, Skill, SkillContext, SkillResult


class RulesSkill(Skill):
    spec = SkillSpec(
        name="/rules", description="Search, explain and run business rules.",
        intent_examples=["run the IR rule", "run rule Add New Hire", "list rules", "create a new-hire workflow"],
        allowed_tools=["list_rules", "get_rule", "run_business_rule"], approval_required=True,
    )

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        text = ctx.user_text
        md = await ctx.tool_ctx.metadata()

        # confirmed run from the runtime-prompt form: "... :: k=v; k=v"
        if "::" in text:
            head, _, kv = text.partition("::")
            name = _extract_rule_name(head, md)
            values = _parse_kv(kv)
            if name:
                return await self._execute(ctx, emit, name, values)

        if re.search(r"\b(list|show|what|which)\b.*\brules?\b", text, re.I) and "run" not in text.lower():
            await self._list(emit, md)
            return SkillResult(skill="rules")

        name = _extract_rule_name(text, md)
        if not name and "new hire" in text.lower():
            name = _match_rule(md, "Add New Hire")
        if not name:
            await self._list(emit, md)
            await emit.block(blocks.markdown("Which rule would you like to run? Name it, e.g. `run the IR rule`."))
            return SkillResult(skill="rules")

        return await self._prompt(ctx, emit, md, name)

    async def _list(self, emit, md):
        lines = ["Business rules in context:", "", "| Rule | Cube | Type | Runtime prompts |", "|---|---|---|---|"]
        for r in md.rules.values():
            lines.append(f"| {r.name} | {r.cube or ''} | {r.type} | {', '.join(r.runtime_prompts) or '—'} |")
        await emit.block(blocks.markdown("\n".join(lines)))

    async def _prompt(self, ctx: SkillContext, emit: Emitter, md, name: str) -> SkillResult:
        rule = await ctx.connector.get_rule(ctx.application, name)
        if rule is None:
            await emit.block(blocks.markdown(f"I couldn't find a rule named **{name}**."))
            return SkillResult(skill="rules")
        emit.set_steps(blocks.steps("Resolving rule", "Discovering runtime prompts"))
        await emit.step_running(0)
        await emit.step_done(0)
        await emit.step_running(1)

        prompt_defs = _prompt_defs(ctx, rule)
        spec = ctx.active_form_spec if isinstance(ctx.active_form_spec, FormSpecification) else None
        fields = []
        prefilled = {}
        for p in prompt_defs:
            default = _resolve_default(md, p.get("default"), p.get("dimension"), spec)
            if default:
                prefilled[p["name"]] = default
            fields.append({
                "name": p["name"], "type": p.get("type", "text"), "dimension": p.get("dimension"),
                "promptText": p.get("promptText") or p["name"], "required": p.get("required", True),
                "default": default,
            })
        await emit.step_done(1)

        kv = "; ".join(f"{f['name']}={f['default']}" for f in fields if f["default"])
        run_value = f"/run-rule {name} :: {kv}"
        await emit.prose(f"Ready to run **{name}** on cube **{rule.cube}**. "
                         f"Review the runtime prompts, then run it.\n\n")
        await emit.block(blocks.runtime_prompt_form({
            "ruleName": name, "application": ctx.application, "cube": rule.cube,
            "fields": fields, "prefilledFrom": prefilled,
            "actions": [
                blocks.action("run", "Run rule", run_value, "primary").model_dump(by_alias=True),
                blocks.action("cancel", "Cancel", "cancel", "ghost").model_dump(by_alias=True),
            ],
        }))
        return SkillResult(skill="rules")

    async def _execute(self, ctx: SkillContext, emit: Emitter, name: str, values: dict) -> SkillResult:
        rule = await ctx.connector.get_rule(ctx.application, name)
        if rule is None:
            await emit.block(blocks.markdown(f"I couldn't find a rule named **{name}**."))
            return SkillResult(skill="rules")
        emit.set_steps(blocks.steps("Validating prompt values", "Submitting to Oracle", "Waiting for job", "Recording result"))
        await emit.step_running(0)
        try:
            values = {k: validate_prompt_value(str(v)) for k, v in values.items()}
        except ConnectorError as exc:
            await emit.block(blocks.error_diagnostics({"category": exc.category.value, "message": exc.message,
                                                       "suggestedAction": exc.suggested_action}))
            return SkillResult(skill="rules")
        await emit.step_done(0)

        await emit.block(blocks.tool_invocation({"tool": "run_business_rule", "operationClass": "execution",
                                                 "status": "running", "summary": f"Running {name}"}))
        started = datetime.now(UTC)
        await emit.step_running(1)
        try:
            job = await ctx.connector.run_business_rule(ctx.application, rule.cube, name, values)
        except ConnectorError as exc:
            await emit.block(blocks.error_diagnostics({"category": exc.category.value, "message": exc.message,
                                                       "suggestedAction": exc.suggested_action}))
            return SkillResult(skill="rules")
        await emit.step_done(1)
        await emit.step_running(2)
        status = await ctx.connector.get_job_status(job.job_id)
        await emit.step_done(2)
        await emit.step_running(3)
        duration = int((datetime.now(UTC) - started).total_seconds() * 1000)
        rule_executions.create_execution(
            ctx.session, ctx.project.id, conversation_id=ctx.conversation.id,
            rule_name=name, application=ctx.application, cube=rule.cube,
            status=status.status, prompt_values=values, job_id=job.job_id, job_result=job.result,
            started_at=started, ended_at=datetime.now(UTC), duration_ms=duration,
            output=job.details, demo_mode=isinstance(ctx.connector, DemoConnector),
        )
        settings_svc.record_audit(ctx.session, action="run_rule", operation_class="execution",
                                  target=name, environment=ctx.environment_name, project_id=ctx.project.id,
                                  detail={"status": status.status, "demo": isinstance(ctx.connector, DemoConnector)})
        await emit.step_done(3)

        await emit.block(blocks.tool_invocation({
            "tool": "run_business_rule", "operationClass": "execution",
            "status": "completed" if status.status == "completed" else "failed",
            "summary": f"{name}: {status.status}", "detail": job.details,
        }))
        prompt_lines = "\n".join(f"- **{k}**: {v}" for k, v in values.items()) or "_none_"
        await emit.block(blocks.markdown(
            f"### Rule executed: {name}\n\n"
            f"- **Status:** {status.status}\n- **Cube:** {rule.cube}\n- **Job:** {job.job_id}\n"
            f"- **Duration:** {duration} ms\n\n**Runtime prompts used:**\n{prompt_lines}\n\n_{job.details or ''}_"))
        return SkillResult(skill="rules")


def _extract_rule_name(text: str, md) -> str | None:
    m = re.search(r"run\s+(the\s+)?([\w \-]+?)\s+rule\b", text, re.I)
    if m:
        return _match_rule(md, m.group(2))
    m = re.search(r"\brule\s+([\w \-]+)$", text.strip(), re.I)
    if m:
        return _match_rule(md, m.group(1))
    # bare rule name mentioned
    for r in md.rules.values():
        if re.search(rf"\b{re.escape(r.name)}\b", text, re.I):
            return r.name
    m = re.search(r"run\s+(?:the\s+)?([A-Za-z][\w \-]*)", text, re.I)
    return _match_rule(md, m.group(1)) if m else None


def _parse_kv(text: str) -> dict:
    values = {}
    for part in re.split(r"[;,]", text):
        m = re.match(r"\s*([\w ]+?)\s*=\s*(.+?)\s*$", part)
        if m:
            values[m.group(1).strip()] = m.group(2).strip()
    return values


def _prompt_defs(ctx: SkillContext, rule) -> list[dict]:
    if isinstance(ctx.connector, DemoConnector):
        raw = ctx.connector.get_rule_raw(rule.name)
        if raw and raw.get("prompt_defs"):
            return raw["prompt_defs"]
    return [{"name": p, "type": "text", "required": True} for p in rule.runtime_prompts]


def _resolve_default(md, default, dimension, spec):  # noqa: ANN001
    if default and default.startswith("{{") and default.endswith("}}"):
        var = md.get_variable(default[2:-2])
        if var and var.value:
            return var.value
        default = None
    if not default and dimension and spec is not None:
        for am in spec.pov + spec.pages:
            if am.dimension == dimension and am.selection.member:
                return am.selection.member
    if not default and dimension:
        var = next((v for v in md.variables.values() if v.dimension == dimension), None)
        if var and var.value:
            return var.value
    return default
