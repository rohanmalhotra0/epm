// Renders the assistant's `spreadsheetPreview` block: what the backend detected
// in an uploaded spreadsheet/CSV. The shape is still evolving server-side, so
// every field is accessed defensively — missing/extra fields must never crash.

import { DataTable as DataTableIcon, Warning } from "@carbon/icons-react";
import { attachmentKindLabel } from "../api/attachments";

export function SpreadsheetBlock({ data }: { data: any }) {
  const d = data || {};
  const columns: any[] = Array.isArray(d.columns) ? d.columns : [];
  const sampleRows: any[][] = Array.isArray(d.sampleRows) ? d.sampleRows.filter(Array.isArray) : [];
  const issues: any[] = Array.isArray(d.issues) ? d.issues : [];
  return (
    <div className="block-card">
      <div className="block-head">
        <DataTableIcon size={16} /> <span className="mono">{d.filename || "Spreadsheet"}</span>
        {d.sheetName && <span className="tag-inline">{d.sheetName}</span>}
        <span className="grow" />
        <span className="tag-inline">{attachmentKindLabel(d.kind)}</span>
      </div>
      <div className="block-body">
        {columns.length > 0 && (
          <>
            <div className="sheet-section-label">Detected columns</div>
            <div className="grid-preview">
              <table className="data-table">
                <thead>
                  <tr><th>#</th><th>Header</th><th>Role</th></tr>
                </thead>
                <tbody>
                  {columns.map((c, i) => (
                    <tr key={i}>
                      <td className="mono">{c?.index ?? i}</td>
                      <td>{c?.header ?? "—"}</td>
                      <td>{c?.role ? <span className="tag-inline role-badge">{String(c.role)}</span> : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {sampleRows.length > 0 && (
          <>
            <div className="sheet-section-label">Sample rows</div>
            <div className="grid-preview sheet-samples">
              <table className="data-table mono">
                <tbody>
                  {sampleRows.map((row, i) => (
                    <tr key={i}>
                      {row.map((cell, j) => (
                        <td key={j}>{cell == null ? "" : String(cell)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {(d.memberCount != null || d.dimensionGuess) && (
          <div style={{ fontSize: 12, color: "var(--cds-text-secondary)", marginTop: 8 }}>
            {d.memberCount != null && <span><b>{Number(d.memberCount).toLocaleString()}</b> members</span>}
            {d.memberCount != null && d.dimensionGuess && " · "}
            {d.dimensionGuess && <span>dimension guess: <b>{String(d.dimensionGuess)}</b></span>}
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
        {columns.length === 0 && sampleRows.length === 0 && issues.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--cds-text-secondary)" }}>No preview details available.</div>
        )}
      </div>
    </div>
  );
}
