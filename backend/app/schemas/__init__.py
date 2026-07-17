"""Canonical EPM Wizard schemas.

``CANONICAL_MODELS`` is the single source of truth for schema export. The build
pipeline turns these into JSON Schema -> TypeScript interfaces -> Zod schemas
(spec section 3), and a drift test fails CI if the committed frontend types fall
out of sync.
"""

from __future__ import annotations

from pydantic import BaseModel

from .api import (
    ArtifactOut,
    ConnectionResult,
    ContextVersionOut,
    ConversationOut,
    DeploymentOut,
    DiagnosticsReport,
    EnvironmentOut,
    ProjectOut,
    ProviderOut,
    RuleExecutionOut,
    SubsystemStatus,
)
from .architecture import (
    CellIntersection,
    CellMember,
    CrossDimArea,
    CrossDimSize,
    CubeArchitecture,
    CubeComparison,
    CubeComparisonRow,
    DimensionCoverageReport,
    DimensionHierarchy,
    DimensionNode,
    FormCoverage,
    HierarchyNode,
    MissingSuggestion,
)
from .artifact_edit import ArtifactKind, EditScope, PromptEditRequest, PromptEditResult
from .chat import (
    ChatAction,
    ChatBlock,
    ChatBlockType,
    ChatMessageIn,
    ConfirmationPayload,
    ConnectionStatusPayload,
    DiffPayload,
    DownloadableFilePayload,
    ErrorDiagnosticsPayload,
    MessageOut,
    MessageRole,
    ProcessStep,
    RuntimePromptFormPayload,
    StreamEvent,
    StreamEventType,
    ToolInvocationPayload,
)
from .common import (
    ArtifactType,
    AxisKind,
    CompletenessStatus,
    Confidence,
    EnvironmentClassification,
    OperationClass,
    SelectionType,
    Severity,
)
from .context import (
    ApplicationRecord,
    ContextManifest,
    ContextMode,
    CubeRecord,
    DimensionRecord,
    FormRecord,
    MemberMatch,
    MemberRecord,
    RuleRecord,
    VariableRecord,
)
from .deployment import (
    DeploymentOperation,
    DeploymentPlan,
    DeploymentReport,
    DeploymentStep,
    FormWorkflowState,
    RuleExecutionReport,
    RuleExecutionStatus,
)
from .form_preview import FormPreview, PreviewAxis, ResolvedMember
from .form_spec import (
    AxisMember,
    BusinessRuleAssociation,
    DisplayOptions,
    FormSpecification,
    MemberSelection,
    PromptMapping,
    ReferenceTemplate,
)
from .report_preview import (
    ReportCell,
    ReportGridPreview,
    ReportPreview,
    ReportRowPreview,
)
from .report_spec import (
    CellOverride,
    ConditionalRule,
    ReportChart,
    ReportGrid,
    ReportSpecification,
    SmartFormat,
)
from .rule_spec import RuleSpecification, RuleType, RuntimePrompt, RuntimePromptType
from .tools import SkillSpec, ToolCall, ToolResult, ToolSpec
from .validation import SizeEstimate, ValidationIssue, ValidationLayer, ValidationReport

