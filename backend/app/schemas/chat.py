"""Chat transport: typed inline blocks (spec section 8) and streaming events.

Blocks travel in a generic envelope (``ChatBlock`` = type + data) so the frontend
can switch on ``type``. Payload models below document the shape each block's
``data`` carries; the important ones embed the canonical artifact schemas.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import CamelModel, EnvironmentClassification, Severity


class ChatBlockType(str, Enum):
    markdown = "markdown"
    code = "code"
    form_preview = "formPreview"
    form_specification = "formSpecification"
    report_preview = "reportPreview"
    report_specification = "reportSpecification"
    rule_preview = "rulePreview"
    runtime_prompt_form = "runtimePromptForm"
    member_search_results = "memberSearchResults"
    context_summary = "contextSummary"
    validation_report = "validationReport"
    deployment_plan = "deploymentPlan"
    deployment_progress = "deploymentProgress"
    deployment_result = "deploymentResult"
    diff = "diff"
    confirmation = "confirmation"
    spreadsheet_preview = "spreadsheetPreview"
    snapshot_summary = "snapshotSummary"
    downloadable_file = "downloadableFile"
    error_diagnostics = "errorDiagnostics"
    connection_status = "connectionStatus"
    tool_invocation = "toolInvocation"
    process_steps = "processSteps"
    # Cube Architecture & Dimensionality Visualizer (spec 4B)
    cube_architecture = "cubeArchitecture"
    cell_intersection = "cellIntersection"
    cube_comparison = "cubeComparison"
    dimension_coverage = "dimensionCoverage"
    dimension_hierarchy = "dimensionHierarchy"


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class ChatBlock(CamelModel):
    """Generic typed block envelope carried inside an assistant message."""

    id: str
    type: ChatBlockType
    data: dict = Field(default_factory=dict)


class ChatAction(CamelModel):
    """A clickable option. Clicking records ``value`` as a normal user message
    (spec section 8), keeping the conversation reproducible."""

    key: str
    label: str
    value: str
    style: str = "secondary"  # primary | secondary | danger | ghost
    disabled: bool = False


class ProcessStepState(str, Enum):
    pending = "pending"
    active = "active"
    done = "done"
    error = "error"


class ProcessStep(CamelModel):
    key: str
    label: str
    state: ProcessStepState = ProcessStepState.pending


# --- Selected block payloads (documented shapes for ChatBlock.data) ----------


class ConfirmationPayload(CamelModel):
    prompt: str
    detail: str | None = None
    actions: list[ChatAction]
    severity: Severity = Severity.info


class ConnectionStatusPayload(CamelModel):
    connected: bool
    environment_name: str | None = None
    classification: EnvironmentClassification | None = None
    application: str | None = None
    context_status: str | None = None
    demo_mode: bool = True


class DiffPayload(CamelModel):
    title: str
    before: str
    after: str
    language: str = "json"


class DownloadableFilePayload(CamelModel):
    filename: str
    artifact_id: str
    media_type: str = "application/octet-stream"
    size_bytes: int | None = None
    checksum: str | None = None


class ToolInvocationPayload(CamelModel):
    tool: str
    operation_class: str
    status: str  # running | completed | failed
    summary: str | None = None
    detail: str | None = None
    error: str | None = None


class ErrorDiagnosticsPayload(CamelModel):
    category: str
    message: str
    likely_cause: str | None = None
    suggested_action: str | None = None
    technical_detail: str | None = None
    actions: list[ChatAction] = Field(default_factory=list)


class RuntimePromptFormPayload(CamelModel):
    rule_name: str
    application: str
    cube: str | None = None
    fields: list[dict] = Field(default_factory=list)  # rendered RuntimePrompt + resolved default
    prefilled_from: dict[str, str] = Field(default_factory=dict)
    actions: list[ChatAction] = Field(default_factory=list)


# --- Streaming (SSE) --------------------------------------------------------


class StreamEventType(str, Enum):
    title = "title"
    process = "process"
    token = "token"
    block = "block"
    tool_call = "toolCall"
    tool_result = "toolResult"
    message_saved = "messageSaved"
    error = "error"
    done = "done"
    usage = "usage"


class StreamEvent(CamelModel):
    type: StreamEventType
    data: dict = Field(default_factory=dict)

    def sse(self) -> str:
        import json

        payload = json.dumps(self.data, default=str)
        # `type` is already the enum value (use_enum_values=True)
        event_name = self.type.value if hasattr(self.type, "value") else self.type
        return f"event: {event_name}\ndata: {payload}\n\n"


# --- API request/response for chat ------------------------------------------


class ChatMessageIn(CamelModel):
    content: str
    attachments: list[str] = Field(default_factory=list)  # attachment ids
    parent_message_id: str | None = None  # for branch/edit


class MessageOut(CamelModel):
    id: str
    conversation_id: str
    role: MessageRole
    content: str
    blocks: list[ChatBlock] = Field(default_factory=list)
    process_steps: list[ProcessStep] = Field(default_factory=list)
    parent_id: str | None = None
    created_at: str
    model: str | None = None
    provider: str | None = None
    usage: dict | None = None
