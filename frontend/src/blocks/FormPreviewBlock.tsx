import { useState } from "react";
import { View, ChartColumn } from "@carbon/icons-react";
import type { FormPreview, PreviewAxis } from "../schemas/types";

const AXIS_LABEL: Record<string, string> = { pov: "POV", page: "Pages", row: "Rows", column: "Columns" };

function AxisChips({ axes }: { axes: PreviewAxis[] }) {
  if (!axes.length) return null;
  return (
    <div className="axis-chips">
      {axes.map((a, i) => (
        <span className="axis-chip" key={i}>
          <b>{AXIS_LABEL[a.kind] || a.kind}</b> · {a.dimension}: {a.selectionSummary}
          {(a.resolvedCount ?? 0) > 1 ? ` (${a.resolvedCount})` : ""}
        </span>
      ))}
    </div>
  );
}

export function FormPreviewBlock({ data }: { data: FormPreview }) {
  const [expanded, setExpanded] = useState(false);
  const cols = data.columnLabels || [];
  const rows = data.rowLabels || [];
  const shownRows = expanded ? rows : rows.slice(0, 8);
  const status = data.validationStatus;
  const statusColor = status === "invalid" ? "#ff8389" : status === "warnings" ? "#f1c21b" : "#42be65";

  return (
    <div className="block-card">
      <div className="block-head">
        <ChartColumn size={16} />
        <span>Form preview — {data.formName}</span>
        <span className="grow" />
        <span className="tag-inline">{data.cube}</span>
        <span style={{ color: statusColor, fontSize: 11 }}>● {status}</span>
      </div>
      <div className="block-body">
        <div style={{ fontSize: 12, color: "var(--cds-text-secondary)", marginBottom: 6 }}>
          {data.application} · {data.folder}
          {data.referenceTemplate ? ` · from ${data.referenceTemplate}` : ""}
          {data.ruleAssociations?.length ? ` · rules: ${data.ruleAssociations.join(", ")}` : ""}
        </div>
        <AxisChips axes={[...(data.pov || []), ...(data.pages || []), ...(data.rows || []), ...(data.columns || [])]} />
        <div className="grid-preview">
          <table className="epm-grid">
            <thead>
              <tr>
                <th className="rowhdr" />
                {cols.map((c, i) => (
                  <th key={i}>{c}</th>
                ))}
                {data.columnsTruncated && <th>…</th>}
              </tr>
            </thead>
            <tbody>
              {shownRows.map((r, ri) => (
                <tr key={ri}>
                  <td className="rowhdr">{r}</td>
                  {cols.map((_, ci) => (
                    <td className="cell" key={ci}>
                      —
                    </td>
                  ))}
                  {data.columnsTruncated && <td className="cell">—</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 12, color: "var(--cds-text-secondary)" }}>
          <span>
            {data.sizeEstimate ? `~${(data.sizeEstimate.totalCells ?? 0).toLocaleString()} cells` : ""}
            {data.hiddenMembers?.length ? ` · hidden: ${data.hiddenMembers.join(", ")}` : ""}
          </span>
          {rows.length > 8 && (
            <button className="conv-item" style={{ width: "auto", padding: "2px 6px" }} onClick={() => setExpanded((v) => !v)}>
              <View size={14} /> {expanded ? "Show fewer rows" : `Show all ${rows.length} rows`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
