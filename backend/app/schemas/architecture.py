"""Cube Architecture & Dimensionality Visualizer models (spec 4B).

All data here is derived deterministically from real tenant/context metadata.
Nothing is invented: an unknown dimension is labelled "custom", never guessed
into a standard type.
"""

from __future__ import annotations

from pydantic import Field

from .common import CamelModel
from .validation import SizeEstimate


class DimensionNode(CamelModel):
    name: str
    alias: str | None = None
    type: str = "custom"  # account | entity | scenario | version | period | years | currency | custom
    group: str = "custom"  # time | context | organization | financial | custom
    member_count: int | None = None
    root_members: list[str] = Field(default_factory=list)
    selected_member: str | None = None
    selection_summary: str | None = None
    used_on_axis: str | None = None  # pov | pages | rows | columns | None
    status: str = "available"  # available | selected | defaulted | missing | duplicate | invalid


class FormCoverage(CamelModel):
    pov: list[dict] = Field(default_factory=list)
    pages: list[dict] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)
    columns: list[dict] = Field(default_factory=list)
    implicit_or_default: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    duplicate: list[str] = Field(default_factory=list)


class CubeArchitecture(CamelModel):
    application: str
    cube: str
    cube_type: str | None = None
    dimension_count: int = 0
    dimensions: list[DimensionNode] = Field(default_factory=list)
    form_name: str | None = None
    form_coverage: FormCoverage | None = None


class CellMember(CamelModel):
    dimension: str
    member: str
    source: str = "default"  # selected | pov | page | row | column | variable | default


class CellIntersection(CamelModel):
    application: str
    cube: str
    members: list[CellMember] = Field(default_factory=list)
    expression: str = ""
    note: str = "Structural only — no data value is retrieved."


class CubeComparisonRow(CamelModel):
    dimension: str
    in_a: bool
    in_b: bool
    detail_a: str | None = None
    detail_b: str | None = None


class CubeComparison(CamelModel):
    application: str
    cube_a: str
    cube_b: str
    rows: list[CubeComparisonRow] = Field(default_factory=list)
    shared: int = 0
    only_a: list[str] = Field(default_factory=list)
    only_b: list[str] = Field(default_factory=list)


class MissingSuggestion(CamelModel):
    dimension: str
    suggested_handling: str


class DimensionCoverageReport(CamelModel):
    cube: str
    valid: bool = True
    covered_dimensions: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
    duplicate_dimensions: list[str] = Field(default_factory=list)
    invalid_selections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggestions: list[MissingSuggestion] = Field(default_factory=list)


class CrossDimArea(CamelModel):
    area: str  # rows | columns | pages
    detail: str
    count: int


class CrossDimSize(CamelModel):
    cube: str
    areas: list[CrossDimArea] = Field(default_factory=list)
    total_potential_cells: int = 0
    size_estimate: SizeEstimate | None = None
    warning: str | None = None
    label: str = "Potential form intersections"


class HierarchyNode(CamelModel):
    name: str
    alias: str | None = None
    parent: str | None = None
    depth: int = 0
    has_children: bool = False


class DimensionHierarchy(CamelModel):
    application: str
    dimension: str
    root: str
    nodes: list[HierarchyNode] = Field(default_factory=list)
    truncated: bool = False
    cap: int = 50
