"""Canonical FormSpecification (spec section 21).

The language model *proposes* this structure; Pydantic validates it; tenant
metadata validators check it; deterministic renderers consume it. The model
never owns the deployable Oracle artifact.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import (
    _MEMBER_ANCHORED,
    FORM_SPEC_SCHEMA_VERSION,
    ArtifactType,
    CamelModel,
    SelectionType,
)


class MemberSelection(CamelModel):
    """A single member-selection expression.

    Modelled as one flat object (rather than a discriminated union) so the
    generated TypeScript stays a single editable interface. A validator enforces
    the fields required by each ``type``.
    """

    type: SelectionType
    member: str | None = Field(None, description="Anchor member for hierarchy functions")
    members: list[str] | None = Field(None, description="Explicit member list")
    start: str | None = Field(None, description="Range start member")
    end: str | None = Field(None, description="Range end member")
    offset_start: int | None = Field(None, description="relativeRange start offset")
    offset_end: int | None = Field(None, description="relativeRange end offset")
    variable: str | None = Field(None, description="Substitution or user variable name")
    attribute: str | None = Field(None, description="Attribute dimension member")
    named_selection: str | None = Field(None, description="Existing named member selection")

    @model_validator(mode="after")
    def _check_required(self) -> MemberSelection:
        t = SelectionType(self.type)
        if t in _MEMBER_ANCHORED and not self.member:
            raise ValueError(f"selection type '{t.value}' requires 'member'")
        if t is SelectionType.member_list and not self.members:
            raise ValueError("selection type 'memberList' requires non-empty 'members'")
        if t is SelectionType.range and not (self.start and self.end):
            raise ValueError("selection type 'range' requires 'start' and 'end'")
        if t is SelectionType.relative_range and (
            self.offset_start is None or self.offset_end is None
        ):
            raise ValueError("selection type 'relativeRange' requires 'offsetStart' and 'offsetEnd'")
        if t in (SelectionType.substitution_variable, SelectionType.user_variable) and not self.variable:
            raise ValueError(f"selection type '{t.value}' requires 'variable'")
        if t is SelectionType.attribute and not self.attribute:
            raise ValueError("selection type 'attribute' requires 'attribute'")
        if t is SelectionType.named_selection and not self.named_selection:
            raise ValueError("selection type 'namedSelection' requires 'namedSelection'")
        return self

    def describe(self) -> str:
        """Human-readable one-liner used in previews / diffs."""
        t = SelectionType(self.type)
        if t is SelectionType.member:
            return self.member or ""
        if t is SelectionType.member_list:
            return ", ".join(self.members or [])
        if t is SelectionType.range:
            return f"{self.start}:{self.end}"
        if t is SelectionType.relative_range:
            return f"relative[{self.offset_start}..{self.offset_end}]"
        if t in (SelectionType.substitution_variable, SelectionType.user_variable):
            return f"{{{self.variable}}}"
        if t is SelectionType.attribute:
            return f"attr={self.attribute}"
        if t is SelectionType.named_selection:
            return f"named:{self.named_selection}"
        # hierarchy functions
        pretty = {
            SelectionType.children: "children of {}",
            SelectionType.inclusive_children: "i-children of {}",
            SelectionType.descendants: "descendants of {}",
            SelectionType.inclusive_descendants: "i-descendants of {}",
            SelectionType.level_zero_descendants: "level-0 descendants of {}",
            SelectionType.ancestors: "ancestors of {}",
            SelectionType.inclusive_ancestors: "i-ancestors of {}",
            SelectionType.siblings: "siblings of {}",
        }
        return pretty.get(t, t.value).format(self.member)


class AxisMember(CamelModel):
    """A dimension placed on an axis with its selection and per-axis options."""

    dimension: str
    selection: MemberSelection
    suppress_missing: bool = False


class ReferenceTemplate(CamelModel):
    """Where the form is derived from (spec section 23)."""

    type: str = Field("existingForm", description="existingForm | projectTemplate | goldenTemplate | generic")
    name: str


class DisplayOptions(CamelModel):
    use_aliases: bool = True
    alias_table: str = "Default"
    hidden_members: list[str] = Field(default_factory=list)
    suppress_missing_rows: bool = True
    suppress_missing_columns: bool = False
    read_only: bool = False


class PromptMapping(CamelModel):
    prompt_name: str
    source: str = Field(
        "userEntered",
        description="formPov | formPage | gridMember | fixed | userEntered",
    )
    dimension: str | None = None
    value: str | None = None


class BusinessRuleAssociation(CamelModel):
    rule_name: str
    rule_type: str = "businessRule"
    association_type: str = Field(
        "manualLaunch",
        description="actionMenu | runAfterSave | runBeforeSave | manualLaunch | epmWizardOnly",
    )
    prompt_mappings: list[PromptMapping] = Field(default_factory=list)


class GenerationMetadata(CamelModel):
    renderer_version: str | None = None
    template_version: str | None = None
    generated_at: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None


class FormSpecification(CamelModel):
    schema_version: str = FORM_SPEC_SCHEMA_VERSION
    artifact_type: ArtifactType = ArtifactType.planning_form
    name: str = Field(..., min_length=1, max_length=80)
    description: str | None = None
    application: str
    cube: str
    folder: str = "EPM Wizard/Generated"
    reference_template: ReferenceTemplate | None = None

    pov: list[AxisMember] = Field(default_factory=list)
    pages: list[AxisMember] = Field(default_factory=list)
    rows: list[AxisMember] = Field(default_factory=list)
    columns: list[AxisMember] = Field(default_factory=list)

    display: DisplayOptions = Field(default_factory=DisplayOptions)
    business_rule_associations: list[BusinessRuleAssociation] = Field(default_factory=list)

    context_version: str | None = None
    generation: GenerationMetadata | None = None

    @model_validator(mode="after")
    def _structural(self) -> FormSpecification:
        # Rows and columns must be non-empty for a usable grid.
        if not self.rows:
            raise ValueError("form must have at least one row dimension")
        if not self.columns:
            raise ValueError("form must have at least one column dimension")
        # A dimension may appear on exactly one axis.
        seen: dict[str, str] = {}
        for kind, axis in (("pov", self.pov), ("pages", self.pages), ("rows", self.rows), ("columns", self.columns)):
            for am in axis:
                if am.dimension in seen:
                    raise ValueError(
                        f"dimension '{am.dimension}' placed on both '{seen[am.dimension]}' and '{kind}'"
                    )
                seen[am.dimension] = kind
        return self

    def all_axis_members(self) -> list[tuple[str, AxisMember]]:
        out: list[tuple[str, AxisMember]] = []
        for kind, axis in (("pov", self.pov), ("page", self.pages), ("row", self.rows), ("column", self.columns)):
            out.extend((kind, am) for am in axis)
        return out

    def dimensions_used(self) -> list[str]:
        return [am.dimension for _, am in self.all_axis_members()]
