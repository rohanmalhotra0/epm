import { useState, useEffect, useRef } from "react";
import { Button } from "@carbon/react";
import { ZoomIn, ZoomOut } from "@carbon/icons-react";
import { api } from "../api/client";
import { useArchitecture, useArtifacts, useBuildContext, useContexts, useDeployments } from "../api/hooks";
import { CubeArchitectureBlock } from "../blocks/CubeArchitectureBlock";
import { useUi } from "../store/ui";
import { toast } from "../store/toast";
import { diffSpecs, formatValue, type DiffRow } from "../utils/specDiff";
import type { ArtifactOut, CubeArchitecture } from "../schemas/types";
import "../styles/feature-pages.css";

function usePid() {
  return useUi((s) => s.currentProjectId) ?? undefined;
}

export function ContextsPage() {
  const pid = usePid();
  const { data: contexts = [] } = useContexts(pid);
  const build = useBuildContext(pid);
  return (
    <div className="page">
      <h2>Contexts</h2>
      <div className="page-sub">Learn the connected EPM application. Contexts are stored locally and reused automatically.</div>
      <div className="action-row" style={{ marginBottom: 16 }}>
        <Button size="sm" kind="primary" disabled={build.isPending} onClick={() => build.mutate("quick")}>
          {build.isPending ? "Building context…" : "Build context"}
        </Button>
      </div>
      <table className="data-table">
        <thead><tr><th>Version</th><th>Mode</th><th>Members</th><th>Forms</th><th>Rules</th><th>Active</th><th>Export</th></tr></thead>
        <tbody>
          {contexts.map((c) => (
            <tr key={c.id}>
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
            </tr>
          ))}
          {contexts.length === 0 && <tr><td colSpan={7} style={{ color: "#8d8d8d" }}>No context yet — build one above.</td></tr>}
        </tbody>
      </table>
      <ArchitectureViewer projectId={pid} />
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
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
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

  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDragging) return;
    setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
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
            cursor: isDragging ? "grabbing" : "grab",
            transition: isDragging ? "none" : "transform 0.1s ease-out"
          }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
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
                    {cubeName}
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
                    y={cubeSize / 2 + 10}
                    fill="#a8a8a8"
                    fontSize={32}
                    fontWeight={700}
                    textAnchor="middle"
                  >
                    {dimCount}
                  </text>

                  <text
                    x={cubeSize / 2}
                    y={cubeSize / 2 + 32}
                    fill="#8d8d8d"
                    fontSize={12}
                    textAnchor="middle"
                  >
                    dimensions
                  </text>

                  {/* Dimension names (small list at bottom) */}
                  {arch.dimensions.slice(0, 5).map((dim, i) => (
                    <text
                      key={i}
                      x={cubeSize / 2}
                      y={cubeSize - 60 + i * 12}
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
                      y={cubeSize - 8}
                      fill="#6f6f6f"
                      fontSize={9}
                      textAnchor="middle"
                    >
                      +{dimCount - 5} more
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
