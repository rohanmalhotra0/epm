"""DeploymentPlan, DeploymentReport, and workflow state machines.

Covers spec sections 20 (form state machine), 29 (deployment pipeline),
32 (rule execution), 38 (deployment history).
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import (
    DEPLOYMENT_PLAN_SCHEMA_VERSION,
    ArtifactType,
    CamelModel,
    EnvironmentClassification,
    OperationClass,
)


class FormWorkflowState(str, Enum):
    request_received = "REQUEST_RECEIVED"
    requirements_collecting = "REQUIREMENTS_COLLECTING"
    context_searching = "CONTEXT_SEARCHING"
    reference_form_selecting = "REFERENCE_FORM_SELECTING"
    specification_drafted = "SPECIFICATION_DRAFTED"
    validating = "VALIDATING"
    preview_ready = "PREVIEW_READY"
    awaiting_user_changes = "AWAITING_USER_CHANGES"
    awaiting_approval = "AWAITING_APPROVAL"
    building_artifact = "BUILDING_ARTIFACT"
    deploying = "DEPLOYING"
    verifying = "VERIFYING"
    completed = "COMPLETED"
    # failure states
    context_required = "CONTEXT_REQUIRED"
    member_not_found = "MEMBER_NOT_FOUND"
    ambiguous_member = "AMBIGUOUS_MEMBER"
    invalid_specification = "INVALID_SPECIFICATION"
    package_build_failed = "PACKAGE_BUILD_FAILED"
    deployment_failed = "DEPLOYMENT_FAILED"
    verification_failed = "VERIFICATION_FAILED"
    cancelled = "CANCELLED"


class DeploymentStepStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class DeploymentOperation(str, Enum):
    create = "create"
    update = "update"
    replace = "replace"
    delete = "delete"


class DeploymentStep(CamelModel):
    key: str
    label: str
    status: DeploymentStepStatus = DeploymentStepStatus.pending
    detail: str | None = None
    started_at: str | None = None
    ended_at: str | None = None


class DeploymentPlan(CamelModel):
    schema_version: str = DEPLOYMENT_PLAN_SCHEMA_VERSION
    artifact_type: ArtifactType
    artifact_name: str
    application: str
    cube: str | None = None
    folder: str | None = None
    environment_name: str
    environment_classification: EnvironmentClassification
    operation: DeploymentOperation
    operation_class: OperationClass = OperationClass.modifying
    overwrites_existing: bool = False
    backup_required: bool = False
    validation_passed: bool = False
    context_fresh: bool = True
    demo_mode: bool = True
    requires_confirmation_phrase: bool = False
    steps: list[DeploymentStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DeploymentReport(CamelModel):
    plan: DeploymentPlan
    state: FormWorkflowState = FormWorkflowState.deploying
    success: bool = False
    verified: bool = False
    verification_notes: list[str] = Field(default_factory=list)
    job_id: str | None = None
    job_result: str | None = None
    package_checksum: str | None = None
    backup_artifact: str | None = None
    rollback_available: bool = False
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --- Rule execution (spec section 32) ---------------------------------------


class RuleExecutionStatus(str, Enum):
    waiting_for_prompts = "waitingForPrompts"
    ready = "ready"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    unknown = "unknown"


class RuleExecutionReport(CamelModel):
    rule_name: str
    application: str
    cube: str | None = None
    status: RuleExecutionStatus = RuleExecutionStatus.ready
    prompt_values: dict[str, str] = Field(default_factory=dict)
    job_id: str | None = None
    job_result: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    output: str | None = None
    errors: list[str] = Field(default_factory=list)
