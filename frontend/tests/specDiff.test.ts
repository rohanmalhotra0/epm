import { describe, expect, it } from "vitest";
import { diffSpecs, flattenSpec, formatValue } from "../src/utils/specDiff";

describe("flattenSpec", () => {
  it("flattens nested objects and arrays to dotted paths", () => {
    const flat = flattenSpec({
      name: "Form A",
      layout: { rows: [{ dimension: "Account" }, { dimension: "Period" }] },
      hidden: [],
      options: {},
    });
    expect(Object.fromEntries(flat)).toEqual({
      name: "Form A",
      "layout.rows[0].dimension": "Account",
      "layout.rows[1].dimension": "Period",
      hidden: "[]",
      options: "{}",
    });
  });

  it("keeps primitive types and null as leaves", () => {
    const flat = flattenSpec({ a: 1, b: true, c: null });
    expect(flat.get("a")).toBe(1);
    expect(flat.get("b")).toBe(true);
    expect(flat.get("c")).toBeNull();
  });

  it("handles a primitive root", () => {
    expect(flattenSpec("x").get("(root)")).toBe("x");
  });
});

describe("diffSpecs", () => {
  const left = { name: "Payroll", cube: "OEP_WFP", rows: [{ member: "Salaries" }], size: 84 };
  const right = { name: "Payroll v2", cube: "OEP_WFP", rows: [{ member: "Salaries" }, { member: "Wages" }] };

  it("reports added, removed and changed paths (unchanged omitted)", () => {
    const rows = diffSpecs(left, right);
    const byPath = Object.fromEntries(rows.map((r) => [r.path, r]));
    expect(byPath["name"]).toMatchObject({ kind: "changed", left: "Payroll", right: "Payroll v2" });
    expect(byPath["rows[1].member"]).toMatchObject({ kind: "added", right: "Wages" });
    expect(byPath["size"]).toMatchObject({ kind: "removed", left: 84 });
    expect(byPath["cube"]).toBeUndefined();
    expect(byPath["rows[0].member"]).toBeUndefined();
  });

  it("returns no rows for identical specs", () => {
    expect(diffSpecs(left, JSON.parse(JSON.stringify(left)))).toEqual([]);
  });

  it("sorts rows by path", () => {
    const rows = diffSpecs({ b: 1, a: 1 }, { b: 2, a: 2 });
    expect(rows.map((r) => r.path)).toEqual(["a", "b"]);
  });
});

describe("formatValue", () => {
  it("shows strings bare and other values as JSON", () => {
    expect(formatValue("abc")).toBe("abc");
    expect(formatValue(12)).toBe("12");
    expect(formatValue(null)).toBe("null");
    expect(formatValue(undefined)).toBe("");
  });
});
