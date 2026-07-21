import { useState, useEffect, useRef } from "react";
import { Button, FileUploaderButton } from "@carbon/react";
import { ZoomIn, ZoomOut } from "@carbon/icons-react";
import { api } from "../api/client";
import {
  useArchitecture,
  useArtifacts,
  useBuildContext,
  useContextDiff,
  useContexts,
  useDeployments,
  useImportContextSnapshot,
  type ContextDiffEntry,
  type ContextDiffKind,
} from "../api/hooks";
import { CubeArchitectureBlock } from "../blocks/CubeArchitectureBlock";
import { useUi } from "../store/ui";
import { toast } from "../store/toast";
import { diffSpecs, formatValue, type DiffRow } from "../utils/specDiff";
import type { ArtifactOut, ContextVersionOut, CubeArchitecture } from "../schemas/types";
import "../styles/feature-pages.css";

function usePid() {
  return useUi((s) => s.currentProjectId) ?? undefined;
}

export function ContextsPage() {
  const pid = usePid();
  const { data: contexts = [] } = useContexts(pid);
  const build = useBuildContext(pid);
  const importSnapshot = useImportContextSnapshot(pid);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const toggleExpanded = (id: string) => setExpanded((cur) => ({ ...cur, [id]: !cur[id] }));
  const activeVersion = contexts.find((c) => c.active);
  return (
    <div className="page">
      <h2>Contexts</h2>
      <div className="page-sub">Learn the connected EPM application. Contexts are stored locally and reused automatically.</div>
      <div className="action-row" style={{ marginBottom: 16 }}>
        <Button size="sm" kind="primary" disabled={build.isPending} onClick={() => build.mutate("quick")}>
          {build.isPending ? "Building context…" : "Build context"}
        </Button>
        <FileUploaderButton
          size="sm"
          buttonKind="tertiary"
          labelText={importSnapshot.isPending ? "Importing snapshot…" : "Upload snapshot"}
          accept={[".zip"]}
          disableLabelChanges
          disabled={importSnapshot.isPending || !pid}
          onChange={(e) => {
            const input = e.target as HTMLInputElement;
            const file = input.files?.[0];
            if (file) importSnapshot.mutate({ file });
            input.value = "";
          }}
        />
      </div>
      <table className="data-table">
        <thead><tr><th style={{ width: 80 }}></th><th>Version</th><th>Mode</th><th>Members</th><th>Forms</th><th>Rules</th><th>Active</th><th>Export</th></tr></thead>
        <tbody>
          {contexts.map((c) => {
            const isOpen = !!expanded[c.id];
            return [
              <tr key={c.id}>
                <td>
                  <Button
                    size="sm"
                    kind="ghost"
                    aria-expanded={isOpen}
                    aria-label={`${isOpen ? "Hide" : "Show"} details for ${c.label}`}
                    onClick={() => toggleExpanded(c.id)}
                  >
                    {isOpen ? "Hide" : "Details"}
                  </Button>
                </td>
                <td className="mono">{c.label}</td>
                <td>{c.mode}</td>
                <td>{String(c.counts?.members ?? "—")}</td>
                <td>{String(c.counts?.forms ?? "—")}</td>
                <td>{String(c.counts?.rules ?? "—")}</td>
                <td>{c.active ? <span className="tag-inline">active</span> : ""}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <a href={`/api/contexts/${c.id}/export.docx`} title="Download as Word document">Word</a>
                  {" · "}
                  <a href={`/api/contexts/${c.id}/export.pdf`} title="Download as PDF with diagrams">PDF</a>
                  {" · "}
                  <a href={`/api/contexts/${c.id}/export.md`} title="Download as Markdown with Mermaid diagrams">Markdown</a>
                </td>
              </tr>,
              isOpen ? (
                <tr key={`${c.id}-detail`}>
                  <td colSpan={8} style={{ padding: "10px 12px", background: "var(--cds-layer,#1f1f1f)" }}>
                    <ContextVersionDetail version={c} activeVersion={activeVersion} />
                  </td>
                </tr>
              ) : null,
            ];
          })}
          {contexts.length === 0 && <tr><td colSpan={8} style={{ color: "#8d8d8d" }}>No context yet — build one above.</td></tr>}
        </tbody>
      </table>
      <ArchitectureViewer projectId={pid} />
    </div>
  );
}

