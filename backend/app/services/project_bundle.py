"""Project export/import bundles (portable zip, documented JSON, no secrets).

Bundle layout (format ``epmwizard-project-bundle``, version 1.0.0):

    manifest.json           format/version/appVersion/exportedAt + per-file sha256 checksums
    project.json            the project row (camelCase)
    environments.json       environment profiles WITHOUT secrets (passwords live in the
                            local secret store and are never exported)
    conversations.json      conversation rows
    messages.json           message rows
    artifacts.json          artifact rows (spec payloads + text content inline)
    context_versions.json   context version rows
    context_records.json    context record rows
    deployments.json        deployment history rows
    rule_executions.json    rule execution history rows
    blobs/<artifactId>      binary package files referenced by artifact rows (optional)

Import validates the manifest and every checksum, only ever reads the member
names the manifest declares (guarding against zip-slip / smuggled members),
enforces size caps, then re-creates the project under entirely fresh IDs with
all foreign keys remapped.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.base import new_id, utcnow
from ..db.models import (
    Artifact,
    ContextRecord,
    ContextVersion,
    Conversation,
    Deployment,
    EnvironmentProfile,
    Message,
    Project,
    RuleExecution,
)
from . import iso

BUNDLE_FORMAT = "epmwizard-project-bundle"
BUNDLE_FORMAT_VERSION = "1.0.0"

# Hard safety caps for imported bundles.
MAX_BUNDLE_BYTES = 50 * 1024 * 1024  # compressed upload
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # declared decompressed total

_FIXED_DT = (1980, 1, 1, 0, 0, 0)

_JSON_MEMBERS = (
    "project.json",
    "environments.json",
    "conversations.json",
    "messages.json",
    "artifacts.json",
    "context_versions.json",
    "context_records.json",
    "deployments.json",
    "rule_executions.json",
)


class BundleError(ValueError):
    """A malformed or unsafe bundle. Routes surface this as HTTP 400."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _dt_or_now(value: object) -> datetime:
    return _dt(value) or utcnow()


# --- Export ------------------------------------------------------------------


def _project_row(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "settings": p.settings or {},
        "activeEnvironmentId": p.active_environment_id,
        "activeContextVersionId": p.active_context_version_id,
        "createdAt": iso(p.created_at),
        "updatedAt": iso(p.updated_at),
    }


def _environment_row(e: EnvironmentProfile) -> dict:
    # Deliberately excludes anything secret-adjacent: passwords/keys are held in
    # the local secret store (never in SQLite) and are NOT part of a bundle.
    return {
        "id": e.id,
        "name": e.name,
        "baseUrl": e.base_url,
        "username": e.username,
        "authMethod": e.auth_method,
        "classification": e.classification,
        "preferredApplication": e.preferred_application,
        "demo": e.demo,
        "createdAt": iso(e.created_at),
        "updatedAt": iso(e.updated_at),
    }


def _conversation_row(c: Conversation) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "pinned": c.pinned,
        "archived": c.archived,
        "provider": c.provider,
        "model": c.model,
        "draft": c.draft,
        "lastMessageAt": iso(c.last_message_at),
        "metadata": c.metadata_ or {},
        "createdAt": iso(c.created_at),
        "updatedAt": iso(c.updated_at),
    }


def _message_row(m: Message) -> dict:
    return {
        "id": m.id,
        "conversationId": m.conversation_id,
        "role": m.role,
        "content": m.content,
        "blocks": m.blocks or [],
        "processSteps": m.process_steps or [],
        "parentId": m.parent_id,
        "active": m.active,
        "provider": m.provider,
        "model": m.model,
        "usage": m.usage,
        "skill": m.skill,
        "createdAt": iso(m.created_at),
        "updatedAt": iso(m.updated_at),
    }


