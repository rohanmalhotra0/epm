"""Skill registry (spec section 35)."""

from __future__ import annotations

from .architecture_skill import ArchitectureSkill
from .base import Emitter, Skill, SkillContext, SkillResult
from .chat_skill import ChatSkill
from .compare_skill import CompareSkill
from .context_skill import ContextSkill
from .deploy_skill import DeploySkill
from .epm_automate_skill import EpmAutomateSkill
from .explain_skill import ExplainSkill
from .forms_skill import FormsSkill
from .help_skill import HelpSkill
from .reports_skill import ReportsSkill
from .rollback_skill import RollbackSkill
from .rules_skill import RulesSkill
from .search_skill import SearchSkill

SKILLS: dict[str, Skill] = {
    "forms": FormsSkill(),
    "reports": ReportsSkill(),
    "rules": RulesSkill(),
    "context": ContextSkill(),
    "architecture": ArchitectureSkill(),
    "deploy": DeploySkill(),
    "rollback": RollbackSkill(),
    "search": SearchSkill(),
    "explain": ExplainSkill(),
    "compare": CompareSkill(),
    "epmAutomate": EpmAutomateSkill(),
    "help": HelpSkill(),
    "chat": ChatSkill(),
}

# skills whose intent should route architecture requests
ARCH_KEYWORDS = ("architecture", "dimension", "cube-map", "cube map", "intersection",
                 "visualize", "dimensionality", "one cell", "data cell")

WORKFLOW_SKILLS = {"forms", "reports"}  # skills that own a resumable workflow


def get_skill(name: str) -> Skill:
    return SKILLS.get(name, SKILLS["chat"])


def skill_specs() -> list[dict]:
    return [s.spec.model_dump(by_alias=True) for s in SKILLS.values()]


__all__ = ["SKILLS", "get_skill", "skill_specs", "Skill", "SkillContext", "SkillResult",
           "Emitter", "WORKFLOW_SKILLS", "ARCH_KEYWORDS"]