function sectionStatusColor(s: string) {
  return s === "complete" ? "#42be65" : s === "unavailable" ? "#ff8389" : s === "notRequested" ? "#6f6f6f" : "#f1c21b";
}

function toCount(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

/** Expanded panel for one context version row: manifest sections, snapshot provenance, count diff vs. active. */
function ContextVersionDetail({
  version,
  activeVersion,
}: {
  version: ContextVersionOut;
  activeVersion: ContextVersionOut | undefined;
}) {
  const manifest = (version.manifest ?? {}) as Record<string, any>;
  const sections: Array<{ name: string; status: string; count?: number; note?: string | null }> =
    Array.isArray(manifest.sections) ? manifest.sections : [];
  const snapshot = manifest.snapshot as Record<string, any> | undefined;
  const provenance = (snapshot?.provenance ?? {}) as Record<string, any>;
  const compare = !version.active && activeVersion && activeVersion.id !== version.id ? activeVersion : undefined;
  const diffKeys = compare
    ? Array.from(new Set([...Object.keys(compare.counts ?? {}), ...Object.keys(version.counts ?? {})])).sort()
    : [];
  const secondary = { color: "var(--cds-text-secondary,#8d8d8d)" } as const;
  return (
    <div style={{ fontSize: 12, display: "grid", gap: 14 }}>
      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Sections</div>
        {sections.length === 0 && <div style={secondary}>No section information in this version's manifest.</div>}
        {sections.map((s, i) => (
          <div key={i} style={{ fontSize: 12, display: "flex", gap: 8, padding: "2px 0" }}>
            <span style={{ width: 210 }}>{s.name}</span>
            <span style={{ color: sectionStatusColor(s.status) }}>{s.status}</span>
            <span style={secondary}>{s.count ? `(${s.count})` : ""} {s.note || ""}</span>
          </div>
        ))}
      </div>
      {snapshot && (
        <div>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Snapshot provenance</div>
          <div style={{ display: "flex", gap: 8, padding: "2px 0" }}>
            <span style={{ width: 210, ...secondary }}>Application</span>
            <span>{snapshot.application || "—"}</span>
          </div>
          <div style={{ display: "flex", gap: 8, padding: "2px 0" }}>
            <span style={{ width: 210, ...secondary }}>Exported by</span>
            <span>{provenance.exportedBy || "—"}</span>
          </div>
          <div style={{ display: "flex", gap: 8, padding: "2px 0" }}>
            <span style={{ width: 210, ...secondary }}>Exported at</span>
            <span>{provenance.exportedAt || "—"}</span>
          </div>
        </div>
      )}
      {compare && (
        <div>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Compare with active ({compare.label})</div>
          {diffKeys.length === 0 && <div style={secondary}>No counts recorded on either version.</div>}
          {diffKeys.map((k) => {
            const before = toCount((compare.counts ?? {})[k]);
            const after = toCount((version.counts ?? {})[k]);
            const delta = after - before;
            const deltaLabel = delta > 0 ? `+${delta}` : delta < 0 ? `−${Math.abs(delta)}` : "±0";
            const deltaColor = delta > 0 ? "#42be65" : delta < 0 ? "#ff8389" : "#6f6f6f";
            return (
              <div key={k} style={{ display: "flex", gap: 8, padding: "2px 0" }}>
                <span style={{ width: 210 }}>{k}</span>
                <span style={secondary}>{before} → {after}</span>
                <span style={{ color: deltaColor, fontWeight: 600 }}>{deltaLabel}</span>
              </div>
            );
          })}
        </div>
      )}
      {compare && <ContextDetailedDiff versionId={compare.id} thisId={version.id} againstLabel={compare.label} />}
    </div>
  );
}

function formatDiffValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

/** A single diff row (added/removed/changed) inside one kind's diff table. */
function ContextDiffRow({ entry, change }: { entry: ContextDiffEntry; change: "added" | "removed" | "changed" }) {
  const ident = [entry.name, entry.dimension || null].filter(Boolean).join(" · ") || "—";
  return (
    <tr className={`diff-row ${change}`}>
      <td><span className={`diff-badge ${change}`}>{change}</span></td>
      <td className="path">{ident}</td>
      <td className="val-left">
        {change === "added" ? "—" : change === "removed" ? (entry.cube || "removed") : formatDiffValue(entry.before)}
      </td>
      <td className="val-right">
        {change === "removed" ? "—" : change === "added" ? (entry.cube || "added") : formatDiffValue(entry.after)}
      </td>
    </tr>
  );
}

/** Record-level diff of one context version vs. the active one, per kind. */
function ContextDetailedDiff({
  versionId,
  thisId,
  againstLabel,
}: {
  versionId: string; // the active baseline (A); added/removed are relative to it
  thisId: string; // the version being viewed (B), so direction matches the count deltas above
  againstLabel: string;
}) {
  const { data, isLoading, isError } = useContextDiff(versionId, thisId);
  const secondary = { color: "var(--cds-text-secondary,#8d8d8d)" } as const;
  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Detailed diff (vs. {againstLabel})</div>
      {isLoading && <div style={secondary}>Loading detailed diff…</div>}
      {isError && <div style={secondary}>Detailed diff is unavailable for this pair of versions.</div>}
      {data && (() => {
        const kinds = Object.entries(data.kinds || {}).filter(
          ([, k]) => k.added.length || k.removed.length || k.changed.length,
        );
        if (kinds.length === 0) return <div style={secondary}>No record-level differences.</div>;
        return kinds.map(([kind, k]: [string, ContextDiffKind]) => {
          const more = [
            k.addedTruncated ? `+${k.addedTruncated} more added` : "",
            k.removedTruncated ? `+${k.removedTruncated} more removed` : "",
            k.changedTruncated ? `+${k.changedTruncated} more changed` : "",
          ].filter(Boolean);
          return (
            <div key={kind} className="diff-panel" style={{ marginTop: 10 }}>
              <div className="diff-head">
                <span>{kind}</span>
                <span className="grow" />
                <span style={{ fontWeight: 400, ...secondary }}>
                  {k.added.length} added · {k.removed.length} removed · {k.changed.length} changed
                </span>
              </div>
              <table className="diff-table">
                <thead>
                  <tr>
                    <th style={{ width: 90 }}>Change</th>
                    <th>Record</th>
                    <th>Before</th>
                    <th>After</th>
                  </tr>
                </thead>
                <tbody>
                  {k.removed.map((e, i) => <ContextDiffRow key={`r${i}`} entry={e} change="removed" />)}
                  {k.added.map((e, i) => <ContextDiffRow key={`a${i}`} entry={e} change="added" />)}
                  {k.changed.map((e, i) => <ContextDiffRow key={`c${i}`} entry={e} change="changed" />)}
                </tbody>
              </table>
              {more.length > 0 && (
                <div style={{ padding: "5px 12px", fontSize: 11, ...secondary }}>{more.join(" · ")}</div>
              )}
            </div>
          );
        });
      })()}
    </div>
  );
}

/** Combined overview showing all cubes in one visualization */
function CubeOverview({ projectId, cubes }: { projectId: string; cubes: string[] }) {
  const [architectures, setArchitectures] = useState<Record<string, CubeArchitecture>>({});
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0, panX: 0, panY: 0 });
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const loadAllCubes = async () => {
      setLoading(true);
      const results: Record<string, CubeArchitecture> = {};

      for (const cube of cubes) {
        try {
          const response = await api<{ cubes: string[]; cube: string; architecture: CubeArchitecture }>(
            `/api/projects/${projectId}/architecture?cube=${encodeURIComponent(cube)}`
          );
          results[cube] = response.architecture;
        } catch (err) {
          console.error(`Failed to load cube ${cube}:`, err);
        }
      }

      setArchitectures(results);
      setLoading(false);
    };

    loadAllCubes();
  }, [projectId, cubes]);

  // Keyboard controls
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Leave typing alone — otherwise "-", "+", "0" and the arrow keys are
      // swallowed by the diagram while the user edits an input or the chat.
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;

      const panStep = 20;
      const zoomStep = 0.2;

      switch (e.key) {
        case "ArrowUp":
          e.preventDefault();
          setPan(prev => ({ ...prev, y: prev.y + panStep }));
          break;
        case "ArrowDown":
          e.preventDefault();
          setPan(prev => ({ ...prev, y: prev.y - panStep }));
          break;
        case "ArrowLeft":
          e.preventDefault();
          setPan(prev => ({ ...prev, x: prev.x + panStep }));
          break;
        case "ArrowRight":
          e.preventDefault();
          setPan(prev => ({ ...prev, x: prev.x - panStep }));
          break;
        case "+":
        case "=":
          e.preventDefault();
          setZoom(prev => Math.min(3, prev + zoomStep));
          break;
        case "-":
        case "_":
          e.preventDefault();
          setZoom(prev => Math.max(0.5, prev - zoomStep));
          break;
        case "0":
          e.preventDefault();
          setZoom(1);
          setPan({ x: 0, y: 0 });
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Pan is applied in viewBox user units, but the mouse moves in screen
  // pixels — convert the drag delta or the content lags the cursor.
  const screenToUser = (totalWidth: number, totalHeight: number) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || rect.height === 0) return 1;
    return 1 / Math.min(rect.width / totalWidth, rect.height / totalHeight);
  };

  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y });
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDragging) return;
    const k = screenToUser(totalWidth, totalHeight);
    setPan({
      x: dragStart.panX + (e.clientX - dragStart.x) * k,
      y: dragStart.panY + (e.clientY - dragStart.y) * k
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  if (loading) {
    return <div style={{ color: "#8d8d8d", fontSize: 13, padding: 20 }}>Loading all cubes…</div>;
  }

  const cubesList = Object.entries(architectures);
  const cols = Math.ceil(Math.sqrt(cubesList.length));
  const rows = Math.ceil(cubesList.length / cols);
  const cubeSize = 200;
  const spacing = 80;
  const totalWidth = cols * (cubeSize + spacing) + spacing;
  const totalHeight = rows * (cubeSize + spacing) + spacing;

  return (
    <div style={{ marginBottom: 12 }}>
      {/* Controls */}
      <div style={{
        display: "flex",
        gap: 12,
        marginBottom: 12,
        padding: "8px 12px",
        background: "#262626",
        borderRadius: 4,
        alignItems: "center"
      }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            onClick={() => setZoom(Math.max(0.5, zoom - 0.2))}
            style={{
              padding: 6,
              background: "#1f1f1f",
              border: "1px solid #393939",
              borderRadius: 3,
              cursor: "pointer",
              display: "flex",
              alignItems: "center"
            }}
            title="Zoom out"
          >
            <ZoomOut size={16} color="#f4f4f4" />
          </button>
          <span style={{ fontSize: 12, color: "#a8a8a8", minWidth: 45, textAlign: "center" }}>
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={() => setZoom(Math.min(3, zoom + 0.2))}
            style={{
              padding: 6,
              background: "#1f1f1f",
              border: "1px solid #393939",
              borderRadius: 3,
              cursor: "pointer",
              display: "flex",
              alignItems: "center"
            }}
            title="Zoom in"
          >
            <ZoomIn size={16} color="#f4f4f4" />
          </button>
          <button
            onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}
            style={{
              padding: "6px 12px",
              background: "#1f1f1f",
              border: "1px solid #393939",
              borderRadius: 3,
              cursor: "pointer",
              fontSize: 12,
              color: "#f4f4f4"
            }}
          >
            Reset
          </button>
        </div>
        <div style={{ fontSize: 11, color: "#8d8d8d", marginLeft: "auto" }}>
          Arrow keys: pan • +/−: zoom • 0: reset
        </div>
      </div>

      {/* Overview visualization */}
      <div style={{ position: "relative", overflow: "hidden", background: "#0f0f0f", borderRadius: 4 }}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${totalWidth} ${totalHeight}`}
          width="100%"
          style={{
            maxHeight: 600,
            cursor: isDragging ? "grabbing" : "grab"
          }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          {/* CSS transform (not the SVG attribute) so the zoom transition
              actually animates; px units are viewBox user units here. */}
          <g style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            transition: isDragging ? "none" : "transform 0.1s ease-out"
          }}>
            {cubesList.map(([cubeName, arch], idx) => {
              const col = idx % cols;
              const row = Math.floor(idx / cols);
              const x = spacing + col * (cubeSize + spacing);
              const y = spacing + row * (cubeSize + spacing);
              const dimCount = arch.dimensions.length;

              return (
                <g key={cubeName} transform={`translate(${x}, ${y})`}>
                  {/* Cube representation */}
                  <rect
                    width={cubeSize}
                    height={cubeSize}
                    rx={4}
                    fill="#1f1f1f"
                    stroke="#4589ff"
                    strokeWidth={2}
                  />

                  {/* Cube name */}
                  <text
                    x={cubeSize / 2}
                    y={30}
                    fill="#f4f4f4"
                    fontSize={16}
                    fontWeight={600}
                    textAnchor="middle"
                  >
                    {cubeName.length > 18 ? cubeName.slice(0, 17) + "…" : cubeName}
                  </text>

                  {/* Application name */}
                  <text
                    x={cubeSize / 2}
                    y={50}
                    fill="#8d8d8d"
                    fontSize={11}
                    textAnchor="middle"
                  >
                    {arch.application}
                  </text>

                  {/* Dimension count */}
                  <text
                    x={cubeSize / 2}
                    y={98}
                    fill="#a8a8a8"
                    fontSize={32}
                    fontWeight={700}
                    textAnchor="middle"
                  >
                    {dimCount}
                  </text>

                  <text
                    x={cubeSize / 2}
                    y={118}
                    fill="#8d8d8d"
                    fontSize={12}
                    textAnchor="middle"
                  >
                    dimensions
                  </text>

                  {/* Dimension names: 4 rows + "+N more" fit the space below
                      the count without rows landing on top of each other. */}
                  {arch.dimensions.slice(0, dimCount > 5 ? 4 : 5).map((dim, i) => (
                    <text
                      key={i}
                      x={cubeSize / 2}
                      y={134 + i * 12}
                      fill="#6f6f6f"
                      fontSize={9}
                      textAnchor="middle"
                    >
                      {dim.name.length > 20 ? dim.name.slice(0, 19) + "…" : dim.name}
                    </text>
                  ))}

                  {dimCount > 5 && (
                    <text
                      x={cubeSize / 2}
                      y={cubeSize - 10}
                      fill="#6f6f6f"
                      fontSize={9}
                      textAnchor="middle"
                    >
                      +{dimCount - 4} more
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      <div style={{ marginTop: 12, fontSize: 12, color: "#8d8d8d" }}>
        Showing {cubesList.length} cube{cubesList.length !== 1 ? "s" : ""} from the active context
      </div>
    </div>
  );
}

/** Cube Architecture & Dimensionality visualizer for the active context. */
function ArchitectureViewer({ projectId }: { projectId: string | undefined }) {
  const [cube, setCube] = useState<string | undefined>(undefined);
  const [showOverview, setShowOverview] = useState(false);
  const { data, isLoading, isError } = useArchitecture(projectId, cube);

  if (!projectId) return null;
  return (
    <div style={{ marginTop: 32 }}>
      <h3 style={{ fontSize: 16, marginBottom: 4 }}>Cube architecture</h3>
      <div className="page-sub">
        How dimensions form each cube in the active context. Select a cube to visualize it.
      </div>
      {isLoading && <div style={{ color: "#8d8d8d", fontSize: 13 }}>Loading architecture…</div>}
      {isError && (
        <div style={{ color: "#8d8d8d", fontSize: 13 }}>
          No active context to visualize yet — build one above, then it appears here.
        </div>
      )}
      {data && (
        <>
          <div className="action-row" style={{ margin: "12px 0" }}>
            <Button
              size="sm"
              kind={showOverview ? "primary" : "ghost"}
              onClick={() => setShowOverview(true)}
            >
              Overview
            </Button>
            {data.cubes.map((c) => (
              <Button
                key={c}
                size="sm"
                kind={!showOverview && c === data.cube ? "primary" : "ghost"}
                onClick={() => { setCube(c); setShowOverview(false); }}
              >
                {c}
              </Button>
            ))}
          </div>
          {showOverview ? (
            <CubeOverview projectId={projectId} cubes={data.cubes} />
          ) : (
            <CubeArchitectureBlock data={data.architecture} onAction={() => {}} />
          )}
        </>
      )}
    </div>
  );
}

interface DiffState {
  left: ArtifactOut;
  right: ArtifactOut;
  rows: DiffRow[];
}

export function ArtifactsPage() {
  const pid = usePid();
  const { data: artifacts = [] } = useArtifacts(pid);
  const [selected, setSelected] = useState<string[]>([]);
  const [diff, setDiff] = useState<DiffState | null>(null);
  const [comparing, setComparing] = useState(false);

  const chosen = selected
    .map((id) => artifacts.find((a) => a.id === id))
    .filter((a): a is ArtifactOut => !!a);
  const sameKind = chosen.length === 2 && chosen[0].kind === chosen[1].kind;

  const toggle = (id: string) => {
    setSelected((cur) =>
      cur.includes(id) ? cur.filter((x) => x !== id) : cur.length >= 2 ? [cur[1], id] : [...cur, id],
    );
  };

  const compare = async () => {
    if (!sameKind) return;
    setComparing(true);
    try {
      const [left, right] = await Promise.all(
        chosen.map((a) => api<ArtifactOut>(`/api/artifacts/${a.id}`)),
      );
      if (!left.payload || !right.payload) {
        toast.warning("Nothing to compare", "Both artifacts need a structured spec (JSON payload).");
        return;
      }
      setDiff({ left, right, rows: diffSpecs(left.payload, right.payload) });
    } catch (e) {
      toast.error("Compare failed", (e as Error).message);
    } finally {
      setComparing(false);
    }
  };

  return (
    <div className="page">
      <h2>Artifacts</h2>
      <div className="page-sub">Form specs, rule specs, XML, packages, and context bundles — all stored locally.</div>
      <div className="action-row" style={{ marginBottom: 12 }}>
        <Button size="sm" kind="tertiary" disabled={!sameKind || comparing} onClick={compare}>
          Compare selected
        </Button>
        <span style={{ fontSize: 12, color: "var(--cds-text-secondary, #8d8d8d)", alignSelf: "center" }}>
          {chosen.length === 2 && !sameKind
            ? "Select two artifacts of the same kind to compare."
            : "Select two artifacts of the same kind, then compare their specs field by field."}
        </span>
      </div>
      <table className="data-table">
        <thead><tr><th></th><th>Name</th><th>Kind</th><th>Version</th><th>Checksum</th><th></th></tr></thead>
        <tbody>
          {artifacts.map((a) => (
            <tr key={a.id}>
              <td style={{ width: 28 }}>
                <input
                  type="checkbox"
                  aria-label={`Select ${a.name} for comparison`}
                  checked={selected.includes(a.id)}
                  onChange={() => toggle(a.id)}
                />
              </td>
              <td>{a.name}</td>
              <td><span className="tag-inline">{a.kind}</span></td>
              <td>v{a.version}</td>
              <td className="mono" style={{ fontSize: 11 }}>{a.checksum?.slice(0, 16) ?? "—"}</td>
              <td><a href={`/api/artifacts/${a.id}/download`} target="_blank" rel="noreferrer">Download</a></td>
            </tr>
          ))}
          {artifacts.length === 0 && <tr><td colSpan={6} style={{ color: "#8d8d8d" }}>No artifacts yet.</td></tr>}
        </tbody>
      </table>
      {diff && <ArtifactDiffPanel diff={diff} onClose={() => setDiff(null)} />}
    </div>
  );
}

function ArtifactDiffPanel({ diff, onClose }: { diff: DiffState; onClose: () => void }) {
  const { left, right, rows } = diff;
  return (
    <div className="diff-panel" role="region" aria-label="Artifact comparison">
      <div className="diff-head">
        <span>
          {left.name} v{left.version} → {right.name} v{right.version}
        </span>
        <span className="tag-inline">{left.kind}</span>
        <span className="grow" />
        <span style={{ fontWeight: 400, color: "var(--cds-text-secondary, #8d8d8d)" }}>
          {rows.length === 0 ? "Specs are identical" : `${rows.length} difference${rows.length === 1 ? "" : "s"}`}
        </span>
        <Button size="sm" kind="ghost" onClick={onClose}>Close</Button>
      </div>
      {rows.length > 0 && (
        <table className="diff-table">
          <thead>
            <tr>
              <th style={{ width: 90 }}>Change</th>
              <th>Field</th>
              <th>{left.name} v{left.version}</th>
              <th>{right.name} v{right.version}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.path} className={`diff-row ${r.kind}`}>
                <td><span className={`diff-badge ${r.kind}`}>{r.kind}</span></td>
                <td className="path">{r.path}</td>
                <td className="val-left">{r.kind === "added" ? "—" : formatValue(r.left)}</td>
                <td className="val-right">{r.kind === "removed" ? "—" : formatValue(r.right)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function DeploymentsPage() {
  const pid = usePid();
  const { data: deployments = [] } = useDeployments(pid);
  return (
    <div className="page">
      <h2>Deployments</h2>
      <div className="page-sub">Every approved modifying operation is recorded here with its verification result.</div>
      <table className="data-table">
        <thead><tr><th>Artifact</th><th>Environment</th><th>Operation</th><th>Result</th><th>Verified</th><th>Mode</th><th>When</th><th>Script</th></tr></thead>
        <tbody>
          {deployments.map((d) => (
            <tr key={d.id}>
              <td>{d.artifactName}</td>
              <td>{d.environmentName} <span className={`env-badge ${d.classification}`}>{d.classification}</span></td>
              <td>{d.operation}</td>
              <td style={{ color: d.success ? "#42be65" : "#ff8389" }}>{d.success ? "Success" : "Failed"}</td>
              <td>{d.verified ? "✓" : "—"}</td>
              <td>{d.demoMode ? "Demo" : "Live"}</td>
              <td style={{ fontSize: 11, color: "#8d8d8d" }}>{new Date(d.createdAt).toLocaleString()}</td>
              <td style={{ whiteSpace: "nowrap" }}>
                <a href={`/api/deployments/${d.id}/script?format=sh`} download={`deployment_${d.id}.sh`}
                   title="Download an EPM Automate script for this deployment (bash)">.sh</a>
                {" · "}
                <a href={`/api/deployments/${d.id}/script?format=ps1`} download={`deployment_${d.id}.ps1`}
                   title="Download an EPM Automate script for this deployment (PowerShell)">.ps1</a>
              </td>
            </tr>
          ))}
          {deployments.length === 0 && <tr><td colSpan={8} style={{ color: "#8d8d8d" }}>No deployments yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export function AboutPage() {
  return (
    <div className="page">
      <h2>About EPM Wizard</h2>
      <div className="page-sub">A local-first AI workspace for Oracle Enterprise Performance Management implementation.</div>
      <div style={{ maxWidth: 680, fontSize: 14, lineHeight: 1.6 }}>
        <p>
          EPM Wizard runs entirely on your computer. There is no hosted server, database, or authentication service.
          Your projects, conversations, context, generated artifacts, and deployment history are stored locally in SQLite.
        </p>
        <p>
          The assistant interprets your intent, but <b>deterministic application code</b> owns every deployable artifact:
          resolving members, validating specifications, rendering XML, building reproducible packages, and verifying results.
          The language model never executes commands directly.
        </p>
        <p style={{ marginTop: 24, padding: 16, border: "1px solid var(--cds-border-subtle,#393939)", background: "var(--cds-layer,#1f1f1f)", fontSize: 12.5, color: "#a8a8a8" }}>
          EPM Wizard is an independent implementation tool. IBM, Oracle, and their respective product names are trademarks
          of their respective owners. EPM Wizard is not made, endorsed, or sponsored by IBM or Oracle.
        </p>
      </div>
    </div>
  );
}
