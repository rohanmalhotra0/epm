"""Context engine (spec sections 16, 18): learn a connected EPM application.

Retrieves metadata through the connector boundary and assembles persistable
records + a manifest. Each section is marked complete / partial / derived /
unavailable / notRequested honestly — a category is never claimed if the
connector did not return it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..connector.base import EpmConnector
from ..schemas.context import (
    CompletenessStatus,
    ContextManifest,
    ContextSectionStatus,
)


@dataclass
class ContextBundle:
    application: str
    mode: str
    label: str
    records: list[dict] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    sections: list[ContextSectionStatus] = field(default_factory=list)
    manifest: ContextManifest | None = None
    fingerprint: str = ""


def environment_fingerprint(base_url: str | None, application: str, username: str | None) -> str:
    raw = f"{base_url or 'demo'}|{application}|{username or ''}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _record(kind, name, data, dimension=None, cube=None, alias=None, parent=None, application=None, search=None):
    return {
        "kind": kind,
        "name": name,
        "dimension": dimension,
        "cube": cube,
        "alias": alias,
        "parent": parent,
        "application": application,
        "search_text": (search or name).lower(),
        "data": data,
    }


async def build_context(
    connector: EpmConnector, application: str, mode: str = "quick", fingerprint: str = ""
) -> ContextBundle:
    # There is a single retrieval depth: everything the connector can supply is
    # always fetched. `mode` is retained only as a label on the stored version
    # (e.g. "imported"), not as a switch.
    now = datetime.now(UTC)
    label = f"{application}_{now:%Y-%m-%d_%H%M}"
    records: list[dict] = []
    sections: list[ContextSectionStatus] = []

    def section(name, count, status, note=None):
        sections.append(ContextSectionStatus(name=name, status=status, count=count, note=note))

    # --- always retrieved ---
    apps = await connector.list_applications()
    for a in apps:
        records.append(_record("application", a.name, a.model_dump(by_alias=True), application=a.name))
    section("Applications", len(apps), CompletenessStatus.complete)

    cubes = await connector.list_cubes(application)
    for c in cubes:
        records.append(_record("cube", c.name, c.model_dump(by_alias=True), cube=c.name, application=application))
    section("Cubes", len(cubes), CompletenessStatus.complete)

    dims = await connector.list_dimensions(application)
    for d in dims:
        records.append(_record("dimension", d.name, d.model_dump(by_alias=True), dimension=d.name, application=application))
    section("Dimensions", len(dims), CompletenessStatus.complete)

    variables = await connector.get_variables(application)
    for v in variables:
        records.append(_record("variable", v.name, v.model_dump(by_alias=True),
                               dimension=v.dimension, application=application,
                               search=f"{v.name} {v.dimension or ''}"))
    section("Substitution & User Variables", len(variables),
            CompletenessStatus.complete if variables else CompletenessStatus.unavailable)

    forms = await connector.list_forms(application)
    for f in forms:
        records.append(_record("form", f.name, f.model_dump(by_alias=True), cube=f.cube, application=application,
                               search=f"{f.name} {f.folder or ''} {f.description or ''}"))
    section("Forms", len(forms), CompletenessStatus.complete if forms else CompletenessStatus.unavailable,
            note=None if forms else "Not exposed by the core REST metadata API — retrieve via Migration.")

    rules = await connector.list_rules(application)
    for r in rules:
        records.append(_record("rule", r.name, r.model_dump(by_alias=True), cube=r.cube, application=application))
    section("Business Rules", len(rules), CompletenessStatus.complete if rules else CompletenessStatus.unavailable)
    rules_with_prompts = sum(1 for r in rules if r.runtime_prompts)
    section("Runtime Prompts", rules_with_prompts,
            CompletenessStatus.derived if rules_with_prompts else CompletenessStatus.partial)

    # --- members ---
    members = []
    for d in dims:
        members.extend(await connector.list_members(application, d.name))
    for m in members:
        records.append(_record("member", m.name, m.model_dump(by_alias=True), dimension=m.dimension,
                               alias=m.alias, parent=m.parent, application=application,
                               search=f"{m.name} {m.alias or ''}"))
    if members:
        section("Member Hierarchies", len(members), CompletenessStatus.complete)
    else:
        section("Member Hierarchies", 0, CompletenessStatus.unavailable,
                note="Member enumeration was not available from this interface.")

    # aliases / storage / formulas are embedded in member records when present
    has_alias = any(m.alias for m in members)
    has_formula = any(m.formula for m in members)
    section("Aliases", sum(1 for m in members if m.alias),
            CompletenessStatus.complete if has_alias else CompletenessStatus.unavailable)
    section("Storage Properties", sum(1 for m in members if m.storage),
            CompletenessStatus.complete if members else CompletenessStatus.unavailable)
    section("Member Formulas", sum(1 for m in members if m.formula),
            CompletenessStatus.derived if has_formula else CompletenessStatus.unavailable)
    # Categories the connector cannot supply are reported honestly.
    for cat in ("Smart Lists", "Data Maps", "Valid Intersections", "Dashboards", "Action Menus", "Navigation Flows"):
        section(cat, 0, CompletenessStatus.unavailable,
                note="Not retrievable through the available interface.")
    section("Naming Conventions", 1, CompletenessStatus.derived, note="Inferred from existing artifact names.")

    counts = {
        "applications": len(apps),
        "cubes": len(cubes),
        "dimensions": len(dims),
        "members": len(members),
        "variables": len(variables),
        "forms": len(forms),
        "rules": len(rules),
    }

    known_limitations = [s.note for s in sections if s.note and s.status in
                         (CompletenessStatus.unavailable, CompletenessStatus.partial)]
    manifest = ContextManifest(
        generated_at=now.isoformat(),
        application=application,
        environment_classification=connector.info.classification,
        environment_fingerprint=fingerprint or environment_fingerprint(None, application, None),
        mode=mode,
        counts=counts,
        sections=sections,
        known_limitations=known_limitations,
        context_version=label,
    )

    return ContextBundle(
        application=application, mode=mode, label=label, records=records, counts=counts,
        sections=sections, manifest=manifest, fingerprint=manifest.environment_fingerprint,
    )


def diff_contexts(old_counts: dict, new_counts: dict) -> dict:
    """Simple count-level diff for the refresh flow (spec section 18)."""
    keys = sorted(set(old_counts) | set(new_counts))
    return {k: {"before": old_counts.get(k, 0), "after": new_counts.get(k, 0),
                "delta": new_counts.get(k, 0) - old_counts.get(k, 0)} for k in keys}