def _artifact_row(a: Artifact, has_blob: bool) -> dict:
    return {
        "id": a.id,
        "kind": a.kind,
        "name": a.name,
        "version": a.version,
        "payload": a.payload,
        "content": a.content,
        "hasFile": has_blob,
        "checksum": a.checksum,
        "contextVersion": a.context_version,
        "sourceConversationId": a.source_conversation_id,
        "sourceMessageId": a.source_message_id,
        "parentArtifactId": a.parent_artifact_id,
        "metadata": a.metadata_ or {},
        "createdAt": iso(a.created_at),
        "updatedAt": iso(a.updated_at),
    }


def _context_version_row(cv: ContextVersion) -> dict:
    return {
        "id": cv.id,
        "environmentId": cv.environment_id,
        "application": cv.application,
        "label": cv.label,
        "mode": cv.mode,
        "manifest": cv.manifest or {},
        "counts": cv.counts or {},
        "fingerprint": cv.fingerprint,
        "active": cv.active,
        "createdAt": iso(cv.created_at),
        "updatedAt": iso(cv.updated_at),
    }


def _context_record_row(r: ContextRecord) -> dict:
    return {
        "id": r.id,
        "contextVersionId": r.context_version_id,
        "kind": r.kind,
        "name": r.name,
        "dimension": r.dimension,
        "application": r.application,
        "cube": r.cube,
        "alias": r.alias,
        "parent": r.parent,
        "searchText": r.search_text or "",
        "data": r.data or {},
    }


def _deployment_row(d: Deployment) -> dict:
    return {
        "id": d.id,
        "conversationId": d.conversation_id,
        "environmentName": d.environment_name,
        "classification": d.classification,
        "application": d.application,
        "artifactName": d.artifact_name,
        "artifactType": d.artifact_type,
        "operation": d.operation,
        "operationClass": d.operation_class,
        "approved": d.approved,
        "approvalNote": d.approval_note,
        "contextVersion": d.context_version,
        "specVersion": d.spec_version,
        "checksum": d.checksum,
        "startedAt": iso(d.started_at),
        "endedAt": iso(d.ended_at),
        "jobResult": d.job_result,
        "success": d.success,
        "verified": d.verified,
        "verificationNotes": d.verification_notes or [],
        "backupArtifactId": d.backup_artifact_id,
        "rollbackAvailable": d.rollback_available,
        "demoMode": d.demo_mode,
        "report": d.report or {},
        "errors": d.errors or [],
        "warnings": d.warnings or [],
        "createdAt": iso(d.created_at),
        "updatedAt": iso(d.updated_at),
    }


def _rule_execution_row(r: RuleExecution) -> dict:
    return {
        "id": r.id,
        "conversationId": r.conversation_id,
        "ruleName": r.rule_name,
        "application": r.application,
        "cube": r.cube,
        "status": r.status,
        "promptValues": r.prompt_values or {},
        "jobId": r.job_id,
        "jobResult": r.job_result,
        "startedAt": iso(r.started_at),
        "endedAt": iso(r.ended_at),
        "durationMs": r.duration_ms,
        "output": r.output,
        "errors": r.errors or [],
        "demoMode": r.demo_mode,
        "createdAt": iso(r.created_at),
        "updatedAt": iso(r.updated_at),
    }


