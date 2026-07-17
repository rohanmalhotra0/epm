import { Button } from "@carbon/react";
import { useArtifacts, useBuildContext, useContexts, useDeployments, useDiagnostics } from "../api/hooks";
import { useUi } from "../store/ui";

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
        <Button size="sm" kind="primary" disabled={build.isPending} onClick={() => build.mutate("quick")}>Build quick context</Button>
        <Button size="sm" kind="tertiary" disabled={build.isPending} onClick={() => build.mutate("deep")}>Build deep context</Button>
      </div>
      <table className="data-table">
        <thead><tr><th>Version</th><th>Mode</th><th>Members</th><th>Forms</th><th>Rules</th><th>Active</th><th></th></tr></thead>
        <tbody>
          {contexts.map((c) => (
            <tr key={c.id}>
              <td className="mono">{c.label}</td>
              <td>{c.mode}</td>
              <td>{String(c.counts?.members ?? "—")}</td>
              <td>{String(c.counts?.forms ?? "—")}</td>
              <td>{String(c.counts?.rules ?? "—")}</td>
              <td>{c.active ? <span className="tag-inline">active</span> : ""}</td>
              <td><a href={`/api/contexts/${c.id}/export`} target="_blank" rel="noreferrer">Export .epwcontext</a></td>
            </tr>
          ))}
          {contexts.length === 0 && <tr><td colSpan={7} style={{ color: "#8d8d8d" }}>No context yet — build one above.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export function ArtifactsPage() {
  const pid = usePid();
  const { data: artifacts = [] } = useArtifacts(pid);
  return (
    <div className="page">
      <h2>Artifacts</h2>
      <div className="page-sub">Form specs, rule specs, XML, packages, and context bundles — all stored locally.</div>
      <table className="data-table">
        <thead><tr><th>Name</th><th>Kind</th><th>Version</th><th>Checksum</th><th></th></tr></thead>
        <tbody>
          {artifacts.map((a) => (
            <tr key={a.id}>
              <td>{a.name}</td>
              <td><span className="tag-inline">{a.kind}</span></td>
              <td>v{a.version}</td>
              <td className="mono" style={{ fontSize: 11 }}>{a.checksum?.slice(0, 16) ?? "—"}</td>
              <td><a href={`/api/artifacts/${a.id}/download`} target="_blank" rel="noreferrer">Download</a></td>
            </tr>
          ))}
          {artifacts.length === 0 && <tr><td colSpan={5} style={{ color: "#8d8d8d" }}>No artifacts yet.</td></tr>}
        </tbody>
      </table>
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
        <thead><tr><th>Artifact</th><th>Environment</th><th>Operation</th><th>Result</th><th>Verified</th><th>Mode</th><th>When</th></tr></thead>
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
            </tr>
          ))}
          {deployments.length === 0 && <tr><td colSpan={7} style={{ color: "#8d8d8d" }}>No deployments yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export function DiagnosticsPage() {
  const { data } = useDiagnostics();
  const dot = (s: string) => (s === "ok" ? "#42be65" : s === "warn" ? "#f1c21b" : s === "unavailable" ? "#6f6f6f" : "#ff8389");
  return (
    <div className="page">
      <h2>Diagnostics</h2>
      <div className="page-sub">Local subsystem health. The diagnostics bundle is sanitized — it never contains secrets.</div>
      <div className="action-row" style={{ marginBottom: 16 }}>
        <Button size="sm" kind="tertiary" onClick={() => window.open("/api/diagnostics/bundle", "_blank")}>Download sanitized bundle</Button>
      </div>
      {data && (
        <>
          <div className="card-grid" style={{ marginBottom: 20 }}>
            {data.subsystems.map((s) => (
              <div className="stat-tile" key={s.name}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ width: 10, height: 10, borderRadius: "50%", background: dot(s.status) }} />
                  <span style={{ fontWeight: 600 }}>{s.name}</span>
                </div>
                <div className="l" style={{ marginTop: 6 }}>{s.detail}</div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 12, color: "#8d8d8d" }}>
            Version {data.appVersion} · provider {data.activeProvider} · model {data.activeModel} · redaction {data.redactionHealthy ? "healthy" : "FAILED"}
          </div>
        </>
      )}
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
