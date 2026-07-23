import { useState, useEffect } from "react";
import {
  Button,
  FileUploaderButton,
  Select,
  SelectItem,
  SkeletonText,
} from "@carbon/react";
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
import "../styles/context-architecture.css";

function usePid() {
  return useUi((s) => s.currentProjectId) ?? undefined;
}

export function ContextsPage() {
  const pid = usePid();
  const {
    data: contexts = [],
    isLoading: contextsLoading,
    isError: contextsError,
    error: contextsErrorDetail,
    refetch: refetchContexts,
  } = useContexts(pid);
  const build = useBuildContext(pid);
  const importSnapshot = useImportContextSnapshot(pid);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const toggleExpanded = (id: string) => setExpanded((cur) => ({ ...cur, [id]: !cur[id] }));
  const activeVersion = contexts.find((c) => c.active);
  return (
    <div className="page">
      <h2 className="text-balance">Contexts</h2>
      <div className="page-sub text-pretty">Learn the connected EPM application. Contexts are stored locally and reused automatically.</div>
      <div className="action-row" style={{ marginBottom: 16 }}>
        <Button size="sm" kind="primary" disabled={build.isPending || !pid} onClick={() => build.mutate("quick")}>
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
      {contextsLoading && (
        <div className="context-version-skeleton" role="status" aria-live="polite" aria-busy="true">
          <SkeletonText paragraph lineCount={3} />
          <span className="cds--visually-hidden">Loading context versions…</span>
        </div>
      )}
      {contextsError && (
        <div className="context-inline-state" role="alert">
          <div>
            <strong>Context versions could not be loaded</strong>
            <span>{contextsErrorDetail instanceof Error ? contextsErrorDetail.message : "Try the request again."}</span>
          </div>
          <Button size="sm" kind="tertiary" onClick={() => refetchContexts()}>Retry</Button>
        </div>
      )}
      {!contextsLoading && !contextsError && (
        <div className="context-version-table-wrap" role="region" aria-label="Context versions" tabIndex={0}>
          <table className="data-table">
            <thead><tr><th style={{ width: 80 }}>Details</th><th>Version</th><th>Mode</th><th>Members</th><th>Forms</th><th>Rules</th><th>Active</th><th>Export</th></tr></thead>
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
                    <td className="tabular-nums">{String(c.counts?.members ?? "—")}</td>
                    <td className="tabular-nums">{String(c.counts?.forms ?? "—")}</td>
                    <td className="tabular-nums">{String(c.counts?.rules ?? "—")}</td>
                    <td>{c.active ? <span className="tag-inline">active</span> : ""}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <a href={`/api/contexts/${c.id}/export.docx`} aria-label={`Download ${c.label} as Word document`}>Word</a>
                      {" · "}
                      <a href={`/api/contexts/${c.id}/export.pdf`} aria-label={`Download ${c.label} as PDF`}>PDF</a>
                      {" · "}
                      <a href={`/api/contexts/${c.id}/export.md`} aria-label={`Download ${c.label} as Markdown`}>Markdown</a>
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
              {contexts.length === 0 && (
                <tr>
                  <td colSpan={8} className="context-empty-cell">
                    No context yet. Build one to explore cube architecture and dimensions.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <ArchitectureViewer key={pid} projectId={pid} />
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

/** Fast, responsive overview of every cube in the active context. */
function CubeOverview({
  projectId,
  cubes,
  onSelectCube,
}: {
  projectId: string;
  cubes: string[];
  onSelectCube: (cube: string) => void;
}) {
  const [architectures, setArchitectures] = useState<Record<string, CubeArchitecture>>({});
  const [failedCubes, setFailedCubes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const loadAllCubes = async () => {
      setLoading(true);
      setFailedCubes([]);
      const settled = await Promise.allSettled(
        cubes.map(async (cube) => {
          const response = await api<{ cubes: string[]; cube: string; architecture: CubeArchitecture }>(
            `/api/projects/${projectId}/architecture?cube=${encodeURIComponent(cube)}`
          );
          return [cube, response.architecture] as const;
        }),
      );
      if (cancelled) return;

      const results: Record<string, CubeArchitecture> = {};
      const failures: string[] = [];
      settled.forEach((result, index) => {
        if (result.status === "fulfilled") results[result.value[0]] = result.value[1];
        else failures.push(cubes[index]);
      });
      setArchitectures(results);
      setFailedCubes(failures);
      setLoading(false);
    };

    loadAllCubes();
    return () => {
      cancelled = true;
    };
  }, [projectId, cubes, retryKey]);

  if (loading) {
    return (
      <div className="context-cube-grid" role="status" aria-live="polite" aria-busy="true">
        {[0, 1, 2, 3].map((item) => (
          <div className="context-cube-skeleton" key={item}>
            <SkeletonText heading />
            <SkeletonText paragraph lineCount={3} />
          </div>
        ))}
        <span className="cds--visually-hidden">Loading cube overview…</span>
      </div>
    );
  }

  const cubeEntries = cubes.flatMap((cube) => architectures[cube] ? [[cube, architectures[cube]] as const] : []);
  const totalDimensions = cubeEntries.reduce((sum, [, architecture]) => sum + architecture.dimensions.length, 0);
  const totalMembers = cubeEntries.reduce(
    (sum, [, architecture]) => sum + architecture.dimensions.reduce(
      (cubeSum, dimension) => cubeSum + (dimension.memberCount ?? 0),
      0,
    ),
    0,
  );

  return (
    <section className="context-overview" aria-label="Application cube overview">
      <div className="context-overview-summary">
        <span><strong className="tabular-nums">{cubeEntries.length}</strong> cubes loaded</span>
        <span><strong className="tabular-nums">{totalDimensions}</strong> dimensions</span>
        <span><strong className="tabular-nums">{totalMembers.toLocaleString()}</strong> known members</span>
      </div>
      {failedCubes.length > 0 && (
        <div className="context-inline-state context-inline-state-warning" role="status">
          <div>
            <strong>{failedCubes.length === cubes.length ? "Cube overview could not be loaded" : "Some cubes could not be loaded"}</strong>
            <span>{failedCubes.join(", ")}</span>
          </div>
          <Button size="sm" kind="tertiary" onClick={() => setRetryKey((value) => value + 1)}>Retry</Button>
        </div>
      )}
      {cubeEntries.length > 0 ? (
        <div className="context-cube-grid">
          {cubeEntries.map(([cubeName, architecture], index) => {
            const preview = architecture.dimensions.slice(0, 4);
            const remaining = architecture.dimensions.length - preview.length;
            const memberCount = architecture.dimensions.reduce(
              (sum, dimension) => sum + (dimension.memberCount ?? 0),
              0,
            );
            return (
              <button
                type="button"
                className="context-cube-card"
                key={cubeName}
                style={{ animationDelay: `${Math.min(index * 28, 140)}ms` }}
                aria-label={`Explore ${cubeName}, ${architecture.dimensions.length} dimensions`}
                onClick={() => onSelectCube(cubeName)}
              >
                <span className="context-cube-card-kicker">{architecture.cubeType || "Planning cube"}</span>
                <strong>{cubeName}</strong>
                <span className="context-cube-card-metric">
                  <b className="tabular-nums">{architecture.dimensions.length}</b> dimensions
                  <span aria-hidden="true"> · </span>
                  <b className="tabular-nums">{memberCount.toLocaleString()}</b> members
                </span>
                <span className="context-cube-dimensions">
                  {preview.map((dimension) => dimension.name).join(" · ")}
                  {remaining > 0 ? ` · +${remaining}` : ""}
                </span>
                <span className="context-cube-card-action">Explore architecture <span aria-hidden="true">→</span></span>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="context-overview-empty">
          <strong>No cube architecture is available</strong>
          <p className="text-pretty">Retry the overview or rebuild the active context.</p>
        </div>
      )}
    </section>
  );
}

/** Cube Architecture & Dimensionality visualizer for the active context. */
function ArchitectureViewer({ projectId }: { projectId: string | undefined }) {
  const [cube, setCube] = useState<string | undefined>(undefined);
  const [view, setView] = useState<"overview" | "detail">("overview");
  const [knownCubes, setKnownCubes] = useState<string[]>([]);
  const { data, isLoading, isFetching, isError, error, refetch } = useArchitecture(projectId, cube);

  useEffect(() => {
    if (data?.cubes.length) setKnownCubes(data.cubes);
  }, [data?.cubes]);

  if (!projectId) return null;

  const selectedCube = cube ?? data?.cube ?? knownCubes[0] ?? "";
  const selectCube = (nextCube: string) => {
    setCube(nextCube);
    setView("detail");
  };

  return (
    <section className="context-architecture-section" aria-labelledby="context-architecture-title">
      <div className="context-architecture-heading">
        <div>
          <h3 id="context-architecture-title" className="text-balance">Cube architecture</h3>
          <p className="text-pretty">
            Explore every cube, then select a dimension to inspect its placement and member coverage.
          </p>
        </div>
        {isFetching && !isLoading && <span className="context-fetching" role="status">Updating…</span>}
      </div>

      {(data || knownCubes.length > 0) && (
        <div className="context-architecture-controls" aria-label="Architecture view controls">
          <Button
            type="button"
            size="sm"
            kind={view === "overview" ? "primary" : "ghost"}
            aria-pressed={view === "overview"}
            onClick={() => setView("overview")}
          >
            All cubes
          </Button>
          <Select
            id="context-cube-select"
            size="sm"
            labelText="Cube"
            value={selectedCube}
            onChange={(event) => selectCube(event.target.value)}
          >
            {(data?.cubes ?? knownCubes).map((cubeName) => (
              <SelectItem key={cubeName} value={cubeName} text={cubeName} />
            ))}
          </Select>
        </div>
      )}
      {isLoading && knownCubes.length === 0 && (
        <div className="context-architecture-loading" role="status" aria-live="polite" aria-busy="true">
          <SkeletonText heading />
          <SkeletonText paragraph lineCount={4} />
          <span className="cds--visually-hidden">Loading cube architecture…</span>
        </div>
      )}
      {isError && (
        <div className="context-inline-state" role="alert">
          <div>
            <strong>Architecture is not available yet</strong>
            <span>{error instanceof Error ? error.message : "Build or refresh the active context, then try again."}</span>
          </div>
          <Button size="sm" kind="tertiary" onClick={() => refetch()}>Retry</Button>
        </div>
      )}
      {data && (
        <>
          {view === "overview" ? (
            <CubeOverview projectId={projectId} cubes={data.cubes} onSelectCube={selectCube} />
          ) : (
            <CubeArchitectureBlock
              key={data.architecture.cube}
              data={data.architecture}
              onAction={() => {}}
              showHeader={false}
            />
          )}
        </>
      )}
    </section>
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