def export_project(session: Session, project: Project) -> bytes:
    """Build the bundle zip for a project. Returns the zip bytes."""
    envs = (
        session.query(EnvironmentProfile)
        .filter_by(project_id=project.id)
        .order_by(EnvironmentProfile.created_at.asc(), EnvironmentProfile.id.asc())
        .all()
    )
    convs = (
        session.query(Conversation)
        .filter_by(project_id=project.id)
        .order_by(Conversation.created_at.asc(), Conversation.id.asc())
        .all()
    )
    conv_ids = [c.id for c in convs]
    msgs = (
        session.query(Message)
        .filter(Message.conversation_id.in_(conv_ids))
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
        if conv_ids
        else []
    )
    arts = (
        session.query(Artifact)
        .filter_by(project_id=project.id)
        .order_by(Artifact.created_at.asc(), Artifact.id.asc())
        .all()
    )
    cvs = (
        session.query(ContextVersion)
        .filter_by(project_id=project.id)
        .order_by(ContextVersion.created_at.asc(), ContextVersion.id.asc())
        .all()
    )
    cv_ids = [cv.id for cv in cvs]
    recs = (
        session.query(ContextRecord)
        .filter(ContextRecord.context_version_id.in_(cv_ids))
        .order_by(ContextRecord.id.asc())
        .all()
        if cv_ids
        else []
    )
    deps = (
        session.query(Deployment)
        .filter_by(project_id=project.id)
        .order_by(Deployment.created_at.asc(), Deployment.id.asc())
        .all()
    )
    rexes = (
        session.query(RuleExecution)
        .filter_by(project_id=project.id)
        .order_by(RuleExecution.created_at.asc(), RuleExecution.id.asc())
        .all()
    )

    blobs: dict[str, bytes] = {}
    artifact_rows = []
    for a in arts:
        data: bytes | None = None
        if a.path:
            p = Path(a.path)
            if p.exists() and p.is_file():
                data = p.read_bytes()
        if data is not None:
            blobs[f"blobs/{a.id}"] = data
        artifact_rows.append(_artifact_row(a, has_blob=data is not None))

    members: dict[str, bytes] = {
        "project.json": _dump(_project_row(project)),
        "environments.json": _dump([_environment_row(e) for e in envs]),
        "conversations.json": _dump([_conversation_row(c) for c in convs]),
        "messages.json": _dump([_message_row(m) for m in msgs]),
        "artifacts.json": _dump(artifact_rows),
        "context_versions.json": _dump([_context_version_row(cv) for cv in cvs]),
        "context_records.json": _dump([_context_record_row(r) for r in recs]),
        "deployments.json": _dump([_deployment_row(d) for d in deps]),
        "rule_executions.json": _dump([_rule_execution_row(r) for r in rexes]),
        **blobs,
    }

    settings = get_settings()
    manifest = {
        "format": BUNDLE_FORMAT,
        "bundleFormatVersion": BUNDLE_FORMAT_VERSION,
        "appVersion": settings.version,
        "exportedAt": iso(utcnow()),
        "projectId": project.id,
        "projectName": project.name,
        "files": sorted(members.keys()),
        "checksums": {name: _sha256(data) for name, data in sorted(members.items())},
    }
    members["manifest.json"] = _dump(manifest)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(members.keys()):
            info = zipfile.ZipInfo(filename=name, date_time=_FIXED_DT)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, members[name])
    return buffer.getvalue()


def _dump(obj: object) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


# --- Import ------------------------------------------------------------------


def _valid_member_name(name: str) -> bool:
    if name in _JSON_MEMBERS:
        return True
    if name.startswith("blobs/"):
        blob_id = name[len("blobs/") :]
        return blob_id.isalnum() and 0 < len(blob_id) <= 64
    return False


def _read_manifest(zf: zipfile.ZipFile) -> dict:
    try:
        raw = zf.read("manifest.json")
    except KeyError as exc:
        raise BundleError("bundle is missing manifest.json") from exc
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BundleError("manifest.json is not valid JSON") from exc
    if not isinstance(manifest, dict):
        raise BundleError("manifest.json must be a JSON object")
    if manifest.get("format") != BUNDLE_FORMAT:
        raise BundleError(f"unsupported bundle format (expected '{BUNDLE_FORMAT}')")
    version = str(manifest.get("bundleFormatVersion", ""))
    if not version.startswith("1."):
        raise BundleError(f"unsupported bundle format version '{version}'")
    files = manifest.get("files")
    checksums = manifest.get("checksums")
    if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
        raise BundleError("manifest 'files' must be a list of member names")
    if not isinstance(checksums, dict):
        raise BundleError("manifest 'checksums' must be an object")
    for name in files:
        if not _valid_member_name(name):
            raise BundleError(f"unexpected bundle member name '{name}'")
    return manifest


