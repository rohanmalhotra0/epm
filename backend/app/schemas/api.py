"""API request/response DTOs (camelCase). Not artifact schemas, but still
generated into the frontend types + guarded by the drift test."""

from __future__ import annotations

from .common import CamelModel, EnvironmentClassification

# --- Projects ---------------------------------------------------------------


class ProjectCreate(CamelModel):
    name: str
    description: str | None = None


class ProjectOut(CamelModel):
    id: str
    name: str
    description: str | None = None
    is_default: bool = False
    active_environment_id: str | None = None
    active_context_version_id: str | None = None
    settings: dict = {}
    conversation_count: int = 0
    created_at: str
    updated_at: str


# --- Environments -----------------------------------------------------------


class EnvironmentCreate(CamelModel):
    name: str
    base_url: str | None = None
    username: str | None = None
    auth_method: str = "passwordInMemory"
    classification: EnvironmentClassification = EnvironmentClassification.development
    preferred_application: str | None = None
    demo: bool = True


class EnvironmentOut(CamelModel):
    id: str
    project_id: str
    name: str
    base_url: str | None = None
    username: str | None = None
    auth_method: str = "passwordInMemory"
    classification: EnvironmentClassification
    preferred_application: str | None = None
    demo: bool = True
    connected: bool = False
    last_connected_at: str | None = None
    last_context_refresh_at: str | None = None


class ConnectRequest(CamelModel):
    password: str | None = None
    remember: bool = False


class ConnectionResult(CamelModel):
    connected: bool
    environment_id: str
    message: str
    application: str | None = None
    detail: str | None = None
    diagnostics: dict = {}


# --- Providers --------------------------------------------------------------


class ProviderCreate(CamelModel):
    name: str
    provider_type: str = "mock"
    base_url: str | None = None
    default_model: str | None = None
    api_key: str | None = None
    role_models: dict = {}


class ProviderOut(CamelModel):
    id: str
    name: str
    provider_type: str
    base_url: str | None = None
    default_model: str | None = None
    models: list[str] = []
    role_models: dict = {}
    enabled: bool = True
    has_key: bool = False


# --- Conversations ----------------------------------------------------------


class ConversationCreate(CamelModel):
    title: str | None = None
    project_id: str | None = None


class ConversationOut(CamelModel):
    id: str
    project_id: str
    title: str
    pinned: bool = False
    archived: bool = False
    provider: str | None = None
    model: str | None = None
    last_message_at: str | None = None
    message_count: int = 0
    created_at: str
    updated_at: str


class ConversationUpdate(CamelModel):
    title: str | None = None
    pinned: bool | None = None
    archived: bool | None = None
    draft: str | None = None


# --- Context / Artifacts / Deployments --------------------------------------


class ContextVersionOut(CamelModel):
    id: str
    project_id: str
    application: str
    label: str
    mode: str
    counts: dict = {}
    active: bool = False
    manifest: dict = {}
    created_at: str


class ArtifactOut(CamelModel):
    id: str
    project_id: str
    kind: str
    name: str
    version: int = 1
    checksum: str | None = None
    context_version: str | None = None
    has_content: bool = False
    has_file: bool = False
    payload: dict | None = None
    metadata: dict = {}
    created_at: str
    updated_at: str


class DeploymentOut(CamelModel):
    id: str
    project_id: str
    conversation_id: str | None = None
    environment_name: str | None = None
    classification: str
    application: str | None = None
    artifact_name: str
    artifact_type: str
    operation: str
    operation_class: str
    approved: bool
    success: bool
    verified: bool
    demo_mode: bool
    checksum: str | None = None
    context_version: str | None = None
    rollback_available: bool = False
    report: dict = {}
    errors: list[str] = []
    warnings: list[str] = []
    created_at: str


class RuleExecutionOut(CamelModel):
    id: str
    project_id: str
    rule_name: str
    application: str | None = None
    cube: str | None = None
    status: str
    prompt_values: dict = {}
    job_result: str | None = None
    duration_ms: int | None = None
    output: str | None = None
    demo_mode: bool = True
    created_at: str


# --- Diagnostics ------------------------------------------------------------


class SubsystemStatus(CamelModel):
    name: str
    status: str  # ok | warn | error | unavailable
    detail: str | None = None


class DiagnosticsReport(CamelModel):
    app_version: str
    subsystems: list[SubsystemStatus] = []
    storage_path: str
    active_provider: str | None = None
    active_model: str | None = None
    demo_mode: bool = True
    schema_versions: dict = {}
    feature_flags: dict = {}
    redaction_healthy: bool = True


class DiagnosticLogEntry(CamelModel):
    """One captured log line from the in-memory ring buffer."""

    ts: str | None = None
    level: str | None = None
    event: str | None = None
    logger: str | None = None
    data: dict = {}


class DiagnosticLogsOut(CamelModel):
    logs: list[DiagnosticLogEntry] = []


# --- Global search ----------------------------------------------------------


class SearchResultOut(CamelModel):
    """One project-wide search hit (conversation title, message or artifact)."""

    type: str  # conversation | message | artifact
    id: str
    conversation_id: str | None = None  # set for message hits
    title: str
    snippet: str
    updated_at: str | None = None


class SearchResponse(CamelModel):
    results: list[SearchResultOut] = []


# --- Skill catalog ----------------------------------------------------------


class SkillInfoOut(CamelModel):
    name: str
    title: str
    description: str
    examples: list[str] = []


class SkillCatalogOut(CamelModel):
    skills: list[SkillInfoOut] = []


# --- Backups / disk usage (diagnostics) --------------------------------------


class BackupFileOut(CamelModel):
    filename: str
    size_bytes: int
    created_at: str


class ProjectDiskUsageOut(CamelModel):
    project_id: str
    name: str
    artifact_bytes: int = 0
    artifact_count: int = 0


class DiskUsageOut(CamelModel):
    db_bytes: int = 0
    backups_bytes: int = 0
    projects: list[ProjectDiskUsageOut] = []


# --- Impact analysis ---------------------------------------------------------


class ImpactReferenceOut(CamelModel):
    artifact_id: str
    artifact_type: str
    artifact_name: str
    locations: list[str] = []


class ImpactAnalysisOut(CamelModel):
    query: str
    references: list[ImpactReferenceOut] = []
