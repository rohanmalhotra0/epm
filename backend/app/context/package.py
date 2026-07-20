"""Portable .epwcontext package (spec section 17): a ZIP for team sharing,
backup and version comparison. Never contains passwords, tokens, keys or cookies.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

from sqlalchemy.orm import Session

from ..db.models import ContextVersion
from ..services import context_store
from . import engine as ctx_engine

_FIXED_DT = (1980, 1, 1, 0, 0, 0)
_KIND_FILE = {
    "application": "applications.json",
    "cube": "cubes.json",
    "dimension": "dimensions.json",
    "member": "members.json",
    "form": "forms.json",
    "rule": "rules.json",
    "variable": "variables.json",
    # Snapshot-derived kinds — without these, exporting a hybrid/snapshot
    # context would silently drop them while the manifest still counts them.
    "template": "templates.json",
    "integration": "integrations.json",
    "securityGroup": "securityGroups.json",
    "smartList": "smartLists.json",
    "dataMap": "dataMaps.json",
    "validIntersection": "validIntersections.json",
}
_FORBIDDEN_KEYS = {"password", "token", "apikey", "api_key", "secret", "cookie", "authorization"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate_context_md(manifest: dict, application: str) -> str:
    lines = [f"# Context: {application}", "", f"Mode: **{manifest.get('mode')}**",
             f"Generated: {manifest.get('generatedAt')}",
             f"Classification: {manifest.get('environmentClassification')}", "", "## Counts", ""]
    for k, v in (manifest.get("counts") or {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Sections", ""]
    for s in manifest.get("sections", []):
        note = f" — {s['note']}" if s.get("note") else ""
        lines.append(f"- **{s['name']}**: {s['status']} ({s['count']}){note}")
    if manifest.get("knownLimitations"):
        lines += ["", "## Known Limitations", ""]
        for lim in manifest["knownLimitations"]:
            lines.append(f"- {lim}")
    return "\n".join(lines).rstrip() + "\n"


def _assert_no_secrets(data) -> None:  # noqa: ANN001
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(k, str) and k.lower() in _FORBIDDEN_KEYS:
                raise ValueError(f"refusing to export secret-like key '{k}' in context package")
            _assert_no_secrets(v)
    elif isinstance(data, list):
        for v in data:
            _assert_no_secrets(v)


def export_context_package(session: Session, context_version_id: str) -> tuple[str, bytes]:
    cv = session.get(ContextVersion, context_version_id)
    if cv is None:
        raise KeyError("context version not found")
    records = context_store.get_records(session, context_version_id)

    grouped: dict[str, list] = {fn: [] for fn in _KIND_FILE.values()}
    relationships = []
    for r in records:
        fname = _KIND_FILE.get(r.kind)
        if fname:
            grouped[fname].append(r.data)
        if r.kind == "member" and r.parent:
            relationships.append({"dimension": r.dimension, "child": r.name, "parent": r.parent})

    files: dict[str, str] = {}
    for fname, items in grouped.items():
        _assert_no_secrets(items)
        files[fname] = json.dumps(items, indent=2) + "\n"
    files["relationships.json"] = json.dumps(relationships, indent=2) + "\n"
    files["conventions.json"] = json.dumps(
        {"folderConvention": "EPM Wizard/Generated", "aliasTable": "Default"}, indent=2) + "\n"

    manifest = dict(cv.manifest or {})
    manifest["checksums"] = {fn: _sha(txt) for fn, txt in sorted(files.items())}
    manifest["includedFiles"] = sorted(files.keys()) + ["context.md", "manifest.json"]
    files["context.md"] = generate_context_md(manifest, cv.application)
    files["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files.keys()):
            info = zipfile.ZipInfo(filename=name, date_time=_FIXED_DT)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, files[name])
    filename = f"{cv.label}.epwcontext"
    return filename, buffer.getvalue()


def validate_context_package(data: bytes) -> list[str]:
    issues: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                issues.append("missing manifest.json")
                return issues
            manifest = json.loads(zf.read("manifest.json"))
            for fn, expected in (manifest.get("checksums") or {}).items():
                if fn not in names:
                    issues.append(f"missing file {fn}")
                    continue
                actual = _sha(zf.read(fn).decode("utf-8"))
                if actual != expected:
                    issues.append(f"checksum mismatch for {fn}")
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        issues.append(f"invalid package: {exc}")
    return issues


def import_context_package(data: bytes) -> ctx_engine.ContextBundle:
    issues = validate_context_package(data)
    if issues:
        raise ValueError("; ".join(issues))
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        loaded: dict[str, list] = {}
        for kind, fname in _KIND_FILE.items():
            if fname in zf.namelist():
                loaded[kind] = json.loads(zf.read(fname))

    application = manifest.get("application", "IMPORTED")
    records: list[dict] = []
    for kind, items in loaded.items():
        for data_item in items:
            records.append({
                "kind": kind,
                "name": data_item.get("name", ""),
                "dimension": data_item.get("dimension"),
                "cube": data_item.get("cube"),
                "alias": data_item.get("alias"),
                "parent": data_item.get("parent"),
                "application": data_item.get("application", application),
                "search_text": f"{data_item.get('name','')} {data_item.get('alias','') or ''}".lower(),
                "data": data_item,
            })
    counts = manifest.get("counts", {})
    from ..schemas.context import ContextSectionStatus
    sections = [ContextSectionStatus.model_validate(s) for s in manifest.get("sections", [])]
    return ctx_engine.ContextBundle(
        application=application,
        mode="imported",
        label=manifest.get("contextVersion", f"{application}_imported"),
        records=records,
        counts=counts,
        sections=sections,
        manifest=None,
        fingerprint=manifest.get("environmentFingerprint", ""),
    )
