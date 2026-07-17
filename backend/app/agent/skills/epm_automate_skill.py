"""/epm-automate skill — generate, validate and explain Oracle EPM Automate
commands and scripts, governed by the bundled ``epm_automate/SKILL.md``.

Drop-in: the behavioural contract lives in ``epm_automate/SKILL.md`` (the user's
skill package). This module loads it as the system prompt, classifies the
operation's risk, emits a deterministic command plan for recognised commands so
Demo Mode is useful offline, streams the provider's explanation, and forces an
approval confirmation for destructive / environment-wide operations. It never
executes anything and always uses secret placeholders.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from ...ai.base import AIMessage
from ...schemas.tools import SkillSpec
from .. import blocks
from .base import Emitter, Skill, SkillContext, SkillResult

_SKILL_DIR = Path(__file__).resolve().parent / "epm_automate"

# Compact command catalog (risk + template) so demo mode produces a real plan.
# Oracle docs remain the source of truth; templates use placeholders only.
_CATALOG: dict[str, tuple[str, str, str]] = {
    # command: (risk, template, note)
    "listfiles": ("read-only", "epmautomate listFiles", "Lists remote inbox/outbox/Migration files."),
    "getsubstvar": ("read-only", 'epmautomate getSubstVar ALL', "Reads substitution variables."),
    "uploadfile": ("write", 'epmautomate uploadFile "<LOCAL_FILE>" inbox',
                   "uploadFile does NOT overwrite an identically named remote file."),
    "downloadfile": ("write", 'epmautomate downloadFile "<REMOTE_PATH_OR_FILE>"', "Downloads a remote file."),
    "runbusinessrule": ("write", 'epmautomate runBusinessRule "<RULE_NAME>" "Period=<PERIOD>" "Entity=<ENTITY>"',
                        "Runtime-prompt names must match the rule exactly."),
    "runintegration": ("write", 'epmautomate runIntegration "<INTEGRATION_NAME>" importMode=Replace exportMode=Merge periodName="{Jan#FY26}"',
                       "Prefer runIntegration over deprecated runDataRule. Replace clears the POV first."),
    "runpipeline": ("write", 'epmautomate runPipeline "<PIPELINE_CODE>" "STARTPERIOD=<P>" "ENDPERIOD=<P>"', "Use only defined pipeline variables."),
    "importdata": ("write", 'epmautomate importData "<IMPORT_JOB>" <FILE_NAME> errorFile="errors.zip"', "Review the error ZIP afterwards."),
    "importmetadata": ("write", 'epmautomate importMetadata "<IMPORT_JOB>" <FILE.zip> errorFile="errors.zip"',
                       "A cube refresh is normally required afterwards."),
    "refreshcube": ("write", "epmautomate refreshCube <DATABASE_REFRESH_JOB>", "Run after successful metadata changes."),
    "setsubstvars": ("write", 'epmautomate setSubstVars ALL "CurYear=FY26" "CurPeriod=Jul"', "Preserve cube vs application scope."),
    "exportdata": ("write", 'epmautomate exportData "<EXPORT_JOB>" <FILE.zip>', "Exports application data via a configured job."),
    "clearcube": ("destructive", 'epmautomate clearCube "<CLEAR_CUBE_JOB>"', "DESTRUCTIVE — identify the exact clear region first."),
    "importsnapshot": ("destructive", 'epmautomate importSnapshot "<SNAPSHOT_NAME>"',
                       "Environment-wide. Default to application-artifact import only."),
    "cloneenvironment": ("destructive", 'epmautomate cloneEnvironment "<TGT_USER>" "<TGT_PWD_FILE>" "<TGT_URL>"',
                         "Environment clone — schedule outside the source maintenance window."),
    "deletefile": ("destructive", 'epmautomate deleteFile "<REMOTE_PATH_OR_FILE>"', "Deletes a remote file."),
    "restorebackup": ("destructive", 'epmautomate restoreBackup "<TIMESTAMP/Artifact_Snapshot.zip>" targetName="<TARGET>"',
                      "Run listBackups first."),
    "rundailymaintenance": ("destructive", "epmautomate runDailyMaintenance", "Environment-wide; confirm no active users/jobs."),
}
_DESTRUCTIVE = re.compile(
    r"\b(clearCube|importSnapshot|deleteFile|cloneEnvironment|restoreBackup|restoreEnvironment|"
    r"recreate|resetService|runDailyMaintenance|removeUsers|Replace|REPLACE_DATA|"
    r"clear|purge|reset|restore|wipe|clone|delete\s+(a\s+)?(remote\s+)?file|daily\s+maintenance)\b",
    re.I,
)


@lru_cache
def _skill_md() -> str:
    path = _SKILL_DIR / "SKILL.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _detect_command(text: str) -> tuple[str, str, str, str] | None:
    tl = text.lower().replace(" ", "")
    for key, (risk, template, note) in _CATALOG.items():
        if key in tl:
            return key, risk, template, note
    # some natural phrasings
    if "upload" in text.lower() and "file" in text.lower():
        return ("uploadfile", *_CATALOG["uploadfile"])
    if ("data integration" in text.lower() or "integration" in text.lower()) and "run" in text.lower():
        return ("runintegration", *_CATALOG["runintegration"])
    if "refresh" in text.lower() and "cube" in text.lower():
        return ("refreshcube", *_CATALOG["refreshcube"])
    if "clone" in text.lower() and ("environment" in text.lower() or "env" in text.lower()):
        return ("cloneenvironment", *_CATALOG["cloneenvironment"])
    return None


def _risk_of(text: str, detected: tuple | None) -> str:
    if detected:
        return detected[1]
    return "destructive" if _DESTRUCTIVE.search(text) else "write" if re.search(r"\b(run|upload|import|refresh|set)\b", text, re.I) else "read-only"


class EpmAutomateSkill(Skill):
    spec = SkillSpec(
        name="/epm-automate",
        description="Generate, validate and explain Oracle EPM Automate commands and scripts (never executes).",
        intent_examples=[
            "epm automate command to run a data integration",
            "write an epmautomate script to upload a file and refresh the cube",
            "how do I clone an environment with epm automate",
            "epmautomate uploadFile syntax",
        ],
        required_context=False,
        approval_required=False,
        allowed_tools=[],
    )

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        text = ctx.user_text
        detected = _detect_command(text)
        risk = _risk_of(text, detected)

        emit.set_steps(blocks.steps("Classifying operation", "Selecting command", "Building safe plan"))
        await emit.step_running(0)
        await emit.step_done(0)
        await emit.step_running(1)

        # Deterministic plan (works offline / demo) following the SKILL.md contract.
        env_name = ctx.environment_name
        plan = [
            "### EPM Automate plan",
            f"**Environment:** {env_name}",
            f"**Risk:** {risk.capitalize()}",
        ]
        if detected:
            _key, _risk, template, note = detected
            plan += [
                "",
                "#### Command",
                f"```shell\n{template}\n```",
                "",
                f"#### Notes\n{note}",
                "",
                "#### Before running",
                "- Log in first: `epmautomate login \"<USERNAME>\" \"<PASSWORD.epw>\" \"<EPM_URL>\"` (encrypted `.epw`, never a plaintext password).",
                "- Run `listFiles` to confirm remote paths; keep local vs inbox/outbox paths distinct.",
                "",
                "#### Verify",
                "- Check the EPM Jobs console / Data Integration process details and row/rejected counts.",
            ]
        else:
            plan += ["", "Tell me the operation (upload a file, run an integration, refresh a cube, clone an "
                         "environment, read/set a substitution variable…) and your OS, and I'll generate the exact "
                         "command or a complete script with login, logging and logout."]
        await emit.block(blocks.markdown("\n".join(plan)))
        await emit.step_done(1)

        # Provider-authored explanation, governed by the full SKILL.md.
        await emit.step_running(2)
        system = _skill_md() + (
            "\n\nYou are the EPM Automate skill inside EPM Wizard. Follow the response contract above. "
            "Use ONLY documented commands and placeholders for secrets. Never claim a command ran."
        )
        try:
            await emit.stream_provider_text(ctx, [AIMessage(role="user", content=text)], system=system)
        except Exception:
            pass  # deterministic plan already emitted; provider prose is a bonus
        await emit.step_done(2)

        if risk == "destructive":
            await emit.block(blocks.confirmation(
                "This is a destructive / environment-wide operation.",
                [
                    blocks.action("snapshot", "Take a snapshot first", "download Artifact Snapshot", "secondary"),
                    blocks.action("cancel", "Not now", "cancel", "ghost"),
                ],
                detail="Confirm the target environment URL and take a recent backup before running. "
                       "EPM Wizard will not execute EPM Automate for you.",
                severity="warning",
            ))

        return SkillResult(skill="epmAutomate", provider_used=getattr(ctx.provider, "name", None))
