"""Deterministic schema codegen: Pydantic -> JSON Schema -> TypeScript + Zod.

Python + Pydantic own the canonical schemas (spec section 3). This module is the
single generator used both by ``scripts/export_schema.py`` (to write the committed
frontend files) and by ``tests/test_schema_drift.py`` (to fail CI on drift). The
output is fully deterministic: ``$defs`` are emitted in sorted order.
"""

from __future__ import annotations

import json

from pydantic.json_schema import models_json_schema

from .schemas import CANONICAL_MODELS

_HEADER = (
    "/* eslint-disable */\n"
    "// ---------------------------------------------------------------------------\n"
    "// GENERATED FILE — DO NOT EDIT BY HAND.\n"
    "// Source of truth: backend Pydantic models (app/schemas/*.py).\n"
    "// Regenerate with:  python -m scripts.export_schema  (from backend/)\n"
    "// A backend drift test fails if this file is out of sync.\n"
    "// ---------------------------------------------------------------------------\n"
)

_TS_PRIMITIVES = {
    "string": "string",
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "null": "null",
}


def build_json_schema() -> dict:
    """Combined JSON Schema document with a sorted ``$defs`` map."""
    _, top = models_json_schema(
        [(m, "serialization") for m in CANONICAL_MODELS.values()],
        ref_template="#/$defs/{model}",
    )
    defs = top.get("$defs", {})
    return {"$defs": {name: defs[name] for name in sorted(defs)}}


# --- shared schema walking --------------------------------------------------


def _ref_name(schema: dict) -> str | None:
    ref = schema.get("$ref")
    if ref:
        return ref.split("/")[-1]
    # allOf with a single ref (Pydantic default-wrapping)
    all_of = schema.get("allOf")
    if all_of and len(all_of) == 1 and "$ref" in all_of[0]:
        return all_of[0]["$ref"].split("/")[-1]
    return None


def _split_nullable(schema: dict) -> tuple[dict, bool]:
    """Return (effective schema, is_nullable) collapsing anyOf-with-null."""
    any_of = schema.get("anyOf")
    if any_of:
        non_null = [s for s in any_of if s.get("type") != "null"]
        nullable = any(s.get("type") == "null" for s in any_of)
        if len(non_null) == 1:
            return non_null[0], nullable
        return {"anyOf": non_null}, nullable
    return schema, False


# --- TypeScript -------------------------------------------------------------


def _ts_type(schema: dict) -> str:
    schema, nullable = _split_nullable(schema)
    ts = _ts_type_inner(schema)
    return f"{ts} | null" if nullable else ts


def _ts_type_inner(schema: dict) -> str:
    ref = _ref_name(schema)
    if ref:
        return ref
    if "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    if "const" in schema:
        return json.dumps(schema["const"])
    if "anyOf" in schema:
        return " | ".join(_ts_type(s) for s in schema["anyOf"])
    t = schema.get("type")
    if t == "array":
        items = schema.get("items", {})
        inner = _ts_type(items) if items else "unknown"
        return f"Array<{inner}>"
    if t == "object":
        ap = schema.get("additionalProperties")
        if isinstance(ap, dict):
            return f"Record<string, {_ts_type(ap)}>"
        return "Record<string, unknown>"
    if isinstance(t, list):
        return " | ".join(_TS_PRIMITIVES.get(x, "unknown") for x in t)
    return _TS_PRIMITIVES.get(t, "unknown")


def _emit_ts_interface(name: str, schema: dict) -> str:
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    lines = [f"export interface {name} {{"]
    for prop, ps in props.items():
        eff, nullable = _split_nullable(ps)
        optional = prop not in required
        # The Pydantic serializer always emits list/dict fields (default_factory),
        # so treat non-nullable containers as required in TS — cleaner client code.
        if optional and not nullable and eff.get("type") in ("array", "object"):
            optional = False
        desc = ps.get("description")
        if desc:
            lines.append(f"  /** {desc} */")
        q = "?" if optional else ""
        lines.append(f"  {prop}{q}: {_ts_type(ps)};")
    lines.append("}")
    return "\n".join(lines)


def generate_typescript(doc: dict) -> str:
    out = [_HEADER, ""]
    for name, schema in doc["$defs"].items():
        if "enum" in schema:
            values = " |\n  ".join(json.dumps(v) for v in schema["enum"])
            out.append(f"export type {name} =\n  {values};\n")
        elif schema.get("type") == "object" or "properties" in schema:
            out.append(_emit_ts_interface(name, schema) + "\n")
        else:  # scalar alias
            out.append(f"export type {name} = {_ts_type(schema)};\n")
    return "\n".join(out).rstrip() + "\n"


# --- Zod --------------------------------------------------------------------


def _zod_type(schema: dict) -> str:
    schema, nullable = _split_nullable(schema)
    z = _zod_type_inner(schema)
    return f"{z}.nullable()" if nullable else z


def _zod_type_inner(schema: dict) -> str:
    ref = _ref_name(schema)
    if ref:
        return f"{ref}Schema"
    if "enum" in schema:
        return "z.enum([" + ", ".join(json.dumps(v) for v in schema["enum"]) + "])"
    if "const" in schema:
        return f"z.literal({json.dumps(schema['const'])})"
    if "anyOf" in schema:
        return "z.union([" + ", ".join(_zod_type(s) for s in schema["anyOf"]) + "])"
    t = schema.get("type")
    if t == "array":
        items = schema.get("items", {})
        return f"z.array({_zod_type(items) if items else 'z.unknown()'})"
    if t == "object":
        ap = schema.get("additionalProperties")
        if isinstance(ap, dict):
            return f"z.record(z.string(), {_zod_type(ap)})"
        return "z.record(z.string(), z.unknown())"
    if t == "string":
        return "z.string()"
    if t in ("integer", "number"):
        return "z.number()"
    if t == "boolean":
        return "z.boolean()"
    if t == "null":
        return "z.null()"
    return "z.unknown()"


def _emit_zod_object(name: str, schema: dict) -> str:
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    lines = [f"export const {name}Schema = z.lazy(() => z.object({{"]
    for prop, ps in props.items():
        optional = prop not in required
        expr = _zod_type(ps)
        if optional:
            expr += ".optional()"
        lines.append(f"  {prop}: {expr},")
    lines.append("}));")
    return "\n".join(lines)


def generate_zod(doc: dict) -> str:
    out = [_HEADER, 'import { z } from "zod";', ""]
    for name, schema in doc["$defs"].items():
        if "enum" in schema:
            values = ", ".join(json.dumps(v) for v in schema["enum"])
            out.append(f"export const {name}Schema = z.enum([{values}]);\n")
        elif schema.get("type") == "object" or "properties" in schema:
            out.append(_emit_zod_object(name, schema) + "\n")
        else:
            out.append(f"export const {name}Schema = z.lazy(() => {_zod_type(schema)});\n")
    return "\n".join(out).rstrip() + "\n"


def generate_all() -> dict[str, str]:
    doc = build_json_schema()
    return {
        "schemas.json": json.dumps(doc, indent=2, sort_keys=True) + "\n",
        "types.ts": generate_typescript(doc),
        "zod.ts": generate_zod(doc),
    }
