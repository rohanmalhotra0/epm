"""Context metadata records and the portable .epwcontext manifest (spec 16-19)."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import (
    CONTEXT_MANIFEST_SCHEMA_VERSION,
    CamelModel,
    CompletenessStatus,
    Confidence,
    EnvironmentClassification,
)


class ContextMode(str, Enum):
    quick = "quick"
    deep = "deep"
    imported = "imported"


# --- Metadata records -------------------------------------------------------


class ApplicationRecord(CamelModel):
    name: str
    type: str = "planning"
    description: str | None = None


class CubeRecord(CamelModel):
    name: str
    application: str
    type: str = "aso/bso"
    description: str | None = None
    dimensions: list[str] = Field(default_factory=list)


class DimensionRecord(CamelModel):
    name: str
    application: str
    type: str = "generic"  # account | entity | scenario | version | period | generic | attribute
    cubes: list[str] = Field(default_factory=list)
    dense: bool | None = None


class MemberRecord(CamelModel):
    name: str
    dimension: str
    application: str
    alias: str | None = None
    parent: str | None = None
    children: list[str] = Field(default_factory=list)
    storage: str | None = None  # storeData | dynamicCalc | neverShare | label | sharedMember
    level: int | None = None
    formula: str | None = None
    data_type: str | None = None


class FormRecord(CamelModel):
    name: str
    application: str
    cube: str | None = None
    folder: str | None = None
    description: str | None = None
    # Optional normalised layout for reference-form cloning (spec section 23).
    definition: dict | None = None


class RuleRecord(CamelModel):
    name: str
    application: str
    cube: str | None = None
    type: str = "businessRule"
    runtime_prompts: list[str] = Field(default_factory=list)
    has_source: bool = False


class VariableRecord(CamelModel):
    name: str
    application: str
    scope: str = "substitution"  # substitution | user
    dimension: str | None = None
    value: str | None = None
    cube: str | None = None


class ContextSectionStatus(CamelModel):
    name: str
    status: CompletenessStatus
    count: int = 0
    note: str | None = None


# --- Manifest ---------------------------------------------------------------


class ContextManifest(CamelModel):
    format: str = "epwcontext"
    schema_version: str = CONTEXT_MANIFEST_SCHEMA_VERSION
    generated_at: str
    application: str
    environment_classification: EnvironmentClassification
    environment_fingerprint: str  # non-secret hash of URL+app+user
    mode: ContextMode
    counts: dict[str, int] = Field(default_factory=dict)
    included_files: list[str] = Field(default_factory=list)
    checksums: dict[str, str] = Field(default_factory=dict)
    sections: list[ContextSectionStatus] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    context_version: str


# --- Retrieval --------------------------------------------------------------


class MemberMatch(CamelModel):
    """A resolved member with provenance (spec section 19)."""

    query: str
    member: str
    alias: str | None = None
    dimension: str
    application: str
    cube: str | None = None
    parent: str | None = None
    source_artifact: str | None = None
    retrieval_method: str = "exact"  # exact | caseInsensitive | alias | prefix | hierarchy | fts | vector
    confidence: Confidence = Confidence.exact
    context_version: str | None = None