def _load_members(zip_bytes: bytes) -> dict[str, bytes]:
    """Open, validate and read only the manifest-declared members."""
    if len(zip_bytes) == 0:
        raise BundleError("uploaded bundle is empty")
    if len(zip_bytes) > MAX_BUNDLE_BYTES:
        raise BundleError(f"bundle exceeds the maximum size of {MAX_BUNDLE_BYTES} bytes")
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise BundleError("uploaded file is not a valid zip archive") from exc
    with zf:
        declared = sum(i.file_size for i in zf.infolist())
        if declared > MAX_UNCOMPRESSED_BYTES:
            raise BundleError("bundle decompressed size exceeds the allowed maximum")
        manifest = _read_manifest(zf)
        present = set(zf.namelist())
        members: dict[str, bytes] = {"manifest.json": zf.read("manifest.json")}
        for name in manifest["files"]:
            if name not in present:
                raise BundleError(f"bundle member '{name}' listed in manifest is missing")
            data = zf.read(name)
            expected = manifest["checksums"].get(name)
            if not isinstance(expected, str):
                raise BundleError(f"manifest has no checksum for '{name}'")
            if _sha256(data) != expected:
                raise BundleError(f"checksum mismatch for bundle member '{name}'")
            members[name] = data
    for required in _JSON_MEMBERS:
        if required not in members:
            raise BundleError(f"bundle is missing required member '{required}'")
    return members


