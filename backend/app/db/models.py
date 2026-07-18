"""ORM models — the full local persistence surface (spec section 9)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, IdMixin, TimestampMixin


class Project(IdMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    active_environment_id: Mapped[str | None] = mapped_column(String(32))
    active_context_version_id: Mapped[str | None] = mapped_column(String(32))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)

    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    environments: Mapped[list[EnvironmentProfile]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class EnvironmentProfile(IdMixin, TimestampMixin, Base):
    __tablename__ = "environment_profiles"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(400))
    username: Mapped[str | None] = mapped_column(String(200))
    auth_method: Mapped[str] = mapped_column(String(40), default="passwordInMemory")
    classification: Mapped[str] = mapped_column(String(20), default="development")
    preferred_application: Mapped[str | None] = mapped_column(String(120))
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    last_connected_at: Mapped[datetime | None] = mapped_column()
    last_context_refresh_at: Mapped[datetime | None] = mapped_column()
    remember_credentials: Mapped[bool] = mapped_column(Boolean, default=False)

    project: Mapped[Project] = relationship(back_populates="environments")


class ProviderProfile(IdMixin, TimestampMixin, Base):
    __tablename__ = "provider_profiles"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(40), default="mock")
    base_url: Mapped[str | None] = mapped_column(String(400))
    default_model: Mapped[str | None] = mapped_column(String(120))
    models: Mapped[list] = mapped_column(JSON, default=list)
    role_models: Mapped[dict] = mapped_column(JSON, default=dict)  # chat/fast/structured/code/embedding
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    has_key: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300), default="New chat")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    provider: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(120))
    draft: Mapped[str | None] = mapped_column(Text)
    last_message_at: Mapped[datetime | None] = mapped_column()
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(IdMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    blocks: Mapped[list] = mapped_column(JSON, default=list)
    process_steps: Mapped[list] = mapped_column(JSON, default=list)
    parent_id: Mapped[str | None] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean, default=True)  # branch selection
    provider: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(120))
    usage: Mapped[dict | None] = mapped_column(JSON)
    skill: Mapped[str | None] = mapped_column(String(60))

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Attachment(IdMixin, TimestampMixin, Base):
    __tablename__ = "attachments"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    conversation_id: Mapped[str | None] = mapped_column(String(32))
    message_id: Mapped[str | None] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(300))
    media_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[str] = mapped_column(String(600))
    checksum: Mapped[str | None] = mapped_column(String(80))
    text_extract: Mapped[str | None] = mapped_column(Text)


class Artifact(IdMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # formSpec | ruleSpec | xml | json | package | ...
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict | None] = mapped_column(JSON)  # for specs / reports
    content: Mapped[str | None] = mapped_column(Text)  # for text artifacts (xml/groovy/md)
    path: Mapped[str | None] = mapped_column(String(600))  # for binary artifacts (zip)
    checksum: Mapped[str | None] = mapped_column(String(80))
    context_version: Mapped[str | None] = mapped_column(String(60))
    source_conversation_id: Mapped[str | None] = mapped_column(String(32))
    source_message_id: Mapped[str | None] = mapped_column(String(32))
    parent_artifact_id: Mapped[str | None] = mapped_column(String(32))
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class ContextVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "context_versions"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    environment_id: Mapped[str | None] = mapped_column(String(32))
    application: Mapped[str] = mapped_column(String(120))
    label: Mapped[str] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(20), default="quick")
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    fingerprint: Mapped[str | None] = mapped_column(String(80))
    path: Mapped[str | None] = mapped_column(String(600))  # .epwcontext file
    active: Mapped[bool] = mapped_column(Boolean, default=False)

    records: Mapped[list[ContextRecord]] = relationship(
        back_populates="context_version", cascade="all, delete-orphan"
    )


class ContextRecord(IdMixin, Base):
    __tablename__ = "context_records"

    context_version_id: Mapped[str] = mapped_column(
        ForeignKey("context_versions.id", ondelete="CASCADE")
    )
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)  # application|cube|dimension|member|form|rule|variable
    name: Mapped[str] = mapped_column(String(300), index=True)
    dimension: Mapped[str | None] = mapped_column(String(120), index=True)
    application: Mapped[str | None] = mapped_column(String(120))
    cube: Mapped[str | None] = mapped_column(String(120))
    alias: Mapped[str | None] = mapped_column(String(300))
    parent: Mapped[str | None] = mapped_column(String(300))
    search_text: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    context_version: Mapped[ContextVersion] = relationship(back_populates="records")


class Deployment(IdMixin, TimestampMixin, Base):
    __tablename__ = "deployments"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    conversation_id: Mapped[str | None] = mapped_column(String(32))
    environment_name: Mapped[str | None] = mapped_column(String(120))
    classification: Mapped[str] = mapped_column(String(20), default="development")
    application: Mapped[str | None] = mapped_column(String(120))
    artifact_name: Mapped[str] = mapped_column(String(200))
    artifact_type: Mapped[str] = mapped_column(String(40), default="planningForm")
    operation: Mapped[str] = mapped_column(String(20), default="create")
    operation_class: Mapped[str] = mapped_column(String(20), default="modifying")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_note: Mapped[str | None] = mapped_column(String(400))
    context_version: Mapped[str | None] = mapped_column(String(60))
    spec_version: Mapped[str | None] = mapped_column(String(30))
    checksum: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime | None] = mapped_column()
    ended_at: Mapped[datetime | None] = mapped_column()
    job_result: Mapped[str | None] = mapped_column(String(60))
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_notes: Mapped[list] = mapped_column(JSON, default=list)
    backup_artifact_id: Mapped[str | None] = mapped_column(String(32))
    rollback_available: Mapped[bool] = mapped_column(Boolean, default=False)
    demo_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)


class RuleExecution(IdMixin, TimestampMixin, Base):
    __tablename__ = "rule_executions"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    conversation_id: Mapped[str | None] = mapped_column(String(32))
    rule_name: Mapped[str] = mapped_column(String(200))
    application: Mapped[str | None] = mapped_column(String(120))
    cube: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="ready")
    prompt_values: Mapped[dict] = mapped_column(JSON, default=dict)
    job_id: Mapped[str | None] = mapped_column(String(120))
    job_result: Mapped[str | None] = mapped_column(String(60))
    started_at: Mapped[datetime | None] = mapped_column()
    ended_at: Mapped[datetime | None] = mapped_column()
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    output: Mapped[str | None] = mapped_column(Text)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    demo_mode: Mapped[bool] = mapped_column(Boolean, default=True)


class Setting(IdMixin, TimestampMixin, Base):
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("scope", "project_id", "key", name="uq_setting"),)

    scope: Mapped[str] = mapped_column(String(20), default="global")  # global | project
    project_id: Mapped[str | None] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class AuditRecord(IdMixin, TimestampMixin, Base):
    __tablename__ = "audit_records"

    project_id: Mapped[str | None] = mapped_column(String(32), index=True)
    actor: Mapped[str] = mapped_column(String(120), default="local-user")
    action: Mapped[str] = mapped_column(String(120))
    operation_class: Mapped[str] = mapped_column(String(20), default="readOnly")
    target: Mapped[str | None] = mapped_column(String(300))
    environment: Mapped[str | None] = mapped_column(String(120))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class WorkflowState(IdMixin, TimestampMixin, Base):
    __tablename__ = "workflow_states"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    skill: Mapped[str] = mapped_column(String(60))
    state: Mapped[str] = mapped_column(String(60))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
