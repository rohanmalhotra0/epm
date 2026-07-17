"""Tool + skill metadata and call envelopes (spec sections 35, 36).

Tools are narrow, typed, allowlisted operations. The model may only select from
the allowed set; application code validates every argument. The model never maps
to a generic shell/command endpoint.
"""

from __future__ import annotations

from pydantic import Field

from .common import CamelModel, OperationClass


class ToolSpec(CamelModel):
    name: str
    description: str
    operation_class: OperationClass = OperationClass.read_only
    read_only: bool = True
    modifies_oracle: bool = False
    required_role: str = "user"
    requires_approval: bool = False
    timeout_s: int = 60
    retryable: bool = False
    audit: bool = True


class ToolCall(CamelModel):
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolResult(CamelModel):
    name: str
    ok: bool = True
    data: dict = Field(default_factory=dict)
    error: str | None = None
    error_category: str | None = None
    operation_class: OperationClass = OperationClass.read_only
    duration_ms: int | None = None


class SkillSpec(CamelModel):
    name: str  # e.g. "/forms"
    description: str
    intent_examples: list[str] = Field(default_factory=list)
    required_context: bool = False
    allowed_tools: list[str] = Field(default_factory=list)
    approval_required: bool = False
    version: str = "1.0.0"