def _json_member(members: dict[str, bytes], name: str, expect: type) -> object:
    try:
        obj = json.loads(members[name].decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BundleError(f"bundle member '{name}' is not valid JSON") from exc
    if not isinstance(obj, expect):
        raise BundleError(f"bundle member '{name}' has the wrong JSON shape")
    return obj


def _rows(members: dict[str, bytes], name: str) -> list[dict]:
    rows = _json_member(members, name, list)
    for row in rows:
        if not isinstance(row, dict):
            raise BundleError(f"bundle member '{name}' must contain JSON objects")
    return rows


def _id_map(rows: list[dict], label: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in rows:
        old = row.get("id")
        if not isinstance(old, str) or not old:
            raise BundleError(f"a row in {label} is missing its 'id'")
        if old in mapping:
            raise BundleError(f"duplicate id '{old}' in {label}")
        mapping[old] = new_id()
    return mapping


def _remap(value: object, mapping: dict[str, str]) -> str | None:
    """Remap an old FK to its new id; unknown/absent references become None."""
    if isinstance(value, str) and value in mapping:
        return mapping[value]
    return None


def import_project(session: Session, zip_bytes: bytes) -> Project:
    """Validate a bundle and create a brand-new project (fresh IDs, remapped FKs)."""
    members = _load_members(zip_bytes)

    project_row = _json_member(members, "project.json", dict)
    env_rows = _rows(members, "environments.json")
    conv_rows = _rows(members, "conversations.json")
    msg_rows = _rows(members, "messages.json")
    art_rows = _rows(members, "artifacts.json")
    cv_rows = _rows(members, "context_versions.json")
    rec_rows = _rows(members, "context_records.json")
    dep_rows = _rows(members, "deployments.json")
    rex_rows = _rows(members, "rule_executions.json")

    name = project_row.get("name")
    if not isinstance(name, str) or not name.strip():
        raise BundleError("project.json must include a non-empty 'name'")

    # Fresh IDs for everything, generated up front so any reference order works.
    env_map = _id_map(env_rows, "environments.json")
    conv_map = _id_map(conv_rows, "conversations.json")
    msg_map = _id_map(msg_rows, "messages.json")
    art_map = _id_map(art_rows, "artifacts.json")
    cv_map = _id_map(cv_rows, "context_versions.json")

    try:
        project = Project(
            name=name.strip()[:120],
            description=project_row.get("description"),
            is_default=False,
            settings=project_row.get("settings") or {},
            active_environment_id=_remap(project_row.get("activeEnvironmentId"), env_map),
            active_context_version_id=_remap(project_row.get("activeContextVersionId"), cv_map),
            created_at=_dt_or_now(project_row.get("createdAt")),
            updated_at=_dt_or_now(project_row.get("updatedAt")),
        )
        session.add(project)
        session.flush()

        for row in env_rows:
            session.add(
                EnvironmentProfile(
                    id=env_map[row["id"]],
                    project_id=project.id,
                    name=str(row.get("name") or "Imported environment")[:120],
                    base_url=row.get("baseUrl"),
                    username=row.get("username"),
                    auth_method=row.get("authMethod") or "passwordInMemory",
                    classification=row.get("classification") or "development",
                    preferred_application=row.get("preferredApplication"),
                    demo=bool(row.get("demo", True)),
                    # Credentials never travel in a bundle; the user reconnects.
                    remember_credentials=False,
                    created_at=_dt_or_now(row.get("createdAt")),
                    updated_at=_dt_or_now(row.get("updatedAt")),
                )
            )

        for row in conv_rows:
            session.add(
                Conversation(
                    id=conv_map[row["id"]],
                    project_id=project.id,
                    title=str(row.get("title") or "New chat")[:300],
                    pinned=bool(row.get("pinned", False)),
                    archived=bool(row.get("archived", False)),
                    provider=row.get("provider"),
                    model=row.get("model"),
                    draft=row.get("draft"),
                    last_message_at=_dt(row.get("lastMessageAt")),
                    metadata_=row.get("metadata") or {},
                    created_at=_dt_or_now(row.get("createdAt")),
                    updated_at=_dt_or_now(row.get("updatedAt")),
                )
            )

        for row in msg_rows:
            conversation_id = _remap(row.get("conversationId"), conv_map)
            if conversation_id is None:
                raise BundleError("a message references a conversation that is not in the bundle")
            session.add(
                Message(
                    id=msg_map[row["id"]],
                    conversation_id=conversation_id,
                    role=str(row.get("role") or "user")[:20],
                    content=row.get("content") or "",
                    blocks=row.get("blocks") or [],
                    process_steps=row.get("processSteps") or [],
                    parent_id=_remap(row.get("parentId"), msg_map),
                    active=bool(row.get("active", True)),
                    provider=row.get("provider"),
                    model=row.get("model"),
                    usage=row.get("usage"),
                    skill=row.get("skill"),
                    created_at=_dt_or_now(row.get("createdAt")),
                    updated_at=_dt_or_now(row.get("updatedAt")),
                )
            )

        for row in cv_rows:
            session.add(
                ContextVersion(
                    id=cv_map[row["id"]],
                    project_id=project.id,
                    environment_id=_remap(row.get("environmentId"), env_map),
                    application=str(row.get("application") or "")[:120],
                    label=str(row.get("label") or "Imported context")[:200],
                    mode=row.get("mode") or "quick",
                    manifest=row.get("manifest") or {},
                    counts=row.get("counts") or {},
                    fingerprint=row.get("fingerprint"),
                    path=None,  # .epwcontext files are not part of a bundle
                    active=bool(row.get("active", False)),
                    created_at=_dt_or_now(row.get("createdAt")),
                    updated_at=_dt_or_now(row.get("updatedAt")),
                )
            )

        for row in rec_rows:
            context_version_id = _remap(row.get("contextVersionId"), cv_map)
            if context_version_id is None:
                raise BundleError("a context record references a context version that is not in the bundle")
            session.add(
                ContextRecord(
                    context_version_id=context_version_id,
                    project_id=project.id,
                    kind=str(row.get("kind") or "member")[:30],
                    name=str(row.get("name") or "")[:300],
                    dimension=row.get("dimension"),
                    application=row.get("application"),
                    cube=row.get("cube"),
                    alias=row.get("alias"),
                    parent=row.get("parent"),
                    search_text=row.get("searchText") or "",
                    data=row.get("data") or {},
                )
            )

        settings = get_settings()
        for row in art_rows:
            old_id = row["id"]
            path: str | None = None
            blob = members.get(f"blobs/{old_id}")
            if blob is not None:
                target = settings.artifacts_dir / f"imported_{art_map[old_id]}.zip"
                target.write_bytes(blob)
                path = str(target)
            session.add(
                Artifact(
                    id=art_map[old_id],
                    project_id=project.id,
                    kind=str(row.get("kind") or "json")[:40],
                    name=str(row.get("name") or "artifact")[:200],
                    version=int(row.get("version") or 1),
                    payload=row.get("payload"),
                    content=row.get("content"),
                    path=path,
                    checksum=row.get("checksum"),
                    context_version=_remap(row.get("contextVersion"), cv_map) or row.get("contextVersion"),
                    source_conversation_id=_remap(row.get("sourceConversationId"), conv_map),
                    source_message_id=_remap(row.get("sourceMessageId"), msg_map),
                    parent_artifact_id=_remap(row.get("parentArtifactId"), art_map),
                    metadata_=row.get("metadata") or {},
                    created_at=_dt_or_now(row.get("createdAt")),
                    updated_at=_dt_or_now(row.get("updatedAt")),
                )
            )

        for row in dep_rows:
            session.add(
                Deployment(
                    project_id=project.id,
                    conversation_id=_remap(row.get("conversationId"), conv_map),
                    environment_name=row.get("environmentName"),
                    classification=row.get("classification") or "development",
                    application=row.get("application"),
                    artifact_name=str(row.get("artifactName") or "")[:200],
                    artifact_type=row.get("artifactType") or "planningForm",
                    operation=row.get("operation") or "create",
                    operation_class=row.get("operationClass") or "modifying",
                    approved=bool(row.get("approved", False)),
                    approval_note=row.get("approvalNote"),
                    context_version=_remap(row.get("contextVersion"), cv_map) or row.get("contextVersion"),
                    spec_version=row.get("specVersion"),
                    checksum=row.get("checksum"),
                    started_at=_dt(row.get("startedAt")),
                    ended_at=_dt(row.get("endedAt")),
                    job_result=row.get("jobResult"),
                    success=bool(row.get("success", False)),
                    verified=bool(row.get("verified", False)),
                    verification_notes=row.get("verificationNotes") or [],
                    backup_artifact_id=_remap(row.get("backupArtifactId"), art_map),
                    rollback_available=bool(row.get("rollbackAvailable", False)),
                    demo_mode=bool(row.get("demoMode", True)),
                    report=row.get("report") or {},
                    errors=row.get("errors") or [],
                    warnings=row.get("warnings") or [],
                    created_at=_dt_or_now(row.get("createdAt")),
                    updated_at=_dt_or_now(row.get("updatedAt")),
                )
            )

        for row in rex_rows:
            session.add(
                RuleExecution(
                    project_id=project.id,
                    conversation_id=_remap(row.get("conversationId"), conv_map),
                    rule_name=str(row.get("ruleName") or "")[:200],
                    application=row.get("application"),
                    cube=row.get("cube"),
                    status=row.get("status") or "ready",
                    prompt_values=row.get("promptValues") or {},
                    job_id=row.get("jobId"),
                    job_result=row.get("jobResult"),
                    started_at=_dt(row.get("startedAt")),
                    ended_at=_dt(row.get("endedAt")),
                    duration_ms=row.get("durationMs"),
                    output=row.get("output"),
                    errors=row.get("errors") or [],
                    demo_mode=bool(row.get("demoMode", True)),
                    created_at=_dt_or_now(row.get("createdAt")),
                    updated_at=_dt_or_now(row.get("updatedAt")),
                )
            )

        session.flush()
    except BundleError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise BundleError(f"bundle contains malformed row data: {exc}") from exc
    return project
