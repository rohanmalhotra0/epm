"""Deterministic intent routing (spec section 35).

Slash commands are explicit; natural language is matched by keyword. This runs
100% locally so demo mode is fully functional without an LLM. When a form/rule
workflow is already active, the orchestrator routes follow-up messages to that
skill before consulting this router.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SLASH_SKILLS = {
    "forms": "forms",
    "form": "forms",
    "reports": "reports",
    "report": "reports",
    "rules": "rules",
    "rule": "rules",
    "run-rule": "rules",
    "run": "rules",
    "context": "context",
    "deploy": "deploy",
    "rollback": "rollback",
    "search": "search",
    "explain": "explain",
    "compare": "compare",
    "epm-automate": "epmAutomate",
    "epmautomate": "epmAutomate",
    "automate": "epmAutomate",
    "help": "help",
    # Cube Architecture & Dimensionality Visualizer (spec 4B)
    "architecture": "architecture",
    "dimensions": "architecture",
    "cube-map": "architecture",
    "explain-intersection": "architecture",
    "compare-cubes": "architecture",
}

# (compiled pattern, skill) — order matters; first match wins.
_RULES: list[tuple[re.Pattern[str], str]] = [
    # EPM Automate command/script generation — explicit mentions win first.
    (re.compile(r"\bepm\s*automate\b|\bepmautomate\b|\bepw\b|\.epw\b", re.I), "epmAutomate"),
    (re.compile(r"\b(uploadFile|downloadFile|listFiles|listBackups|runIntegration|runPipeline|runRuleSet|"
                r"importSnapshot|exportSnapshot|copySnapshotFromInstance|clearCube|cloneEnvironment|refreshCube|"
                r"importMetadata|exportMetadata|importData|exportData|setSubstVars|getSubstVar|restoreBackup|"
                r"runDailyMaintenance|setApplicationAdminMode)\b"), "epmAutomate"),
    (re.compile(r"\b(build|create|refresh|learn|import|export)\s+(the\s+)?context\b", re.I), "context"),
    (re.compile(r"\b(learn|understand)\s+this\s+application\b", re.I), "context"),
    (re.compile(r"\brun\s+(the\s+)?[\w \-]*\brule\b", re.I), "rules"),
    (re.compile(r"\brun\s+the\s+\w+\b", re.I), "rules"),
    (re.compile(r"\b(create|generate|write|explain|associate|inspect)\s+(a\s+|the\s+)?[\w \-]*\b(business\s+)?rule\b", re.I), "rules"),
    (re.compile(r"\b(create|build|make|generate)\s+(a\s+|an\s+|the\s+)?[\w \-]*\bform\b", re.I), "forms"),
    (re.compile(r"\bform\s+(with|for|like|using)\b", re.I), "forms"),
    (re.compile(r"\b(create|build|make|generate|produce|show me)\s+(a\s+|an\s+|the\s+)?[\w \-]*\breport\b", re.I), "reports"),
    (re.compile(r"\breport\s+(with|for|like|using|of|on|showing)\b", re.I), "reports"),
    (re.compile(r"\bnew[- ]hire\b", re.I), "rules"),
    (re.compile(r"\b(visualize|architecture of|cube[- ]map|dimensionality|cross[- ]dimensional|"
                r"one (data )?cell|data cell|identifies this cell|makes up one|which dimensions am i missing)\b", re.I), "architecture"),
    (re.compile(r"\bwhat dimensions are in\b", re.I), "architecture"),
    (re.compile(r"\b(deploy|verify that|verify it|verify the)\b", re.I), "deploy"),
    (re.compile(r"\broll\s*back\b", re.I), "rollback"),
    (re.compile(r"\bcompare\b", re.I), "compare"),
    (re.compile(r"\b(what|which|list|show|find|search)\b.*\b(cube|cubes|dimension|dimensions|member|members|form|forms|rule|rules|variable|variables)\b", re.I), "search"),
    (re.compile(r"\bexplain\b", re.I), "explain"),
    (re.compile(r"\b(help|what can you do|get started)\b", re.I), "help"),
]


@dataclass
class Intent:
    skill: str
    text: str
    is_slash: bool = False


def detect_intent(message: str) -> Intent:
    text = (message or "").strip()
    if text.startswith("/"):
        head, _, rest = text[1:].partition(" ")
        skill = SLASH_SKILLS.get(head.lower(), "chat")
        return Intent(skill=skill, text=rest.strip(), is_slash=True)
    for pattern, skill in _RULES:
        if pattern.search(text):
            return Intent(skill=skill, text=text)
    return Intent(skill="chat", text=text)
