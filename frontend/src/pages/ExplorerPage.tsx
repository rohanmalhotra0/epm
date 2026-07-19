// Metadata explorer: browse the active context's dimensions and member
// hierarchies (application → dimensions → members) with filtering and a
// detail card for the selected member.

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search, Tile } from "@carbon/react";
import { api } from "../api/client";
import { useContexts } from "../api/hooks";
import { useUi } from "../store/ui";
import type { MemberMatch } from "../schemas/types";
import "../styles/feature-pages.css";

const MEMBER_FETCH_LIMIT = 10000;

interface MemberNode {
  match: MemberMatch;
  children: MemberNode[];
}

interface DimensionTree {
  name: string;
  memberCount: number;
  roots: MemberNode[];
}

/** Group the flat member list by dimension and rebuild each hierarchy from parent pointers. */
export function buildDimensionTrees(matches: MemberMatch[]): DimensionTree[] {
  const byDim = new Map<string, MemberMatch[]>();
  for (const m of matches) {
    const list = byDim.get(m.dimension) ?? [];
    list.push(m);
    byDim.set(m.dimension, list);
  }
  const trees: DimensionTree[] = [];
  for (const [dim, members] of byDim) {
    const nodes = new Map<string, MemberNode>();
    for (const m of members) {
      if (!nodes.has(m.member)) nodes.set(m.member, { match: m, children: [] });
    }
    const roots: MemberNode[] = [];
    for (const node of nodes.values()) {
      const parent = node.match.parent ? nodes.get(node.match.parent) : undefined;
      if (parent && parent !== node) parent.children.push(node);
      else roots.push(node);
    }
    trees.push({ name: dim, memberCount: nodes.size, roots });
  }
  trees.sort((a, b) => a.name.localeCompare(b.name));
  return trees;
}

function matchesFilter(m: MemberMatch, f: string): boolean {
  return m.member.toLowerCase().includes(f) || (m.alias ?? "").toLowerCase().includes(f);
}

