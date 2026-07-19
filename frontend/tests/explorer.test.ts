import { describe, expect, it } from "vitest";
import { buildDimensionTrees } from "../src/pages/ExplorerPage";
import type { MemberMatch } from "../src/schemas/types";

function m(member: string, dimension: string, parent: string | null = null, alias: string | null = null): MemberMatch {
  return { query: "", member, dimension, application: "APP", parent, alias };
}

describe("buildDimensionTrees", () => {
  it("groups members by dimension and rebuilds each hierarchy from parent pointers", () => {
    const trees = buildDimensionTrees([
      m("Total Entity", "Entity"),
      m("US", "Entity", "Total Entity"),
      m("US East", "Entity", "US"),
      m("Jan", "Period"),
    ]);
    expect(trees.map((t) => t.name)).toEqual(["Entity", "Period"]);
    const entity = trees[0];
    expect(entity.memberCount).toBe(3);
    expect(entity.roots).toHaveLength(1);
    expect(entity.roots[0].match.member).toBe("Total Entity");
    expect(entity.roots[0].children[0].match.member).toBe("US");
    expect(entity.roots[0].children[0].children[0].match.member).toBe("US East");
  });

  it("treats members whose parent is missing from the context as roots", () => {
    const trees = buildDimensionTrees([m("Orphan", "Account", "NotLoaded")]);
    expect(trees[0].roots.map((n) => n.match.member)).toEqual(["Orphan"]);
  });

  it("sorts dimensions alphabetically and counts members per dimension", () => {
    const trees = buildDimensionTrees([m("x", "Zeta"), m("a", "Alpha"), m("b", "Alpha", "a")]);
    expect(trees.map((t) => [t.name, t.memberCount])).toEqual([["Alpha", 2], ["Zeta", 1]]);
  });
});
