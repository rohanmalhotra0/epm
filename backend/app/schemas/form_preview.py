"""Interactive form-preview model (spec section 24). Rendered inside chat as a
``formPreview`` block. Produced deterministically from a FormSpecification +
tenant metadata — never by the model."""

from __future__ import annotations

from pydantic import Field

from .common import CamelModel
from .validation import SizeEstimate


class ResolvedMember(CamelModel):
    name: str
    alias: str | None = None


class PreviewAxis(CamelModel):
    kind: str  # pov | page | row | column
    dimension: str
    selection_summary: str
    resolved_count: int = 0
    sample_members: list[ResolvedMember] = Field(default_factory=list)
    suppress_missing: bool = False
    truncated: bool = False


class FormPreview(CamelModel):
    form_name: str
    application: str
    cube: str
    folder: str
    validation_status: str = "valid"  # valid | warnings | invalid
    reference_template: str | None = None
    use_aliases: bool = True
    hidden_members: list[str] = Field(default_factory=list)
    rule_associations: list[str] = Field(default_factory=list)

    pov: list[PreviewAxis] = Field(default_factory=list)
    pages: list[PreviewAxis] = Field(default_factory=list)
    rows: list[PreviewAxis] = Field(default_factory=list)
    columns: list[PreviewAxis] = Field(default_factory=list)

    # Small materialised grid for display.
    row_labels: list[str] = Field(default_factory=list)
    column_labels: list[str] = Field(default_factory=list)
    rows_truncated: bool = False
    columns_truncated: bool = False

    size_estimate: SizeEstimate | None = None