# Models exported to the frontend as TypeScript + Zod. Order is stable so the
# generated file is deterministic.
CANONICAL_MODELS: dict[str, type[BaseModel]] = {
    # enums-as-models are handled by the generator via referenced schemas
    "FormSpecification": FormSpecification,
    "MemberSelection": MemberSelection,
    "AxisMember": AxisMember,
    "ReferenceTemplate": ReferenceTemplate,
    "DisplayOptions": DisplayOptions,
    "PromptMapping": PromptMapping,
    "BusinessRuleAssociation": BusinessRuleAssociation,
    "RuleSpecification": RuleSpecification,
    "RuntimePrompt": RuntimePrompt,
    "ContextManifest": ContextManifest,
    "ApplicationRecord": ApplicationRecord,
    "CubeRecord": CubeRecord,
    "DimensionRecord": DimensionRecord,
    "MemberRecord": MemberRecord,
    "FormRecord": FormRecord,
    "RuleRecord": RuleRecord,
    "VariableRecord": VariableRecord,
    "MemberMatch": MemberMatch,
    "ValidationReport": ValidationReport,
    "ValidationIssue": ValidationIssue,
    "SizeEstimate": SizeEstimate,
    "FormPreview": FormPreview,
    "PreviewAxis": PreviewAxis,
    "ResolvedMember": ResolvedMember,
    # Reports
    "ReportSpecification": ReportSpecification,
    "ReportGrid": ReportGrid,
    "ReportChart": ReportChart,
    "SmartFormat": SmartFormat,
    "ConditionalRule": ConditionalRule,
    "CellOverride": CellOverride,
    "ReportPreview": ReportPreview,
    "ReportGridPreview": ReportGridPreview,
    "ReportRowPreview": ReportRowPreview,
    "ReportCell": ReportCell,
    # Artifact panel editing
    "PromptEditRequest": PromptEditRequest,
    "PromptEditResult": PromptEditResult,
    "DeploymentPlan": DeploymentPlan,
    "DeploymentStep": DeploymentStep,
    "DeploymentReport": DeploymentReport,
    "RuleExecutionReport": RuleExecutionReport,
    "ToolSpec": ToolSpec,
    "ToolCall": ToolCall,
    "ToolResult": ToolResult,
    "SkillSpec": SkillSpec,
    "ChatBlock": ChatBlock,
    "ChatAction": ChatAction,
    "ProcessStep": ProcessStep,
    "MessageOut": MessageOut,
    "StreamEvent": StreamEvent,
    "ConfirmationPayload": ConfirmationPayload,
    "ConnectionStatusPayload": ConnectionStatusPayload,
    "DiffPayload": DiffPayload,
    "DownloadableFilePayload": DownloadableFilePayload,
    "ErrorDiagnosticsPayload": ErrorDiagnosticsPayload,
    "RuntimePromptFormPayload": RuntimePromptFormPayload,
    "ToolInvocationPayload": ToolInvocationPayload,
    # API DTOs
    "ProjectOut": ProjectOut,
    "EnvironmentOut": EnvironmentOut,
    "ProviderOut": ProviderOut,
    "ConversationOut": ConversationOut,
    "ContextVersionOut": ContextVersionOut,
    "ArtifactOut": ArtifactOut,
    "DeploymentOut": DeploymentOut,
    "RuleExecutionOut": RuleExecutionOut,
    "ConnectionResult": ConnectionResult,
    "DiagnosticsReport": DiagnosticsReport,
    "SubsystemStatus": SubsystemStatus,
    # Cube Architecture (4B)
    "CubeArchitecture": CubeArchitecture,
    "DimensionNode": DimensionNode,
    "FormCoverage": FormCoverage,
    "CellIntersection": CellIntersection,
    "CellMember": CellMember,
    "CubeComparison": CubeComparison,
    "CubeComparisonRow": CubeComparisonRow,
    "DimensionCoverageReport": DimensionCoverageReport,
    "MissingSuggestion": MissingSuggestion,
    "CrossDimSize": CrossDimSize,
    "CrossDimArea": CrossDimArea,
    "DimensionHierarchy": DimensionHierarchy,
    "HierarchyNode": HierarchyNode,
}

__all__ = [
    "CANONICAL_MODELS",
    # common
    "ArtifactType",
    "AxisKind",
    "CompletenessStatus",
    "Confidence",
    "EnvironmentClassification",
    "OperationClass",
    "SelectionType",
    "Severity",
    # form
    "FormSpecification",
    "MemberSelection",
    "AxisMember",
    "ReferenceTemplate",
    "DisplayOptions",
    "PromptMapping",
    "BusinessRuleAssociation",
    # rule
    "RuleSpecification",
    "RuntimePrompt",
    "RuleType",
    "RuntimePromptType",
    # reports
    "ReportSpecification",
    "ReportGrid",
    "ReportChart",
    "SmartFormat",
    "ConditionalRule",
    "CellOverride",
    "ReportPreview",
    "ReportGridPreview",
    "ReportRowPreview",
    "ReportCell",
    # artifact editing
    "PromptEditRequest",
    "PromptEditResult",
    "ArtifactKind",
    "EditScope",
    # context
    "ContextManifest",
    "ContextMode",
    "ApplicationRecord",
    "CubeRecord",
    "DimensionRecord",
    "MemberRecord",
    "FormRecord",
    "RuleRecord",
    "VariableRecord",
    "MemberMatch",
    # validation
    "ValidationReport",
    "ValidationIssue",
    "ValidationLayer",
    "SizeEstimate",
    # deployment
    "DeploymentPlan",
    "DeploymentReport",
    "DeploymentStep",
    "DeploymentOperation",
    "FormWorkflowState",
    "RuleExecutionReport",
    "RuleExecutionStatus",
    # tools
    "ToolSpec",
    "ToolCall",
    "ToolResult",
    "SkillSpec",
    # chat
    "ChatBlock",
    "ChatBlockType",
    "ChatAction",
    "ProcessStep",
    "MessageOut",
    "MessageRole",
    "ChatMessageIn",
    "StreamEvent",
    "StreamEventType",
]
