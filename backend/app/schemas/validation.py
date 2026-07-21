"""Structured ValidationReport (spec section 26)."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import VALIDATION_REPORT_SCHEMA_VERSION, CamelModel, Severity


class ValidationLayer(str, Enum):
    schema = "schema"
    application = "application"
    axis = "axis"
    selection = "selection"
    runtime_prompt = "runtimePrompt"
    script = "script"
    display = "display"
    performance = "performance"
    security = "security"
    deployment = "deployment"


class ValidationIssue(CamelModel):
    layer: ValidationLayer
    severity: Severity
    code: str
    message: str
    path: str | None = None
    suggested_fix: str | None = None
    candidates: list[str] = Field(default_factory=list)


class SizeEstimate(CamelModel):
    row_combinations: int = 0
    column_combinations: int = 0
    page_combinations: int = 0
    total_cells: int = 0
    warning_threshold: int = 250_000


class ValidationReport(CamelModel):
    schema_version: str = VALIDATION_REPORT_SCHEMA_VERSION
    artifact_name: str
    valid: bool = True
    blocking: bool = False
    issues: list[ValidationIssue] = Field(default_factory=list)
    size_estimate: SizeEstimate | None = None
    resolved_member_counts: dict[str, int] = Field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.error.value]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.warning.value]

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)
        if issue.severity == Severity.error.value:
            self.valid = False
            self.blocking = True
