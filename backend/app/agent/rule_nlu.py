"""Deterministic natural-language rule drafting (spec section 30).

Turns "create a rule that copies Working to Final" into a draft
``RuleSpecification`` without an LLM: cube, name and runtime prompts are
inferred from the request and the tenant outline, and every guess is reported
as an inference or an open question — nothing is decided silently. The model
may draft the script *body*, but the specification itself stays deterministic
and reproducible.
"""

from __future__ import annotations

import re

from ..artifacts.metadata import TenantMetadata
from ..schemas.rule_spec import RuleSpecification, RuleType, RuntimePrompt, RuntimePromptType
from . import outline_defaults as od
from .form_nlu import find_members

# "a rule called \"Copy Working to Final\"" — the user's own name always wins.
_QUOTED = re.compile(r"[\"“”'`]([^\"“”'`]{2,79})[\"“”'`]")

# Strips the command lead-in so the remainder reads as a title:
# "create a new business rule that copies working to final" -> "copies working to final".
_LEAD_IN = re.compile(
    r"^\s*(?:/rules?\s+)?(?:please\s+)?(?:can you\s+)?"
    r"(?:create|generate|write|draft|build|make)\s+(?:me\s+)?(?:a|an|the)?\s*(?:new\s+)?"
    r"(?:business\s+)?(?:calc(?:ulation)?\s+|groovy\s+)?rule\s*"
    r"(?:that|which|to|for|named|called)?\s*",
    re.I,
)
_TRAILING_PUNCT = re.compile(r"[\s.?!,;:]+$")

# Dimension *types* that commonly become runtime prompts on a business rule.
_PROMPTABLE_TYPES = ("entity", "scenario", "version")


def build_initial_rule_spec(
    text: str, md: TenantMetadata, application: str
) -> tuple[RuleSpecification, list[str], list[str]]:
    """Draft ``RuleSpecification`` from a creation request. Returns
    ``(spec, inferences, questions)`` — inferences say what was decided and why,
    questions flag the guesses the user should confirm."""
    inferences: list[str] = []
    questions: list[str] = []

    mentioned = find_members(md, text)
    cube = _infer_cube(text, md, mentioned, inferences, questions)
    name = _derive_name(text)
    prompts = _runtime_prompts(text, md, cube, inferences, questions)
    rule_type = _infer_rule_type(text, inferences)

    referenced_members: list[str] = []
    referenced_dimensions: list[str] = []
    for member, dim in mentioned:
        if member not in referenced_members:
            referenced_members.append(member)
        if dim not in referenced_dimensions:
            referenced_dimensions.append(dim)
    if referenced_members:
        inferences.append("Referenced members: " + ", ".join(referenced_members[:8])
                          + (" …" if len(referenced_members) > 8 else ""))

    spec = RuleSpecification(
        name=name,
        application=application,
        cube=cube,
        type=rule_type,
        purpose=text.strip()[:300] or None,
        runtime_prompts=prompts,
        referenced_dimensions=referenced_dimensions[:12],
        referenced_members=referenced_members[:12],
    )
    return spec, inferences, questions


# Calc-script cues: explicit "calc script", or Essbase calc verbs the drafter
# would emit as native calcscript rather than Groovy.
_CALC_SCRIPT_RE = re.compile(
    r"\bcalc(?:ulation)?\s*script\b|\bessbase\b|\b(?:fix|endfix|datacopy|agg|calc\s+dim|clearblock|cleardata)\b",
    re.I)


def _infer_rule_type(text: str, inferences: list[str]) -> RuleType:
    if _CALC_SCRIPT_RE.search(text):
        inferences.append("Drafting as an Essbase **calc script** (detected calc-script intent); "
                          "the import package is typed accordingly.")
        return RuleType.calc_script
    return RuleType.business_rule


# --- helpers ------------------------------------------------------------------


def _infer_cube(
    text: str, md: TenantMetadata, mentioned: list[tuple[str, str]],
    inferences: list[str], questions: list[str],
) -> str:
    """Explicit cube mention > cube containing a mentioned member > first cube.
    Always records how the choice was made — the cube is the one inference a
    rule can't survive being wrong about."""
    tl = text.lower()
    for cube_name in md.cubes:
        if re.search(rf"\b{re.escape(cube_name.lower())}\b", tl):
            inferences.append(f"Cube: {cube_name} (named in your request)")
            return cube_name
    for member, dim in mentioned:
        cube = next((c for c, rec in md.cubes.items() if dim in rec.dimensions), None)
        if cube:
            inferences.append(f"Cube: {cube} (contains {member}, which you mentioned)")
            return cube
    cube = next(iter(md.cubes), "OEP_FS")
    inferences.append(f"Cube: {cube} (defaulted — nothing in the request pinned a cube)")
    questions.append(f"I defaulted the cube to {cube} — is that the right cube for this rule?")
    return cube


def _derive_name(text: str) -> str:
    """Quoted string in the request, else a cleaned title of the request (<=80)."""
    m = _QUOTED.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip()[:80]
    remainder = _TRAILING_PUNCT.sub("", _LEAD_IN.sub("", text)).strip()
    if not remainder:
        return "New Business Rule"
    # Title-case plain lowercase words; leave technical tokens (OEP_FS, FY26) alone.
    titled = " ".join(w.capitalize() if w.islower() else w for w in remainder.split())
    return titled[:80].rstrip() or "New Business Rule"


def _runtime_prompts(
    text: str, md: TenantMetadata, cube: str,
    inferences: list[str], questions: list[str],
) -> list[RuntimePrompt]:
    """A runtime prompt per Entity/Scenario/Version dimension the request
    mentions (by type word or by the dimension's actual name), when the outline
    has such a dimension."""
    tl = text.lower()
    prompts: list[RuntimePrompt] = []
    for dim_type in _PROMPTABLE_TYPES:
        dim = od.find_dimension(md, dim_type, cube=cube)
        mentioned = re.search(rf"\b{dim_type}\b", tl) is not None or (
            dim is not None and re.search(rf"\b{re.escape(dim.lower())}\b", tl) is not None)
        if not mentioned:
            continue
        if dim is None:
            questions.append(
                f"You mentioned {dim_type}, but this application has no {dim_type}-typed "
                f"dimension — should the rule still prompt for one?")
            continue
        prompts.append(RuntimePrompt(
            name=dim, prompt_text=f"Select {dim}", type=RuntimePromptType.member, dimension=dim))
        inferences.append(f"Runtime prompt: {dim} (mentioned in your request)")
    return prompts
