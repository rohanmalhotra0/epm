"""Canonical RuleSpecification (spec section 30)."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import RULE_SPEC_SCHEMA_VERSION, CamelModel
from .form_spec import GenerationMetadata


class RuleType(str, Enum):
    business_rule = "businessRule"
    calc_script = "calcScript"
    groovy = "groovy"
    ruleset = "ruleset"


class RuntimePromptType(str, Enum):
    member = "member"
    members = "members"
    dimension = "dimension"
    numeric = "numeric"
    text = "text"
    date = "date"
    percent = "percent"
    smart_list = "smartList"
    cross_dimension = "crossDimension"


class RuntimePrompt(CamelModel):
    name: str
    prompt_text: str | None = None
    type: RuntimePromptType = RuntimePromptType.text
    dimension: str | None = None
    default_value: str | None = None
    required: bool = True
    choices: list[str] | None = None


class RuleSpecification(CamelModel):
    schema_version: str = RULE_SPEC_SCHEMA_VERSION
    name: str = Field(..., min_length=1, max_length=80)
    type: RuleType = RuleType.business_rule
    application: str
    cube: str
    purpose: str | None = None

    runtime_prompts: list[RuntimePrompt] = Field(default_factory=list)
    referenced_dimensions: list[str] = Field(default_factory=list)
    referenced_members: list[str] = Field(default_factory=list)
    referenced_variables: list[str] = Field(default_factory=list)
    form_associations: list[str] = Field(default_factory=list)

    # The draft calc/Groovy source. Deterministic code owns deployment; the model
    # may draft this text but it is never executed directly.
    source: str | None = None

    context_version: str | None = None
    generation: GenerationMetadata | None = None
