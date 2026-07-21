"""LCM application-snapshot analysis and context merge (snapshot upload flow).

An Oracle EPM Migration snapshot zip (``epmautomate exportSnapshot`` +
``downloadFile "Artifact Snapshot"``) is the richest offline source of
application truth: full dimension CSVs, Calculation Manager rule bodies with
runtime prompts, substitution/user variables, navigation-flow form references,
FDMEE inventory and security groups. ``analyze_snapshot`` inventories the
archive fully in memory (zip-slip guarded, size-capped, never extracted to
disk) into a ``SnapshotBundle``; ``merge_snapshot_into_context`` layers it over
the active context as a NEW ContextVersion (mode "hybrid") or imports it
standalone (mode "snapshot"). Everything — application, cubes, dimensions — is
read from the archive itself (Export.xml + ``<PRODUCT>-<App>/`` folders);
nothing is hardcoded. A malformed artifact adds an ``issues`` entry and parsing
continues.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from dataclasses import dataclass, field

from defusedxml import ElementTree as DET
from sqlalchemy.orm import Session

from ..artifacts.parser import parse_xml as _parse_form_xml
from ..connector.metadata_export import _parse_csv as _parse_dimension_csv
from ..connector.metadata_export import _strip_lcm_header
from ..db.models import ContextVersion
from ..schemas.context import (
    CompletenessStatus,
    ContextSectionStatus,
    SnapshotAnalysis,
    SnapshotComponent,
    SnapshotProvenance,
)
from ..services import context_store
from .engine import _record

_MAX_ENTRIES = 20_000
_MAX_TOTAL_UNCOMPRESSED = 400 * 1024 * 1024
_MAX_TEXT_ENTRY = 8 * 1024 * 1024
# Caps entries/bytes alone miss: highly compressible CSVs can amplify a small
# zip into hundreds of millions of member records (and ORM rows).
_MAX_RECORDS = 250_000
_RULE_BODY_CAP = 60_000
_TRUNCATION_MARK = "...[truncated]"
_SOURCE = "snapshot"

# Folder prefixes whose LCM product code differs from the folder name.
_PRODUCT_BY_PREFIX = {"FDMEE": "AIF", "HSS": "HUB"}
_COMPONENT_DIR = re.compile(r"^[A-Z][A-Z0-9]*-.+")
_TEMPLATE_REF = re.compile(r'%Template\(\s*name\s*:=\s*"([^"]+)"')
_CUBE_COLUMN = re.compile(r"^Aggregation \((.+)\)$")
_DIM_TYPES = {"account", "entity", "scenario", "version", "period", "attribute"}

_FORMS_REFERENCED_NOTE = "Names referenced by navigation flows; definitions not included in this snapshot"
_FORMS_UNPARSED_NOTE = "Form definition files present but none could be parsed"


class SnapshotError(ValueError):
    """The upload is not a usable LCM snapshot zip (routes map this to HTTP 400)."""


@dataclass
class SnapshotBundle:
    analysis: SnapshotAnalysis
    records: list[dict] = field(default_factory=list)
    sections: list[ContextSectionStatus] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


# --- safe in-memory archive access -------------------------------------------


@dataclass
class _Archive:
    zf: zipfile.ZipFile
    files: dict[tuple[str, ...], zipfile.ZipInfo]
    issues: list[str]

    def read_text(self, parts: tuple[str, ...]) -> str | None:
        info = self.files.get(parts)
        if info is None:
            return None
        if info.file_size > _MAX_TEXT_ENTRY:
            self.issues.append(f"skipped oversized entry: {'/'.join(parts)}")
            return None
        try:
            raw = self.zf.read(info)
        except (RuntimeError, NotImplementedError, zipfile.BadZipFile, OSError) as exc:
            # Encrypted entries, unsupported compression methods, CRC mismatches.
            self.issues.append(f"unreadable entry {'/'.join(parts)}: {exc}")
            return None
        if b"\x00" in raw[:1024]:
            self.issues.append(f"skipped binary entry: {'/'.join(parts)}")
            return None
        return raw.decode("utf-8-sig", "replace")

    def under(self, *prefix: str) -> list[tuple[str, ...]]:
        n = len(prefix)
        return sorted(p for p in self.files if p[:n] == prefix)


def _open_archive(data: bytes, issues: list[str]) -> _Archive:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise SnapshotError("not a valid zip archive") from exc
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > _MAX_ENTRIES:
        raise SnapshotError(f"archive has too many entries ({len(infos)} > {_MAX_ENTRIES})")
    total = sum(i.file_size for i in infos)
    if total > _MAX_TOTAL_UNCOMPRESSED:
        raise SnapshotError("archive exceeds the uncompressed size cap")
    files: dict[tuple[str, ...], zipfile.ZipInfo] = {}
    for info in sorted(infos, key=lambda i: i.filename):
        name = info.filename.replace("\\", "/")
        parts = tuple(p for p in name.split("/") if p and p != ".")
        if not parts:
            continue
        if name.startswith("/") or ".." in parts or ":" in parts[0]:
            issues.append(f"skipped unsafe path: {info.filename}")
            continue
        if "Essbase Data" in parts:
            continue
        files[parts] = info
    # Tolerate a single wrapping root directory ("Artifact Snapshot/HP-App/…"),
    # but never strip a component folder ("HP-App/…") itself.
    tops = {p[0] for p in files}
    if len(tops) == 1:
        top = next(iter(tops))
        if all(len(p) > 1 for p in files) and not _COMPONENT_DIR.match(top):
            files = {p[1:]: v for p, v in files.items()}
    return _Archive(zf, files, issues)


def _parse_xml_text(text: str, where: str, issues: list[str]):
    try:
        return DET.fromstring(text)
    except Exception as exc:  # malformed XML must never abort the whole parse
        issues.append(f"{where}: {exc}")
        return None


def _read_xml(archive: _Archive, parts: tuple[str, ...]):
    text = archive.read_text(parts)
    if text is None:
        return None
    return _parse_xml_text(text, "/".join(parts), archive.issues)


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


# --- package structure --------------------------------------------------------


def _package_tasks(archive: _Archive) -> dict[str, tuple[str, str]]:
    """folder key -> (product, application) from Export.xml (Import.xml fallback)."""
    out: dict[str, tuple[str, str]] = {}
    for name in ("Export.xml", "Import.xml"):
        root = _read_xml(archive, (name,)) if (name,) in archive.files else None
        if root is None:
            continue
        for task in root.iter():
            if _local(task.tag) != "Task":
                continue
            product = application = folder = None
            for child in task:
                if _local(child.tag) not in ("Source", "Target"):
                    continue
                if child.get("product"):
                    product = child.get("product")
                    application = child.get("application") or ""
                if child.get("filePath"):
                    folder = (child.get("filePath") or "").strip("/")
            if folder and product and folder not in out:
                out[folder] = (product, application or "")
    return out


def _components(archive: _Archive, tasks: dict[str, tuple[str, str]]) -> list[SnapshotComponent]:
    comps: list[SnapshotComponent] = []
    for key in sorted({p[0] for p in archive.files if len(p) > 1}):
        if key in tasks:
            product, application = tasks[key]
        elif _COMPONENT_DIR.match(key):
            prefix, _, application = key.partition("-")
            product = _PRODUCT_BY_PREFIX.get(prefix, prefix)
        else:
            continue
        count = sum(1 for p in archive.files if len(p) > 2 and p[0] == key and p[1] == "resource")
        comps.append(SnapshotComponent(key=key, product=product, application=application, artifact_count=count))
    return comps


def _provenance(archive: _Archive) -> SnapshotProvenance | None:
    root = _read_xml(archive, ("Import.xml",)) if ("Import.xml",) in archive.files else None
    if root is None:
        return None
    vals = {_local(c.tag): c.text.strip() for c in root if c.text and c.text.strip()}
    exported_at = None
    date, time = vals.get("ExportedDateUTC"), vals.get("ExportedTimeUTC")
    if date and len(date) == 8 and date.isdigit():
        exported_at = f"{date[:4]}-{date[4:6]}-{date[6:]}" + (f"T{time}Z" if time else "")
    prov = SnapshotProvenance(
        exported_by=vals.get("ExportedBy"),
        exported_at=exported_at,
        service_instance=vals.get("ServiceInstance"),
        domain=vals.get("IDMDomain"),
        exported_version=vals.get("ExportedVersion"),
    )
    return prov if any(prov.model_dump().values()) else None


# --- HP (Planning) component ---------------------------------------------------


def _dimension_header(text: str, where: str, issues: list[str]) -> tuple[bool | None, str, list[str]]:
    """(dense, type, cubes) from the HEADERBLOCK XML + per-cube CSV columns."""
    dense: bool | None = None
    dim_type = "generic"
    if "#!-- HEADERBLOCK" in text[:256]:
        start, end = text.find("<?xml"), text.find("</DIMENSIONS>")
        if start != -1 and end != -1:
            root = _parse_xml_text(text[start:end + len("</DIMENSIONS>")], where, issues)
            dim_el = next((el for el in root.iter() if _local(el.tag) == "Dimension"), None) if root is not None else None
            if dim_el is not None:
                density = (dim_el.get("density") or "").casefold()
                dense = {"dense": True, "sparse": False}.get(density)
                declared = (dim_el.get("dimensionType") or "").casefold()
                if declared in _DIM_TYPES:
                    dim_type = declared
                elif declared == "time":
                    dim_type = "period"
    try:
        header_row = next(csv.reader(io.StringIO(_strip_lcm_header(text))), [])
    except csv.Error as exc:
        # A single oversized/unbalanced header field must not abort the whole
        # snapshot: degrade this dimension to no per-cube columns and continue.
        issues.append(f"unparseable dimension header {where}: {exc}")
        header_row = []
    cubes = []
    for h in header_row:
        m = _CUBE_COLUMN.match(h.strip())
        if m:
            cubes.append(m.group(1))
    return dense, dim_type, cubes


def _read_variable_xml(archive: _Archive, parts: tuple[str, ...], application: str) -> dict | None:
    root = _read_xml(archive, parts)
    if root is None:
        return None
    vals = {_local(c.tag): (c.text or "").strip() for c in root.iter()}
    name = vals.get("name") or parts[-1].removesuffix(".xml")
    plan_type = vals.get("planType") or "ALL"
    return {
        "name": name,
        "application": application,
        "scope": "substitution",
        "dimension": None,
        "value": vals.get("value") or None,
        "cube": None if plan_type.upper() == "ALL" else plan_type,
    }


def _navigation_flow_refs(archive: _Archive, parts: tuple[str, ...]) -> set[str]:
    root = _read_xml(archive, parts)
    if root is None:
        return set()
    refs: set[str] = set()
    for usage in root.iter():
        if _local(usage.tag) != "usageXML" or not (usage.text or "").strip():
            continue
        inner = _parse_xml_text(usage.text, "/".join(parts) + "#usageXML", archive.issues)
        if inner is None:
            continue
        for param in inner.iter():
            if _local(param.tag) != "tfParameter" or param.get("name") != "formId":
                continue
            uid = param.get("artifactUID") or ""
            if "~~~" in uid:
                refs.add(uid.split("~~~", 1)[1])
    return refs


def _parse_form_definition(text: str, where: str, issues: list[str]):
    """FormSpecification from a Data Forms definition file, or None + an issue."""
    try:
        return _parse_form_xml(text)
    except Exception as exc:  # noqa: BLE001 — a bad definition must never abort the parse
        issues.append(f"unparseable form definition {where}: {exc}")
        return None


# --- optional deep-parsers (smart lists / data maps / valid intersections /
#     dashboards). Oracle exports these under varied root/element tag names; all
#     matching is by local tag, case-insensitively, so a differently-cased or
#     namespaced variant still parses. A malformed file degrades to a name-only
#     record plus an issue (via _read_xml) and never aborts the snapshot parse. --


def _attr_ci(el, *names: str) -> str | None:
    wanted = {n.casefold() for n in names}
    for k, v in el.attrib.items():
        if _local(k).casefold() in wanted and (v or "").strip():
            return v.strip()
    return None


def _child_text_ci(el, *names: str) -> str | None:
    wanted = {n.casefold() for n in names}
    for c in el:
        if _local(c.tag).casefold() in wanted and (c.text or "").strip():
            return c.text.strip()
    return None


def _parse_smart_list(root, name: str) -> tuple[dict, str | None]:
    entries: list[dict] = []
    for el in root.iter():
        if _local(el.tag).casefold() not in ("entry", "smartlistentry"):
            continue
        ename = _attr_ci(el, "name", "entryName") or _child_text_ci(el, "name")
        label = _attr_ci(el, "label", "entryLabel") or _child_text_ci(el, "label")
        value = _attr_ci(el, "value", "entryValue", "id") or _child_text_ci(el, "value")
        if ename or label or value:
            entries.append({"name": ename, "label": label, "value": value})
    search = " ".join([name] + [e["label"] for e in entries if e["label"]])
    return {"entries": entries}, search


def _cube_ref(root, which: str) -> str | None:
    val = _attr_ci(root, f"{which}Cube", f"{which}PlanType")
    if val:
        return val
    for el in root.iter():
        if _local(el.tag).casefold() == which:
            return _attr_ci(el, "cube", "planType", "name") or (el.text or "").strip() or None
    return None


def _parse_data_map(root, name: str) -> tuple[dict, str | None]:
    return {"sourceCube": _cube_ref(root, "source"), "targetCube": _cube_ref(root, "target")}, None


def _parse_valid_intersection(root, name: str) -> tuple[dict, str | None]:
    dims: list[str] = []
    for el in root.iter():
        if _local(el.tag).casefold() not in ("dimension", "dimensionname", "axis"):
            continue
        d = _attr_ci(el, "name", "dimension", "dimensionName") or (el.text or "").strip()
        if d and d not in dims:
            dims.append(d)
    return {"dimensions": dims}, None


def _parse_dashboard(root, name: str) -> tuple[dict, str | None]:
    forms: list[str] = []
    for el in root.iter():
        tag = _local(el.tag).casefold()
        ref = None
        if tag in ("form", "formname", "formreference"):
            ref = _attr_ci(el, "name", "formName", "form") or (el.text or "").strip() or None
        elif tag in ("object", "artifact"):
            if "form" in (_attr_ci(el, "type", "objectType") or "").casefold():
                ref = _attr_ci(el, "name", "artifactName")
        else:
            ref = _attr_ci(el, "formName")
        if ref and ref not in forms:
            forms.append(ref)
    return {"forms": forms}, " ".join([name] + forms)


def _parse_hp(archive: _Archive, key: str, application: str, records: list[dict]) -> dict:
    found: dict = {"dimensions": [], "cubes": [], "members": 0, "variables": 0,
                   "forms_referenced": set(), "dashboards_referenced": set(),
                   "real_forms": 0, "forms_parsed": 0, "nav_flows": False,
                   "sub_var_files": False, "user_vars": None}
    res = (key, "resource")
    cube_dims: dict[str, list[str]] = {}

    # Dimensions + members (Global Artifacts/Common Dimensions/**/<Dim>.csv).
    dim_entries = [p for p in archive.under(*res, "Global Artifacts", "Common Dimensions")
                   if p[-1].casefold().endswith(".csv")]
    member_records: list[dict] = []
    for parts in dim_entries:
        text = archive.read_text(parts)
        if text is None:
            continue
        dimension = parts[-1][:-4]
        where = "/".join(parts)
        dense, dim_type, dim_cubes = _dimension_header(text, where, archive.issues)
        found["dimensions"].append(dimension)
        for cube in dim_cubes:
            cube_dims.setdefault(cube, []).append(dimension)
        dim_data = {"name": dimension, "application": application, "type": dim_type,
                    "cubes": dim_cubes, "dense": dense, "source": _SOURCE}
        records.append(_record("dimension", dimension, dim_data, dimension=dimension, application=application))
        before = len(member_records)
        try:
            for m in _parse_dimension_csv(text, dimension, application):
                data = m.model_dump(by_alias=True)
                data["source"] = _SOURCE
                member_records.append(_record(
                    "member", m.name, data, dimension=dimension, alias=m.alias, parent=m.parent,
                    application=application, search=f"{m.name} {m.alias or ''}".strip(),
                ))
                if len(member_records) > _MAX_RECORDS:
                    raise SnapshotError(f"snapshot exceeds the record cap ({_MAX_RECORDS:,})")
        except csv.Error as exc:
            del member_records[before:]
            archive.issues.append(f"unparseable dimension CSV {where}: {exc}")
    found["members"] = len(member_records)

    # Cubes: folder names under Cube/ plus any named in per-cube dimension columns.
    cube_names = sorted({p[len(res) + 1] for p in archive.under(*res, "Cube") if len(p) > len(res) + 2}
                        | set(cube_dims))
    for cube in cube_names:
        cube_data = {"name": cube, "application": application, "type": "aso/bso",
                     "dimensions": sorted(cube_dims.get(cube, [])), "source": _SOURCE}
        records.append(_record("cube", cube, cube_data, cube=cube, application=application))
    found["cubes"] = cube_names
    records.extend(member_records)

    # Substitution variables: global and per-cube.
    variables: dict[tuple[str, str], dict] = {}
    sub_var_entries = [p for p in archive.under(*res, "Global Artifacts", "Substitution Variables")
                       if p[-1].casefold().endswith(".xml")]
    sub_var_entries += [p for p in archive.under(*res, "Cube")
                        if len(p) > len(res) + 2 and p[len(res) + 2] == "Substitution Variables"
                        and p[-1].casefold().endswith(".xml")]
    for parts in sorted(sub_var_entries):
        found["sub_var_files"] = True
        var = _read_variable_xml(archive, parts, application)
        if var is not None:
            variables.setdefault((var["name"], var["cube"] or ""), var)
    found["variables"] = len(variables)

    # User variables.
    user_vars = 0
    uv_parts = (*res, "Configuration", "User Variables.xml")
    if uv_parts in archive.files:
        root = _read_xml(archive, uv_parts)
        for el in root.iter() if root is not None else []:
            if _local(el.tag) != "UserVariable" or not el.get("Name"):
                continue
            selection = next((c.text for c in el if _local(c.tag) == "mbrSelection" and c.text), None)
            var = {"name": el.get("Name"), "application": application, "scope": "user",
                   "dimension": el.get("Dimension") or None, "value": selection, "cube": None}
            if variables.setdefault((var["name"], "user"), var) is var:
                user_vars += 1
    for (name, _), var in sorted(variables.items()):
        data = {**var, "source": _SOURCE}
        records.append(_record("variable", name, data, dimension=var["dimension"], cube=var["cube"],
                               application=application, search=f"{name} {var['dimension'] or ''}".strip()))
    if uv_parts in archive.files:
        found["user_vars"] = user_vars

    # Real form definitions: richer exports include definition XML under Data
    # Forms; the shipped fixture generation carries names only. Each file is
    # parsed into a full definition when possible; a bad file keeps its
    # name-only record plus an issue and never aborts the snapshot parse.
    parsed_forms: set[str] = set()
    # Every name that came from a definition FILE (parsed or not) — a bare
    # nav-flow stub must never overwrite a file-derived record in the last-wins
    # metadata dict, even when the definition XML failed to parse.
    file_forms: set[str] = set()
    form_entries = [p for p in archive.under(*res, "Global Artifacts", "Data Forms")]
    form_entries += [p for p in archive.under(*res, "Cube")
                     if len(p) > len(res) + 2 and p[len(res) + 2] == "Data Forms"]
    for parts in sorted(form_entries):
        name = parts[-1].removesuffix(".xml")
        folder = "/".join(parts[len(res):-1])
        cube = parts[len(res) + 1] if parts[len(res)] == "Cube" else None
        data = {"name": name, "application": application, "cube": cube, "folder": folder, "source": _SOURCE}
        text = archive.read_text(parts)
        spec = _parse_form_definition(text, "/".join(parts), archive.issues) if text is not None else None
        if spec is not None:
            definition = spec.model_dump(by_alias=True, exclude_none=True)
            # The name stays out of the definition dict so reference-form
            # cloning (parse_definition) can rename the copy cleanly.
            definition.pop("name", None)
            name = spec.name
            data.update({"name": name, "cube": cube or spec.cube, "definition": definition})
            parsed_forms.add(name.casefold())
            found["forms_parsed"] += 1
        records.append(_record("form", name, data, cube=data["cube"], application=application,
                               search=f"{name} {folder}"))
        file_forms.add(name.casefold())
        found["real_forms"] += 1

    # Forms referenced by navigation flows: still valuable when no definition
    # was shipped, but a parsed definition of the same name always wins — the
    # referenced-only stub is skipped, not duplicated.
    for parts in archive.under(*res, "Global Artifacts", "Navigation Flows"):
        if not parts[-1].casefold().endswith(".xml"):
            continue
        found["nav_flows"] = True
        for name in _navigation_flow_refs(archive, parts):
            bucket = "dashboards_referenced" if "dashboard" in name.casefold() else "forms_referenced"
            found[bucket].add(name)
    for name in sorted(found["forms_referenced"] | found["dashboards_referenced"]):
        if name.casefold() in file_forms:
            continue  # a definition file already produced a richer record
        data = {"name": name, "application": application, "referencedOnly": True, "source": _SOURCE}
        records.append(_record("form", name, data, application=application))

    # Smart lists, data maps, valid intersections, dashboards: optional deep
    # parsers, each tolerant of presence or absence. Per kind we track whether
    # the folder was present, the total records emitted, and how many were
    # actually deep-parsed (vs. degraded to a name-only stub) so the section
    # tier can be reported honestly: complete (parsed), derived (names only),
    # unavailable (folder absent).
    deep: dict[str, dict[str, int | bool]] = {
        k: {"present": False, "total": 0, "parsed": 0}
        for k in ("smartList", "dataMap", "validIntersection", "dashboard")}

    def _emit_deep(kind: str, parts: tuple[str, ...], parser, cube: str | None = None) -> None:
        entry_name = parts[-1].removesuffix(".xml")
        bucket = deep[kind]
        bucket["present"] = True
        bucket["total"] += 1
        data = {"name": entry_name, "application": application, "source": _SOURCE}
        if cube is not None:
            data["cube"] = cube
        search = entry_name
        root = _read_xml(archive, parts)  # malformed -> issue + name-only
        if root is not None:
            extra, extra_search = parser(root, entry_name)
            data.update(extra)
            search = extra_search or entry_name
            bucket["parsed"] += 1
        records.append(_record(kind, entry_name, data, cube=data.get("cube"),
                               application=application, search=search))

    for folder, kind, parser in (("Smart Lists", "smartList", _parse_smart_list),
                                 ("Data Maps", "dataMap", _parse_data_map),
                                 ("Valid Intersections", "validIntersection", _parse_valid_intersection)):
        for parts in archive.under(*res, "Global Artifacts", folder):
            if parts[-1].casefold().endswith(".xml"):
                _emit_deep(kind, parts, parser)

    # Dashboards live under Global Artifacts and per-cube (Cube/<cube>/Dashboards).
    dash_entries = list(archive.under(*res, "Global Artifacts", "Dashboards"))
    dash_entries += [p for p in archive.under(*res, "Cube")
                     if len(p) > len(res) + 2 and p[len(res) + 2] == "Dashboards"]
    for parts in sorted(dash_entries):
        if not parts[-1].casefold().endswith(".xml"):
            continue
        cube = parts[len(res) + 1] if parts[len(res)] == "Cube" else None
        _emit_deep("dashboard", parts, _parse_dashboard, cube=cube)

    found["deep"] = deep
    return found


# --- CALC (Calculation Manager) component --------------------------------------


def _iter_outside_templates(elem):
    """Iterate a rule subtree (pre-order DFS) skipping inlined dependent-template
    subtrees. Iterative on purpose: a deeply nested (hostile) rule XML would blow
    the Python stack with a recursive walk and abort the whole snapshot parse."""
    stack = list(elem)[::-1]
    while stack:
        node = stack.pop()
        if _local(node.tag) in ("template", "templates"):
            continue
        yield node
        stack.extend(list(node)[::-1])


def _parse_rule_file(text: str, where: str, fallback_name: str, fallback_cube: str,
                     application: str, issues: list[str]) -> list[dict]:
    root = _parse_xml_text(text, where, issues)
    if root is None:
        return []
    rules: list[dict] = []
    for rule in root.iter():
        if _local(rule.tag) != "rule":
            continue
        name = rule.get("name") or fallback_name
        cube = fallback_cube
        script_type = None
        body = ""
        prompts: list[str] = []
        for el in _iter_outside_templates(rule):
            tag = _local(el.tag)
            if tag == "property" and el.get("name") == "plantype" and (el.text or "").strip():
                cube = el.text.strip()
            elif tag == "variable_reference" and el.get("name"):
                if el.get("name") not in prompts:
                    prompts.append(el.get("name"))
            elif tag == "script":
                script_type = el.get("type") or script_type
                if el.text:
                    body = el.text
        templates = sorted(set(_TEMPLATE_REF.findall(body)))
        truncated = len(body) > _RULE_BODY_CAP
        if truncated:
            body = body[:_RULE_BODY_CAP] + _TRUNCATION_MARK
        data = {"name": name, "application": application, "cube": cube, "scriptType": script_type,
                "runtimePrompts": prompts, "templates": templates, "body": body, "source": _SOURCE}
        if truncated:
            data["bodyTruncated"] = True
        rules.append(data)
    return rules


def _parse_calc(archive: _Archive, key: str, records: list[dict]) -> tuple[int, int]:
    rule_count = template_count = 0
    for parts in archive.under(key, "resource", "Planning"):
        # <key>/resource/Planning/<App>/<Cube>/{Rules,Templates}/<name>
        if len(parts) != 7:
            continue
        _, _, _, calc_app, cube, folder, name = parts
        if folder == "Templates":
            data = {"name": name, "application": calc_app, "cube": cube, "source": _SOURCE}
            records.append(_record("template", name, data, cube=cube, application=calc_app))
            template_count += 1
        elif folder == "Rules":
            text = archive.read_text(parts)
            if text is None:
                continue
            for data in _parse_rule_file(text, "/".join(parts), name, cube, calc_app, archive.issues):
                records.append(_record("rule", data["name"], data, cube=data["cube"], application=calc_app,
                                       search=f"{data['name']} {data['cube'] or ''}".strip()))
                rule_count += 1
    return rule_count, template_count


# --- FDMEE (AIF) and Shared Services (HUB) components ---------------------------


def _parse_fdmee(archive: _Archive, key: str, records: list[dict]) -> tuple[int, int]:
    integrations: dict[tuple[str, str], dict] = {}
    pipelines = 0
    for parts in archive.under(key, "resource"):
        leaf = parts[-1]
        if leaf == "Import Format.xml":
            root = _read_xml(archive, parts)
            for el in root.iter() if root is not None else []:
                if _local(el.tag) == "Impgroupkey" and (el.text or "").strip():
                    name = el.text.strip()
                    integrations.setdefault(("importFormat", name), {"type": "importFormat", "name": name})
        elif leaf == "Location.xml":
            root = _read_xml(archive, parts)
            for el in root.iter() if root is not None else []:
                if _local(el.tag) == "Partname" and (el.text or "").strip():
                    name = el.text.strip()
                    integrations.setdefault(("location", name), {"type": "location", "name": name})
        elif len(parts) > 2 and parts[-2] == "Pipeline Definition" and leaf.casefold().endswith(".xml"):
            root = _read_xml(archive, parts)
            if root is None:
                continue
            vals = {_local(c.tag): (c.text or "") for c in root.iter()}
            name = vals.get("PIPELINENAME", "").strip() or leaf.removesuffix(".xml")
            data = {"type": "pipeline", "name": name}
            try:
                stages = json.loads(vals.get("JSONVALUE", "")).get("stages")
                if isinstance(stages, list):
                    data["stages"] = len(stages)
            except (ValueError, AttributeError):
                pass
            integrations.setdefault(("pipeline", name), data)
            pipelines += 1
    for (_, name), data in sorted(integrations.items()):
        records.append(_record("integration", name, {**data, "source": _SOURCE}))
    return len(integrations), pipelines


def _parse_hss(archive: _Archive, key: str, records: list[dict]) -> tuple[int | None, int | None]:
    groups: int | None = None
    users: int | None = None
    groups_parts = (key, "resource", "Native Directory", "Groups.csv")
    text = archive.read_text(groups_parts) if groups_parts in archive.files else None
    if text is not None:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if lines and lines[0].startswith("#"):
            lines = lines[1:]
        names = []
        try:
            for row in csv.DictReader(io.StringIO("\n".join(lines))):
                name = (row.get("name") or "").strip()
                if name:
                    names.append(name)
        except csv.Error as exc:
            # An oversized/unbalanced field must not abort the whole snapshot.
            archive.issues.append(f"unparseable groups CSV {'/'.join(groups_parts)}: {exc}")
        for name in sorted(names):
            records.append(_record("securityGroup", name, {"name": name, "source": _SOURCE}))
        groups = len(names)
    users_parts = (key, "resource", "External Directory", "Users.csv")
    text = archive.read_text(users_parts) if users_parts in archive.files else None
    if text is not None:
        # Count only — user emails/logins are never stored in records.
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if lines and lines[0].startswith("#"):
            lines = lines[1:]
        users = max(len(lines) - 1, 0)  # minus the header row
    return groups, users


# --- public API -----------------------------------------------------------------


def analyze_snapshot(data: bytes, filename: str | None = None) -> SnapshotBundle:
    # Callers only handle SnapshotError; any parse failure a hostile or damaged
    # archive can still trigger (csv limits, codec corner cases…) must map to it.
    try:
        return _analyze_snapshot(data, filename)
    except SnapshotError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SnapshotError(f"failed to parse snapshot: {exc}") from exc


def _analyze_snapshot(data: bytes, filename: str | None = None) -> SnapshotBundle:
    issues: list[str] = []
    archive = _open_archive(data, issues)
    if not archive.files:
        raise SnapshotError("archive is empty")

    tasks = _package_tasks(archive)
    components = _components(archive, tasks)
    if not components:
        raise SnapshotError("not an EPM LCM snapshot (no Export.xml tasks or <PRODUCT>-<name> component folders)")

    hp = next((c for c in components if c.product == "HP"), None)
    application = hp.application if hp else None
    records: list[dict] = []
    counts: dict[str, int] = {}

    if application:
        records.append(_record("application", application,
                               {"name": application, "type": "planning", "source": _SOURCE},
                               application=application))

    found: dict = {"dimensions": [], "cubes": [], "members": 0, "variables": 0,
                   "forms_referenced": set(), "dashboards_referenced": set(),
                   "real_forms": 0, "forms_parsed": 0, "nav_flows": False,
                   "sub_var_files": False, "user_vars": None}
    if hp is not None:
        found = _parse_hp(archive, hp.key, hp.application, records)
        if found["dimensions"]:
            counts["members"] = found["members"]
        if found["variables"] or found["sub_var_files"]:
            counts["variables"] = found["variables"]
        if found["user_vars"] is not None:
            counts["userVariables"] = found["user_vars"]
        if found["real_forms"]:
            counts["forms"] = found["real_forms"]
        if found["nav_flows"]:
            counts["formsReferenced"] = len(found["forms_referenced"])
            counts["dashboardsReferenced"] = len(found["dashboards_referenced"])
        for kind, ckey in (("smartList", "smartLists"), ("dataMap", "dataMaps"),
                           ("validIntersection", "validIntersections"), ("dashboard", "dashboards")):
            total = found.get("deep", {}).get(kind, {}).get("total", 0)
            if total:
                counts[ckey] = total

    rule_count = template_count = 0
    for comp in components:
        if comp.product == "CALC":
            r, t = _parse_calc(archive, comp.key, records)
            rule_count += r
            template_count += t
            counts["rules"] = rule_count
            counts["templates"] = template_count

    integrations = pipelines = 0
    has_fdmee = False
    for comp in components:
        if comp.product == "AIF":
            has_fdmee = True
            i, p = _parse_fdmee(archive, comp.key, records)
            integrations += i
            pipelines += p
    if has_fdmee:
        counts["integrations"] = integrations
        counts["pipelines"] = pipelines

    for comp in components:
        if comp.product == "HUB":
            groups, users = _parse_hss(archive, comp.key, records)
            if groups is not None:
                counts["securityGroups"] = counts.get("securityGroups", 0) + groups
            if users is not None:
                counts["users"] = counts.get("users", 0) + users

    sections: list[ContextSectionStatus] = []

    def section(name: str, count: int, status: CompletenessStatus, note: str | None = None) -> None:
        sections.append(ContextSectionStatus(name=name, status=status, count=count, note=note))

    dims = sorted(found["dimensions"])
    section("Dimensions", len(dims),
            CompletenessStatus.complete if dims else CompletenessStatus.unavailable)
    section("Member Hierarchies", found["members"],
            CompletenessStatus.complete if found["members"] else CompletenessStatus.unavailable)
    section("Business Rules", rule_count,
            CompletenessStatus.complete if rule_count else CompletenessStatus.unavailable)
    section("Rule Bodies & Runtime Prompts", rule_count,
            CompletenessStatus.complete if rule_count else CompletenessStatus.unavailable)
    all_variables = found["variables"] + (found["user_vars"] or 0)
    section("Substitution & User Variables", all_variables,
            CompletenessStatus.complete if all_variables else CompletenessStatus.unavailable)
    referenced = len(found["forms_referenced"] | found["dashboards_referenced"])
    if found["forms_parsed"]:
        section("Forms", found["real_forms"], CompletenessStatus.complete)
    elif found["real_forms"]:
        section("Forms", found["real_forms"], CompletenessStatus.partial, note=_FORMS_UNPARSED_NOTE)
    elif referenced:
        section("Forms", referenced, CompletenessStatus.derived, note=_FORMS_REFERENCED_NOTE)
    else:
        section("Forms", 0, CompletenessStatus.unavailable)
    section("Data Integrations (FDMEE)", integrations,
            CompletenessStatus.derived if integrations else CompletenessStatus.unavailable)
    section("Security Groups", counts.get("securityGroups", 0),
            CompletenessStatus.derived if counts.get("securityGroups") else CompletenessStatus.unavailable)

    # Optional deep-parsed categories: complete when structured entries were
    # parsed, derived when only a name was recoverable, unavailable when the
    # folder is absent from the snapshot (the case for the shipped fixture).
    deep = found.get("deep", {})

    def _deep_status(info: dict) -> CompletenessStatus:
        if not info.get("present"):
            return CompletenessStatus.unavailable
        return CompletenessStatus.complete if info.get("parsed") else CompletenessStatus.derived

    for sec_name, kind in (("Smart Lists", "smartList"), ("Data Maps", "dataMap"),
                           ("Valid Intersections", "validIntersection"), ("Dashboards", "dashboard")):
        info = deep.get(kind, {})
        section(sec_name, int(info.get("total", 0)), _deep_status(info))

    analysis = SnapshotAnalysis(
        filename=filename,
        application=application,
        applications=sorted({c.application for c in components if c.application}),
        provenance=_provenance(archive),
        components=components,
        cubes=sorted(found["cubes"]),
        dimensions=dims,
        counts=counts,
        issues=issues,
    )
    return SnapshotBundle(analysis=analysis, records=records, sections=sections, counts=dict(counts))


def summarize_snapshot(analysis: SnapshotAnalysis) -> str:
    bits: list[str] = []
    if analysis.application:
        bits.append(f"application {analysis.application}")
    if analysis.cubes:
        bits.append(f"{len(analysis.cubes)} cubes")
    if analysis.dimensions:
        bits.append(f"{len(analysis.dimensions)} dimensions")
    labels = (("members", "members"), ("rules", "rules"), ("templates", "templates"),
              ("variables", "variables"), ("forms", "forms"), ("formsReferenced", "referenced forms"),
              ("dashboardsReferenced", "referenced dashboards"), ("smartLists", "smart lists"),
              ("dataMaps", "data maps"), ("validIntersections", "valid intersections"),
              ("dashboards", "dashboards"), ("integrations", "integrations"),
              ("pipelines", "pipelines"), ("securityGroups", "security groups"), ("users", "users"))
    bits.extend(f"{analysis.counts[key]} {label}" for key, label in labels if analysis.counts.get(key))
    prov = analysis.provenance
    if prov is not None and (prov.exported_at or prov.exported_by):
        who = f" by {prov.exported_by}" if prov.exported_by else ""
        when = f" {prov.exported_at}" if prov.exported_at else ""
        where = f" ({prov.service_instance})" if prov.service_instance else ""
        bits.append(f"exported{when}{who}{where}")
    if analysis.issues:
        bits.append(f"{len(analysis.issues)} parse issues")
    return "EPM application snapshot — " + "; ".join(bits) if bits else "EPM application snapshot"


# --- merge into context ----------------------------------------------------------

_SECTION_RANK = {"complete": 4, "derived": 3, "partial": 2, "unavailable": 1, "notRequested": 0}
_KIND_COUNT_KEYS = {"application": "applications", "cube": "cubes", "dimension": "dimensions",
                    "member": "members", "variable": "variables", "form": "forms", "rule": "rules",
                    "template": "templates", "integration": "integrations",
                    "securityGroup": "securityGroups", "smartList": "smartLists",
                    "dataMap": "dataMaps", "validIntersection": "validIntersections",
                    "dashboard": "dashboards"}
_CARRIED_COUNT_KEYS = ("userVariables", "formsReferenced", "dashboardsReferenced", "pipelines", "users")


def _normalize_app(name: str | None) -> str:
    return "".join(ch for ch in (name or "").casefold() if ch.isalnum())


def _record_key(rec: dict) -> tuple[str, str, str]:
    return (rec.get("kind") or "", _normalize_app(rec.get("dimension")), (rec.get("name") or "").casefold())


def _next_label(session: Session, project_id: str, prefix: str) -> str:
    existing = [cv for cv in context_store.list_context_versions(session, project_id)
                if cv.label.startswith(prefix)]
    return f"{prefix}{len(existing) + 1}"


def merge_snapshot_into_context(
    session: Session,
    project_id: str,
    bundle: SnapshotBundle,
    *,
    standalone: bool = False,
    filename: str | None = None,
) -> ContextVersion:
    analysis = bundle.analysis
    active = None if standalone else context_store.get_active_context(session, project_id)
    mode = "hybrid" if active is not None else "snapshot"
    snap_app = analysis.application or (analysis.applications[0] if analysis.applications else "SNAPSHOT")
    application = active.application if active is not None else snap_app

    # Snapshot records are copied, never mutated in the bundle; when the snapshot
    # app matches the live app (normalized: MCW_PCF == MCWPCF) they adopt the
    # live application name so retrieval stays uniform.
    snapshot_records = [{**r, "data": dict(r.get("data") or {})} for r in bundle.records]
    if active is not None and _normalize_app(active.application) == _normalize_app(snap_app):
        for rec in snapshot_records:
            if _normalize_app(rec.get("application")) == _normalize_app(snap_app):
                rec["application"] = active.application
                if "application" in rec["data"]:
                    rec["data"]["application"] = active.application
                # The application record itself must also adopt the live name,
                # or the hybrid context ends up claiming two applications.
                if rec.get("kind") == "application" and _normalize_app(rec.get("name")) == _normalize_app(snap_app):
                    rec["name"] = active.application
                    rec["search_text"] = active.application.lower()
                    if "name" in rec["data"]:
                        rec["data"]["name"] = active.application

    live_records: list[dict] = []
    if active is not None:
        for r in context_store.get_records(session, active.id):
            live_records.append({
                "kind": r.kind,
                "name": r.name,
                "dimension": r.dimension,
                "cube": r.cube,
                "alias": r.alias,
                "parent": r.parent,
                "application": r.application,
                "search_text": r.search_text,
                "data": dict(r.data or {}),
            })
    live_keys = {_record_key(rec) for rec in live_records}
    # Referenced-only stubs (form names lifted from navigation flows) never
    # replace a live record that carries a real definition — they only fill gaps.
    snapshot_records = [rec for rec in snapshot_records
                        if not (rec["data"].get("referencedOnly") and _record_key(rec) in live_keys)]
    snap_keys = {_record_key(rec) for rec in snapshot_records}
    # Remaining same-key snapshot records replace their live counterparts.
    records = [rec for rec in live_records if _record_key(rec) not in snap_keys]
    records.extend(snapshot_records)

    counts: dict[str, int] = {}
    for rec in records:
        key = _KIND_COUNT_KEYS.get(rec["kind"])
        if key:
            counts[key] = counts.get(key, 0) + 1
    for key in _CARRIED_COUNT_KEYS:
        if key in bundle.counts:
            counts[key] = bundle.counts[key]
    counts = dict(sorted(counts.items()))

    # Sections: for each name keep the better of (live, snapshot); snapshot notes
    # travel with snapshot wins.
    live_sections = list((active.manifest or {}).get("sections") or []) if active is not None else []
    snap_sections = {s.name: s.model_dump(by_alias=True) for s in bundle.sections}
    merged_sections: list[dict] = []
    merged_names: list[str] = []
    seen: set[str] = set()
    for live in live_sections:
        name = live.get("name") or ""
        seen.add(name)
        snap = snap_sections.get(name)
        if snap and _SECTION_RANK.get(snap["status"], 0) > _SECTION_RANK.get(live.get("status"), 0):
            merged_sections.append(snap)
            merged_names.append(name)
        else:
            merged_sections.append(live)
    for status in bundle.sections:
        if status.name in seen:
            continue
        merged_sections.append(snap_sections[status.name])
        if active is not None and _SECTION_RANK.get(snap_sections[status.name]["status"], 0) > 1:
            merged_names.append(status.name)

    snap_dump = analysis.model_dump(by_alias=True)
    if filename and not snap_dump.get("filename"):
        snap_dump["filename"] = filename
    snap_dump = {k: v for k, v in snap_dump.items() if v not in ([], {}, None)}

    label = _next_label(session, project_id, f"{application}_{mode}_")
    manifest = dict(active.manifest or {}) if active is not None else {}
    manifest.update({
        "mode": mode,
        "application": application,
        "contextVersion": label,
        "counts": counts,
        "sections": merged_sections,
        "snapshot": snap_dump,
    })
    if active is not None:
        manifest["mergedSections"] = merged_names

    return context_store.persist_context(
        session,
        project_id,
        application,
        mode=mode,
        label=label,
        manifest=manifest,
        counts=counts,
        records=records,
        fingerprint=active.fingerprint if active is not None else None,
        environment_id=active.environment_id if active is not None else None,
        activate=True,
    )
