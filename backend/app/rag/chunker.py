"""Chunk construction for the RAG index.

Turns the ContextRecords of one context version into retrieval chunks:
rule/template bodies are split into overlapping windows, members are collapsed
into one "naming convention digest" per dimension (never one chunk per member),
variables become one chunk each. All chunk text is passed through the central
secret redaction before it is stored, tokenized or embedded.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field

from ..security.redaction import redact_text

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
SNIPPET_LIMIT = 700
MEMBER_SAMPLE_LIMIT = 40

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens (>= 2 chars). Underscore-joined names like
    ``OCF_Daily`` are kept BOTH as the full token (``ocf_daily``) and as their
    parts (``ocf``, ``daily``) so either spelling matches."""
    out: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        full = raw.strip("_")
        if "_" in full:
            if len(full) >= 2:
                out.append(full)
            out.extend(p for p in full.split("_") if len(p) >= 2)
        elif len(full) >= 2:
            out.append(full)
    return out


@dataclass
class Chunk:
    """One retrieval unit. ``text`` (redacted) feeds BM25 tokens and embeddings;
    ``snippet`` is the redacted head shown to the user."""

    kind: str
    name: str
    cube: str | None = None
    dimension: str | None = None
    text: str = ""
    snippet: str = ""
    tokens: list[str] = field(default_factory=list)


def _chunk(kind: str, name: str, text: str, *, cube: str | None = None,
           dimension: str | None = None, snippet: str | None = None) -> Chunk:
    red = redact_text(text or "")
    snip = redact_text(snippet) if snippet is not None else red
    return Chunk(kind=kind, name=name, cube=cube, dimension=dimension, text=red,
                 snippet=snip[:SNIPPET_LIMIT], tokens=tokenize(red))


def split_body(body: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """~1200-char windows with ~150-char overlap; never a degenerate tail."""
    if len(body) <= size:
        return [body] if body.strip() else []
    step = size - overlap
    out: list[str] = []
    i = 0
    while i < len(body):
        out.append(body[i:i + size])
        if i + size >= len(body):
            break
        i += step
    return out


def _script_chunks(kind: str, name: str, cube: str | None, data: dict) -> list[Chunk]:
    prompts = [p for p in (data.get("runtimePrompts") or []) if isinstance(p, str)]
    header = " ".join(x for x in [name, cube or "", *prompts] if x)
    body = str(data.get("body") or "")
    pieces = split_body(body)
    if not pieces:
        return [_chunk(kind, name, header, cube=cube)]
    return [_chunk(kind, name, f"{header}\n{piece}", cube=cube) for piece in pieces]


def _form_chunk(record) -> Chunk:
    data = record.data or {}
    parts = [record.name]
    if record.cube:
        parts.append(record.cube)
    if data.get("folder"):
        parts.append(str(data["folder"]))
    if data.get("description"):
        parts.append(str(data["description"]))
    if data.get("definition"):
        parts.append(json.dumps(data["definition"], sort_keys=True, default=str)[:CHUNK_SIZE])
    text = " ".join(parts)
    if data.get("referencedOnly"):
        text = f"{text} (referenced only)"
    return _chunk("form", record.name, text, cube=record.cube)


def _variable_chunk(record) -> Chunk:
    data = record.data or {}
    value = data.get("value")
    text = f"{record.name} = {value}" if value not in (None, "") else record.name
    plan_type = data.get("planType") or data.get("plan_type") or record.cube
    if plan_type:
        text = f"{text} (planType: {plan_type})"
    return _chunk("variable", record.name, text, cube=record.cube,
                  dimension=record.dimension)


def _smartlist_chunk(record) -> Chunk:
    data = record.data or {}
    labels = [str(e.get("label") or e.get("name") or "")
              for e in (data.get("entries") or []) if isinstance(e, dict)]
    text = " ".join(x for x in [record.name, *labels] if x)
    return _chunk("smartList", record.name, text)


def _datamap_chunk(record) -> Chunk:
    data = record.data or {}
    parts = [record.name]
    if data.get("sourceCube"):
        parts.append(f"from {data['sourceCube']}")
    if data.get("targetCube"):
        parts.append(f"to {data['targetCube']}")
    return _chunk("dataMap", record.name, " ".join(parts))


def _intersection_chunk(record) -> Chunk:
    data = record.data or {}
    dims = [str(d) for d in (data.get("dimensions") or [])]
    return _chunk("validIntersection", record.name, " ".join([record.name, *dims]))


def _dashboard_chunk(record) -> Chunk:
    data = record.data or {}
    forms = [str(f) for f in (data.get("forms") or [])]
    return _chunk("dashboard", record.name, " ".join([record.name, *forms]), cube=record.cube)


def _member_digest(dimension: str, members: list[tuple[str, str | None]]) -> Chunk:
    """Per-dimension convention digest: sample of member names/aliases plus the
    common ``PREFIX_`` naming patterns — never one chunk per member."""
    names = sorted({name for name, _ in members})
    aliases = {name: alias for name, alias in members if alias}
    sample = names[:MEMBER_SAMPLE_LIMIT]
    listed = ", ".join(f"{n} ({aliases[n]})" if n in aliases else n for n in sample)
    prefixes = Counter(n.split("_", 1)[0] + "_" for n in names if "_" in n and len(n.split("_", 1)[0]) >= 2)
    common = sorted(p for p, c in prefixes.items() if c >= 2)
    text = f"Dimension {dimension} members: {listed}"
    if common:
        text += f". Naming prefixes: {' '.join(common)}"
    return _chunk("member", dimension, text, dimension=dimension)


def build_chunks(records) -> list[Chunk]:
    """Deterministic chunk list from ContextRecords (stable ordering regardless
    of database row order)."""
    ordered = sorted(records, key=lambda r: (r.kind or "", r.name or "", r.dimension or "", r.cube or ""))
    chunks: list[Chunk] = []
    members_by_dim: dict[str, list[tuple[str, str | None]]] = {}
    for r in ordered:
        data = r.data or {}
        if r.kind in ("rule", "template"):
            chunks.extend(_script_chunks(r.kind, r.name, r.cube, data))
        elif r.kind == "form":
            chunks.append(_form_chunk(r))
        elif r.kind == "variable":
            chunks.append(_variable_chunk(r))
        elif r.kind == "smartList":
            chunks.append(_smartlist_chunk(r))
        elif r.kind == "dataMap":
            chunks.append(_datamap_chunk(r))
        elif r.kind == "validIntersection":
            chunks.append(_intersection_chunk(r))
        elif r.kind == "dashboard":
            chunks.append(_dashboard_chunk(r))
        elif r.kind == "member":
            dim = r.dimension or data.get("dimension") or ""
            if dim:
                members_by_dim.setdefault(dim, []).append((r.name, r.alias))
    for dim in sorted(members_by_dim):
        chunks.append(_member_digest(dim, members_by_dim[dim]))
    return chunks
