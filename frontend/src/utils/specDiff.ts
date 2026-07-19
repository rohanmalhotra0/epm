// Structural field-level diff of two artifact spec JSON documents.
// Each spec is flattened to path -> value pairs; the diff is then a simple
// set comparison over paths. No external diff library.

export type FlatSpec = Map<string, unknown>;

export interface DiffRow {
  path: string;
  kind: "added" | "removed" | "changed";
  /** value in the left (first) spec — set for removed/changed */
  left?: unknown;
  /** value in the right (second) spec — set for added/changed */
  right?: unknown;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * Flatten a JSON value into dotted-path -> primitive pairs.
 * Objects contribute `parent.key`, arrays `parent[i]`. Empty objects/arrays
 * are kept as their own leaf so "field became {}" is still visible.
 */
export function flattenSpec(value: unknown, prefix = "", out: FlatSpec = new Map()): FlatSpec {
  if (Array.isArray(value)) {
    if (value.length === 0) out.set(prefix || "(root)", "[]");
    value.forEach((item, i) => flattenSpec(item, `${prefix}[${i}]`, out));
  } else if (isPlainObject(value)) {
    const keys = Object.keys(value);
    if (keys.length === 0) out.set(prefix || "(root)", "{}");
    for (const key of keys) {
      flattenSpec(value[key], prefix ? `${prefix}.${key}` : key, out);
    }
  } else {
    out.set(prefix || "(root)", value);
  }
  return out;
}

/** Render a leaf value for display. */
export function formatValue(v: unknown): string {
  if (v === undefined) return "";
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

/**
 * Field-level diff between two specs. Rows are sorted by path so related
 * fields group together; unchanged paths are omitted.
 */
export function diffSpecs(left: unknown, right: unknown): DiffRow[] {
  const a = flattenSpec(left);
  const b = flattenSpec(right);
  const paths = new Set([...a.keys(), ...b.keys()]);
  const rows: DiffRow[] = [];
  for (const path of paths) {
    const inA = a.has(path);
    const inB = b.has(path);
    if (inA && !inB) rows.push({ path, kind: "removed", left: a.get(path) });
    else if (!inA && inB) rows.push({ path, kind: "added", right: b.get(path) });
    else if (!Object.is(a.get(path), b.get(path))) {
      rows.push({ path, kind: "changed", left: a.get(path), right: b.get(path) });
    }
  }
  rows.sort((x, y) => x.path.localeCompare(y.path));
  return rows;
}
