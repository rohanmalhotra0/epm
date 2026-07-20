// Renders the assistant's `snapshotSummary` block: what the backend detected in
// an uploaded LCM application snapshot zip. The shape is still evolving
// server-side, so every field is accessed defensively — missing/extra fields
// must never crash.

import { Archive, Warning } from "@carbon/icons-react";

const COUNT_LABELS: Record<string, string> = {
  members: "Members",
  rules: "Rules",
  templates: "Templates",
  variables: "Variables",
  userVariables: "User variables",
  formsReferenced: "Forms referenced",
  dashboardsReferenced: "Dashboards referenced",
  integrations: "Integrations",
  pipelines: "Pipelines",
  securityGroups: "Security groups",
  users: "Users",
};

const TAG_LIMIT = 12;

/** Compact tag list; truncates past TAG_LIMIT with a "+N more" tag. */
function TagList({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  const shown = items.slice(0, TAG_LIMIT);
  const extra = items.length - shown.length;
  return (
    <div style={{ marginTop: 8 }}>
      <div className="sheet-section-label">{label}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
        {shown.map((t, i) => (
          <span className="tag-inline" key={`${t}-${i}`}>{t}</span>
        ))}
        {extra > 0 && <span className="tag-inline">+{extra} more</span>}
      </div>
    </div>
  );
}

export function SnapshotSummaryBlock({ data }: { data: any }) {
  const d = data || {};
  const cubes: string[] = Array.isArray(d.cubes) ? d.cubes.map(String) : [];
  const dimensions: string[] = Array.isArray(d.dimensions) ? d.dimensions.map(String) : [];
  const issues: any[] = Array.isArray(d.issues) ? d.issues : [];
  const prov = d.provenance || {};
  const counts = Object.entries(d.counts || {}).filter(([, v]) => typeof v === "number");
  const provParts = [
    prov.exportedBy && `exported by ${prov.exportedBy}`,
    prov.exportedAt && `on ${prov.exportedAt}`,
    (prov.serviceInstance || prov.domain) && `from ${prov.serviceInstance || prov.domain}`,
  ].filter(Boolean);
  return (
    <div className="block-card">
      <div className="block-head">
        <Archive size={16} /> <span className="mono">{d.filename || "Snapshot"}</span>
        <span className="grow" />
        <span className="tag-inline">Application snapshot</span>
      </div>
      <div className="block-body">
        {(d.application || provParts.length > 0) && (
          <div style={{ fontSize: 12.5, marginBottom: 8 }}>
            {d.application && <b>{String(d.application)}</b>}
            {d.application && provParts.length > 0 && " — "}
            {provParts.length > 0 && (
              <span style={{ color: "var(--cds-text-secondary)" }}>{provParts.join(" ")}</span>
            )}
          </div>
        )}
        <TagList label="Cubes" items={cubes} />
        <TagList label="Dimensions" items={dimensions} />
        {counts.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div className="sheet-section-label">Contents</div>
            <div className="card-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(110px,1fr))", gap: 8 }}>
              {counts.map(([k, v]) => (
                <div className="stat-tile" key={k} style={{ padding: 10 }}>
                  <div className="n" style={{ fontSize: 20 }}>{Number(v).toLocaleString()}</div>
                  <div className="l">{COUNT_LABELS[k] || k}</div>
                </div>
              ))}
            </div>
          </div>
        )}
        {issues.length > 0 && (
          <div style={{ marginTop: 8 }}>
            {issues.map((iss, i) => (
              <div className="issue" key={i}>
                <span className="sev warning"><Warning size={12} /> warning</span>
                <div>{typeof iss === "string" ? iss : JSON.stringify(iss)}</div>
              </div>
            ))}
          </div>
        )}
        {!d.application && provParts.length === 0 && cubes.length === 0 && dimensions.length === 0 &&
          counts.length === 0 && issues.length === 0 && (
            <div style={{ fontSize: 12, color: "var(--cds-text-secondary)" }}>No snapshot details available.</div>
          )}
      </div>
    </div>
  );
}
