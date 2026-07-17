import { useState } from "react";
import { Button } from "@carbon/react";
import {
  Rule,
  Search,
  DataTable as DataTableIcon,
  Warning,
  DocumentDownload,
  Connect,
  Tools,
  TreeView,
  Analytics,
  ArrowsHorizontal,
} from "@carbon/icons-react";
import { Markdown } from "./Markdown";
import type {
  CellIntersection,
  CubeComparison,
  DimensionCoverageReport,
  DimensionHierarchy,
  ValidationReport,
} from "../schemas/types";

type Act = (v: string) => void;
const kindMap: Record<string, "primary" | "secondary" | "danger" | "ghost" | "tertiary"> = {
  primary: "primary",
  secondary: "tertiary",
  danger: "danger",
  ghost: "ghost",
};

export function CodeBlock({ data }: { data: any }) {
  return (
    <pre className="fallback-json mono">
      <code>{data.code}</code>
    </pre>
  );
}

export function ConfirmationBlock({ data, onAction }: { data: any; onAction: Act }) {
  return (
    <div className="block-card">
      <div className="block-body">
        <div style={{ fontSize: 13.5, marginBottom: data.detail ? 4 : 10 }}>{data.prompt}</div>
        {data.detail && <div className="mono" style={{ fontSize: 11.5, color: "var(--cds-text-secondary)", marginBottom: 10 }}>{data.detail}</div>}
        <div className="action-row">
          {(data.actions || []).map((a: any) => (
            <Button key={a.key} size="sm" kind={kindMap[a.style] || "tertiary"} onClick={() => onAction(a.value)} disabled={a.disabled}>
              {a.label}
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ValidationReportBlock({ data }: { data: ValidationReport }) {
  const errors = data.issues.filter((i) => i.severity === "error");
  const warnings = data.issues.filter((i) => i.severity === "warning");
  const infos = data.issues.filter((i) => i.severity === "info");
  return (
    <div className="block-card">
      <div className="block-head">
        {data.valid ? <span style={{ color: "#42be65" }}>✓</span> : <Warning size={16} />}
        <span>Validation — {data.valid ? "passed" : "failed"}</span>
        <span className="grow" />
        <span className="tag-inline">{errors.length} err · {warnings.length} warn</span>
      </div>
      {data.issues.length > 0 && (
        <div className="block-body">
          {[...errors, ...warnings, ...infos].map((i, idx) => (
            <div className="issue" key={idx}>
              <span className={`sev ${i.severity}`}>{i.severity}</span>
              <div>
                <div>{i.message}</div>
                {i.suggestedFix && <div style={{ color: "var(--cds-text-secondary)", fontSize: 11.5 }}>{i.suggestedFix}</div>}
                {i.candidates?.length > 0 && (
                  <div className="cands">
                    {i.candidates.map((c) => (
                      <span className="tag-inline" key={c}>{c}</span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function MemberSearchBlock({ data }: { data: any }) {
  return (
    <div className="block-card">
      <div className="block-head">
        <Search size={16} /> <span>Members matching “{data.query}”</span>
        <span className="grow" />
        <span className="tag-inline">{data.matches?.length || 0}</span>
      </div>
      <div className="block-body grid-preview">
        <table className="data-table">
          <thead>
            <tr><th>Member</th><th>Alias</th><th>Dimension</th><th>Parent</th><th>Match</th></tr>
          </thead>
          <tbody>
            {(data.matches || []).map((m: any, i: number) => (
              <tr key={i}>
                <td className="mono">{m.member}</td>
                <td>{m.alias || "—"}</td>
                <td>{m.dimension}</td>
                <td>{m.parent || "—"}</td>
                <td><span className="tag-inline">{m.retrievalMethod || m.confidence}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ContextSummaryBlock({ data }: { data: any }) {
  const counts = data.counts || {};
  return (
    <div className="block-card">
      <div className="block-head">
        <DataTableIcon size={16} /> <span>Context — {data.application} ({data.mode})</span>
        <span className="grow" />
        {data.active && <span className="tag-inline">active</span>}
      </div>
      <div className="block-body">
        <div className="card-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(110px,1fr))", gap: 8 }}>
          {Object.entries(counts).map(([k, v]) => (
            <div className="stat-tile" key={k} style={{ padding: 10 }}>
              <div className="n" style={{ fontSize: 20 }}>{v as number}</div>
              <div className="l">{k}</div>
            </div>
          ))}
        </div>
        {data.sections && (
          <div style={{ marginTop: 12 }}>
            {data.sections.map((s: any, i: number) => (
              <div key={i} style={{ fontSize: 12, display: "flex", gap: 8, padding: "2px 0" }}>
                <span style={{ width: 210 }}>{s.name}</span>
                <span style={{ color: statusColor(s.status) }}>{s.status}</span>
                <span style={{ color: "var(--cds-text-secondary)" }}>{s.count ? `(${s.count})` : ""} {s.note || ""}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
function statusColor(s: string) {
  return s === "complete" ? "#42be65" : s === "unavailable" ? "#ff8389" : s === "notRequested" ? "#6f6f6f" : "#f1c21b";
}

export function RuntimePromptFormBlock({ data, onAction }: { data: any; onAction: Act }) {
  const [vals, setVals] = useState<Record<string, string>>(
    Object.fromEntries((data.fields || []).map((f: any) => [f.name, f.default || ""])),
  );
  const submit = () => {
    const kv = (data.fields || []).map((f: any) => `${f.name}=${vals[f.name] ?? ""}`).join("; ");
    onAction(`/run-rule ${data.ruleName} :: ${kv}`);
  };
  return (
    <div className="block-card">
      <div className="block-head">
        <Rule size={16} /> <span>Run business rule — {data.ruleName}</span>
        <span className="grow" />
        <span className="tag-inline">{data.cube}</span>
      </div>
      <div className="block-body">
        {(data.fields || []).map((f: any) => (
          <div key={f.name} style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 12, color: "var(--cds-text-secondary)", display: "block", marginBottom: 2 }}>
              {f.promptText || f.name} {f.dimension ? `(${f.dimension})` : ""} {f.required ? "*" : ""}
            </label>
            <input
              value={vals[f.name] ?? ""}
              onChange={(e) => setVals((v) => ({ ...v, [f.name]: e.target.value }))}
              style={{ width: "100%", padding: "6px 10px", background: "var(--cds-field,#262626)", color: "inherit", border: "1px solid var(--cds-border-strong,#6f6f6f)", fontFamily: "inherit" }}
            />
          </div>
        ))}
        <div className="action-row">
          <Button size="sm" kind="primary" onClick={submit}>Run rule</Button>
          <Button size="sm" kind="ghost" onClick={() => onAction("cancel")}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

export function ToolInvocationBlock({ data }: { data: any }) {
  const color = data.status === "completed" ? "#42be65" : data.status === "failed" ? "#ff8389" : "#78a9ff";
  return (
    <div className="block-card">
      <div className="block-head">
        {data.status === "running" ? <div className="spinner" /> : <Tools size={16} />}
        <span>{data.summary || data.tool}</span>
        <span className="grow" />
        <span style={{ color, fontSize: 11 }}>{data.status}</span>
      </div>
      {data.detail && <div className="block-body" style={{ fontSize: 12, color: "var(--cds-text-secondary)" }}>{data.detail}</div>}
    </div>
  );
}

export function ErrorDiagnosticsBlock({ data, onAction }: { data: any; onAction: Act }) {
  return (
    <div className="block-card" style={{ borderColor: "#da1e28" }}>
      <div className="block-head" style={{ color: "#ff8389" }}>
        <Warning size={16} /> <span>{data.category} error</span>
      </div>
      <div className="block-body">
        <div style={{ fontSize: 13 }}>{data.message}</div>
        {data.likelyCause && <div style={{ fontSize: 12, marginTop: 4 }}><b>Likely cause:</b> {data.likelyCause}</div>}
        {data.suggestedAction && <div style={{ fontSize: 12, marginTop: 4 }}><b>Suggested:</b> {data.suggestedAction}</div>}
        {data.technicalDetail && (
          <details style={{ marginTop: 6 }}>
            <summary style={{ cursor: "pointer", fontSize: 12 }}>Technical details</summary>
            <pre className="fallback-json mono">{data.technicalDetail}</pre>
          </details>
        )}
        {data.actions?.length > 0 && (
          <div className="action-row">
            {data.actions.map((a: any) => (
              <Button key={a.key} size="sm" kind="tertiary" onClick={() => onAction(a.value)}>{a.label}</Button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function DownloadableFileBlock({ data }: { data: any }) {
  return (
    <div className="block-card">
      <div className="block-body" style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <DocumentDownload size={20} />
        <div style={{ flex: 1 }}>
          <div className="mono" style={{ fontSize: 13 }}>{data.filename}</div>
          <div style={{ fontSize: 11, color: "var(--cds-text-secondary)" }}>
            {data.sizeBytes ? `${data.sizeBytes.toLocaleString()} bytes` : ""}
            {data.checksum ? ` · ${data.checksum.slice(0, 12)}` : ""}
          </div>
        </div>
        <Button size="sm" kind="tertiary" href={`/api/artifacts/${data.artifactId}/download`} target="_blank">Download</Button>
      </div>
    </div>
  );
}

export function ConnectionStatusBlock({ data }: { data: any }) {
  return (
    <div className="block-card">
      <div className="block-head">
        <Connect size={16} /> <span className="conn-dot on" /> <span>Connected — {data.environmentName}</span>
        {data.classification && <span className={`env-badge ${data.classification}`} style={{ marginLeft: 8 }}>{data.classification}</span>}
      </div>
    </div>
  );
}

export function DiffBlock({ data }: { data: any }) {
  return (
    <div className="block-card">
      <div className="block-head"><span>Δ {data.title}</span></div>
      <div className="block-body" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <div>
          <div style={{ fontSize: 11, color: "#ff8389", marginBottom: 4 }}>Before</div>
          <pre className="fallback-json mono">{data.before}</pre>
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#42be65", marginBottom: 4 }}>After</div>
          <pre className="fallback-json mono">{data.after}</pre>
        </div>
      </div>
    </div>
  );
}

export function CellIntersectionBlock({ data }: { data: CellIntersection }) {
  return (
    <div className="block-card">
      <div className="block-head"><Analytics size={16} /> <span>One data cell — {data.cube}</span></div>
      <div className="block-body">
        <div className="grid-preview">
          <table className="data-table">
            <thead><tr><th>Dimension</th><th>Member</th><th>Source</th></tr></thead>
            <tbody>
              {data.members.map((m, i) => (
                <tr key={i}><td>{m.dimension}</td><td className="mono">{m.member}</td><td><span className="tag-inline">{m.source}</span></td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ fontSize: 11, color: "var(--cds-text-secondary)", marginTop: 8 }}>{data.note}</div>
      </div>
    </div>
  );
}

export function CubeComparisonBlock({ data }: { data: CubeComparison }) {
  return (
    <div className="block-card">
      <div className="block-head"><ArrowsHorizontal size={16} /> <span>{data.cubeA} vs {data.cubeB}</span></div>
      <div className="block-body grid-preview">
        <table className="data-table">
          <thead><tr><th>Dimension</th><th>{data.cubeA}</th><th>{data.cubeB}</th></tr></thead>
          <tbody>
            {data.rows.map((r, i) => (
              <tr key={i}>
                <td>{r.dimension}</td>
                <td style={{ color: r.inA ? "#42be65" : "#6f6f6f" }}>{r.inA ? "Yes" : "—"}</td>
                <td style={{ color: r.inB ? "#42be65" : "#6f6f6f" }}>{r.inB ? "Yes" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ fontSize: 12, marginTop: 8 }}>
          <div>Shared: <b>{data.shared}</b></div>
          <div>Only in {data.cubeA}: {data.onlyA.join(", ") || "—"}</div>
          <div>Only in {data.cubeB}: {data.onlyB.join(", ") || "—"}</div>
        </div>
      </div>
    </div>
  );
}

export function DimensionCoverageBlock({ data }: { data: DimensionCoverageReport }) {
  return (
    <div className="block-card">
      <div className="block-head">
        {data.valid ? <span style={{ color: "#42be65" }}>✓</span> : <Warning size={16} />}
        <span>Dimension coverage — {data.cube}</span>
      </div>
      <div className="block-body">
        <div style={{ fontSize: 12.5, marginBottom: 6 }}>
          {data.coveredDimensions.length} covered · {data.missingDimensions.length} missing · {data.duplicateDimensions.length} duplicate
        </div>
        {data.suggestions?.length > 0 && (
          <table className="data-table">
            <thead><tr><th>Missing dimension</th><th>Suggested handling</th></tr></thead>
            <tbody>
              {data.suggestions.map((s, i) => (
                <tr key={i}><td>{s.dimension}</td><td>{s.suggestedHandling}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export function DimensionHierarchyBlock({ data, onAction }: { data: DimensionHierarchy; onAction: Act }) {
  return (
    <div className="block-card">
      <div className="block-head"><TreeView size={16} /> <span>{data.dimension} — {data.root}</span></div>
      <div className="block-body">
        {data.nodes.map((n, i) => (
          <div key={i} style={{ fontSize: 12.5, paddingLeft: (n.depth ?? 0) * 18, display: "flex", gap: 6 }}>
            <span className="mono">{n.hasChildren ? "▸" : "·"}</span>
            <span>{n.name}</span>
            {n.alias && <span style={{ color: "var(--cds-text-secondary)" }}>({n.alias})</span>}
          </div>
        ))}
        {data.truncated && <div style={{ fontSize: 11, color: "var(--cds-text-secondary)", marginTop: 6 }}>Showing first {data.cap} members.</div>}
        <div className="action-row">
          {["children", "descendants", "level-0 descendants"].map((fn) => (
            <Button key={fn} size="sm" kind="ghost" onClick={() => onAction(`use ${fn} of ${data.root} in rows`)}>Use {fn}</Button>
          ))}
        </div>
      </div>
    </div>
  );
}

export function FallbackBlock({ type, data }: { type: string; data: any }) {
  if (data?.spec || data?.preview) {
    return (
      <div className="block-card">
        <div className="block-head"><span>{type}</span></div>
        <div className="block-body">
          <Markdown text={"```json\n" + JSON.stringify(data, null, 2).slice(0, 2000) + "\n```"} />
        </div>
      </div>
    );
  }
  return (
    <details className="block-card">
      <summary className="block-head" style={{ cursor: "pointer" }}>{type}</summary>
      <pre className="fallback-json mono">{JSON.stringify(data, null, 2)}</pre>
    </details>
  );
}