function MemberRow({ node, depth, selected, onSelect }: {
  node: MemberNode;
  depth: number;
  selected: MemberMatch | null;
  onSelect: (m: MemberMatch) => void;
}) {
  const [open, setOpen] = useState(depth === 0);
  const hasChildren = node.children.length > 0;
  const isSelected = selected?.member === node.match.member && selected?.dimension === node.match.dimension;
  return (
    <li>
      <button
        type="button"
        className={`explorer-node ${isSelected ? "selected" : ""}`}
        style={{ paddingLeft: 10 + depth * 16 }}
        aria-expanded={hasChildren ? open : undefined}
        onClick={() => {
          onSelect(node.match);
          if (hasChildren) setOpen((v) => !v);
        }}
      >
        <span className="twisty">{hasChildren ? (open ? "▾" : "▸") : "·"}</span>
        <span>{node.match.member}</span>
        {node.match.alias && node.match.alias !== node.match.member && (
          <span className="alias">{node.match.alias}</span>
        )}
      </button>
      {hasChildren && open && (
        <ul>
          {node.children.map((c) => (
            <MemberRow key={c.match.member} node={c} depth={depth + 1} selected={selected} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </li>
  );
}

function DimensionRow({ tree, filter, selected, onSelect }: {
  tree: DimensionTree;
  filter: string;
  selected: MemberMatch | null;
  onSelect: (m: MemberMatch) => void;
}) {
  const [open, setOpen] = useState(false);
  const filtering = filter.length > 0;
  const filtered = useMemo(() => {
    if (!filtering) return [];
    const out: MemberMatch[] = [];
    const walk = (nodes: MemberNode[]) => {
      for (const n of nodes) {
        if (matchesFilter(n.match, filter)) out.push(n.match);
        walk(n.children);
      }
    };
    walk(tree.roots);
    return out;
  }, [tree, filter, filtering]);

  if (filtering && filtered.length === 0) return null;
  const expanded = filtering || open;
  return (
    <li>
      <button
        type="button"
        className="explorer-node"
        aria-expanded={expanded}
        onClick={() => setOpen((v) => !v)}
        style={{ fontWeight: 600 }}
      >
        <span className="twisty">{expanded ? "▾" : "▸"}</span>
        <span>{tree.name}</span>
        <span className="count tag-inline">
          {filtering ? `${filtered.length} of ${tree.memberCount}` : tree.memberCount} members
        </span>
      </button>
      {expanded && (
        <ul>
          {filtering
            ? filtered.map((m) => (
                <li key={m.member}>
                  <button
                    type="button"
                    className={`explorer-node ${selected?.member === m.member && selected?.dimension === m.dimension ? "selected" : ""}`}
                    style={{ paddingLeft: 26 }}
                    onClick={() => onSelect(m)}
                  >
                    <span className="twisty">·</span>
                    <span>{m.member}</span>
                    {m.alias && m.alias !== m.member && <span className="alias">{m.alias}</span>}
                  </button>
                </li>
              ))
            : tree.roots.map((n) => (
                <MemberRow key={n.match.member} node={n} depth={1} selected={selected} onSelect={onSelect} />
              ))}
        </ul>
      )}
    </li>
  );
}

function DetailRow({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="detail-row">
      <div className="k">{label}</div>
      <div className="v">{value}</div>
    </div>
  );
}

export function ExplorerPage() {
  const pid = useUi((s) => s.currentProjectId) ?? undefined;
  const { data: contexts = [], isLoading: contextsLoading } = useContexts(pid);
  const active = contexts.find((c) => c.active);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<MemberMatch | null>(null);

  const { data: memberData, isLoading: membersLoading } = useQuery({
    queryKey: ["explorerMembers", pid, active?.id],
    enabled: !!pid && !!active,
    queryFn: () =>
      api<{ matches: MemberMatch[] }>(
        `/api/projects/${pid}/context/search?q=&limit=${MEMBER_FETCH_LIMIT}`,
      ),
  });
  const matches = memberData?.matches ?? [];
  const trees = useMemo(() => buildDimensionTrees(matches), [matches]);

  if (!pid) {
    return (
      <div className="page">
        <h2>Metadata explorer</h2>
        <div className="page-sub">Select a project first.</div>
      </div>
    );
  }

  if (!contextsLoading && !active) {
    return (
      <div className="page">
        <h2>Metadata explorer</h2>
        <div className="page-sub">Browse the dimensions and member hierarchies of the connected EPM application.</div>
        <Tile style={{ maxWidth: 520 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>No active context yet</div>
          <div style={{ fontSize: 13, color: "var(--cds-text-secondary, #a8a8a8)", lineHeight: 1.5 }}>
            The explorer reads from your project's active context. Go to{" "}
            <Link to="/contexts">Contexts</Link> and build a quick or deep context — the metadata will then be
            browsable here.
          </div>
        </Tile>
      </div>
    );
  }

  return (
    <div className="page">
      <h2>Metadata explorer</h2>
      <div className="page-sub">
        {active
          ? `Application ${active.application} — context ${active.label} (${active.mode})`
          : "Loading context…"}
      </div>
      <div className="explorer-toolbar">
        <Search
          size="sm"
          labelText="Filter members"
          placeholder="Filter members by name or alias"
          value={filter}
          onChange={(e) => setFilter(e.target.value.toLowerCase())}
          style={{ maxWidth: 360 }}
        />
        <span className="tag-inline">{matches.length} members in {trees.length} dimensions</span>
      </div>
      <div className="explorer-layout">
        <div className="explorer-tree">
          {membersLoading && (
            <div style={{ padding: 12, fontSize: 13, color: "var(--cds-text-secondary, #8d8d8d)" }}>
              Loading members…
            </div>
          )}
          {!membersLoading && trees.length === 0 && (
            <div style={{ padding: 12, fontSize: 13, color: "var(--cds-text-secondary, #8d8d8d)" }}>
              The active context has no member records. Build a deep context to load member hierarchies.
            </div>
          )}
          <ul>
            {trees.map((t) => (
              <DimensionRow key={t.name} tree={t} filter={filter} selected={selected} onSelect={setSelected} />
            ))}
          </ul>
        </div>
        {selected && (
          <Tile className="explorer-detail">
            <div style={{ fontWeight: 600, fontSize: 14 }}>{selected.member}</div>
            <div className="detail-rows">
              <DetailRow label="Alias" value={selected.alias} />
              <DetailRow label="Dimension" value={selected.dimension} />
              <DetailRow label="Parent" value={selected.parent} />
              <DetailRow label="Cube" value={selected.cube} />
              <DetailRow label="Application" value={selected.application} />
              <DetailRow label="Source artifact" value={selected.sourceArtifact} />
              <DetailRow label="Context version" value={selected.contextVersion} />
            </div>
          </Tile>
        )}
      </div>
    </div>
  );
}
