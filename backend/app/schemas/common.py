"""Shared building blocks for every canonical EPM Wizard schema.

Python + Pydantic own the canonical artifact schemas (spec section 3). Every
model here serialises to **camelCase** JSON so the generated TypeScript / Zod is
idiomatic on the frontend, while Python code keeps snake_case attributes.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# Canonical schema versions. Bump when a model changes shape in a breaking way.
FORM_SPEC_SCHEMA_VERSION = "1.0.0"
RULE_SPEC_SCHEMA_VERSION = "1.0.0"
CONTEXT_MANIFEST_SCHEMA_VERSION = "1.0.0"
DEPLOYMENT_PLAN_SCHEMA_VERSION = "1.0.0"
VALIDATION_REPORT_SCHEMA_VERSION = "1.0.0"


class CamelModel(BaseModel):
    """Base for all canonical models: camelCase JSON, snake_case Python."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        use_enum_values=True,
        str_strip_whitespace=True,
        extra="forbid",
    )


class EnvironmentClassification(str, Enum):
    """DEV / TEST / PROD gating (spec sections 13, 39)."""

    development = "development"
    test = "test"
    production = "production"


class ArtifactType(str, Enum):
    planning_form = "planningForm"
    business_rule = "businessRule"
    calc_script = "calcScript"
    groovy_rule = "groovyRule"
    ruleset = "ruleset"
    context_package = "contextPackage"


class AxisKind(str, Enum):
    pov = "pov"
    page = "page"
    row = "row"
    column = "column"


class SelectionType(str, Enum):
    """Supported member-selection functions (spec section 21)."""

    member = "member"
    member_list = "memberList"
    children = "children"
    inclusive_children = "inclusiveChildren"
    descendants = "descendants"
    inclusive_descendants = "inclusiveDescendants"
    level_zero_descendants = "levelZeroDescendants"
    ancestors = "ancestors"
    inclusive_ancestors = "inclusiveAncestors"
    siblings = "siblings"
    range = "range"
    relative_range = "relativeRange"
    substitution_variable = "substitutionVariable"
    user_variable = "userVariable"
    attribute = "attribute"
    pov_reference = "povReference"
    page_reference = "pageReference"
    named_selection = "namedSelection"


# Selection types that require a single anchor `member`.
_MEMBER_ANCHORED = {
    SelectionType.member,
    SelectionType.children,
    SelectionType.inclusive_children,
    SelectionType.descendants,
    SelectionType.inclusive_descendants,
    SelectionType.level_zero_descendants,
    SelectionType.ancestors,
    SelectionType.inclusive_ancestors,
    SelectionType.siblings,
}


class Severity(str, Enum):
    error = "error"
    warning = "warning"
    info = "info"


class Confidence(str, Enum):
    exact = "exact"
    high = "high"
    medium = "medium"
    low = "low"


class CompletenessStatus(str, Enum):
    complete = "complete"
    partial = "partial"
    derived = "derived"
    unavailable = "unavailable"
    not_requested = "notRequested"


class OperationClass(str, Enum):
    """Connector / tool risk classification (spec section 14)."""

    read_only = "readOnly"
    execution = "execution"
    modifying = "modifying"
    destructive = "destructive"
