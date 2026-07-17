"""Request/response models for the artifact panel's inline prompt-editing.

The Claude-style artifacts panel lets a user edit a whole artifact, a single
table/grid, or a single cell by typing a natural-language instruction. These
DTOs carry that request over HTTP; the deterministic ``*_nlu`` modules apply the
change and re-render, so every edit is explainable and reproducible.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import CamelModel


class ArtifactKind(str, Enum):
    form_spec = "formSpec"
    report_spec = "reportSpec"


class EditScope(str, Enum):
    artifact = "artifact"
    table = "table"
    cell = "cell"


class PromptEditRequest(CamelModel):
    artifact_kind: ArtifactKind
    scope: EditScope = EditScope.artifact
    instruction: str = Field(..., min_length=1)
    spec: dict = Field(..., description="Current artifact spec (camelCase JSON)")
    grid_index: int = Field(0, description="Target grid for table/cell scope (reports)")
    row_label: str | None = Field(None, description="Target row label for cell scope")
    column_label: str | None = Field(None, description="Target column label for cell scope")


class PromptEditResult(CamelModel):
    changed: bool
    changes: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    spec: dict = Field(default_factory=dict, description="Updated spec (camelCase JSON)")
    preview: dict | None = Field(None, description="Fresh preview for the updated spec")
    validation: dict | None = Field(None, description="Fresh validation report (forms only)")
