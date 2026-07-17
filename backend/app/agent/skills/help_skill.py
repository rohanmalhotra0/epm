"""/help skill (spec section 35)."""

from __future__ import annotations

from ...schemas.tools import SkillSpec
from .. import blocks
from .base import Emitter, Skill, SkillContext, SkillResult

HELP_TEXT = """### What EPM Wizard can do

I'm a local-first assistant for Oracle EPM implementation. Everything runs on your machine.

**Skills** (type the command or just ask):
- `/context` — learn or refresh your EPM application
- `/forms` — build, preview, edit and deploy data forms
- `/rules` · `/run-rule` — search, explain and run business rules
- `/architecture` — visualize a cube's dimensions & how a form uses them
- `/deploy` · `/rollback` — deploy artifacts and roll back
- `/search` — find members, forms, rules, variables
- `/explain` — explain a rule or calculation
- `/compare` — compare cubes or context versions

**Try:**
- "Create an Actuals form with level-zero descendants of Total Payroll in rows"
- "What cubes and dimensions exist?"
- "Visualize OEP_DCSH"
- "Run the IR rule"
"""


class HelpSkill(Skill):
    spec = SkillSpec(name="/help", description="Explain what EPM Wizard can do.",
                     intent_examples=["help", "what can you do"])

    async def run(self, ctx: SkillContext, emit: Emitter) -> SkillResult:
        await emit.block(blocks.markdown(HELP_TEXT))
        return SkillResult(skill="help")
