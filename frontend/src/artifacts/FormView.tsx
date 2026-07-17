// Form preview grid (read-only structural preview, matching the wizard).
//
// Shows the resolved POV/Page bar and the row×column grid with "—" placeholders,
// exactly like the inline wizard preview — just larger, in the panel. Editing a
// form is done via the Edit tab's prompt box (whole-artifact scope), since form
// cells are data-entry intersections, not values.

import type { FormPreview, PreviewAxis } from "../schemas/types";

function axisChips(title: string, axes?: Array<PreviewAxis>) {
  if (!axes || axes.length === 0) return null;
  return (
    <div className="epmw-pov">
      <span className="epmw-pov-label">{title}</span>
      {axes.map((a) => (
        <span className="epmw-chip" key={a.dimension} title={a.selectionSummary}>
          {a.dimension}: {a.selectionSummary}
        </span>
      ))}
    </div>
  );
}

export function FormView({ preview }: { preview: FormPreview }) {
  const cols = preview.columnLabels ?? [];
  const rows = preview.rowLabels ?? [];
  return (
    <div className="epmw-report">
      <div className="epmw-grid">
        <div className="epmw-grid-head">
          <span className="epmw-grid-title">{preview.formName}</span>
          <span className={"epmw-badge " + (preview.validationStatus === "valid" ? "ok" : "warn")}>
            {preview.validationStatus}
          </span>
        </div>
        {axisChips("POV", preview.pov)}
        {axisChips("Pages", preview.pages)}
        <div className="epmw-tablewrap">
          <table className="epmw-table">
            <thead>
              <tr>
                <th className="rowhead" />
                {cols.map((c) => <th key={c}>{c}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r}>
                  <td className="rowhead">{r}</td>
                  {cols.map((c) => <td key={c} className="epmw-empty">—</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(preview.rowsTruncated || preview.columnsTruncated) && (
          <div className="epmw-trunc">Preview truncated for display.</div>
        )}
        {preview.sizeEstimate && (
          <div className="epmw-trunc">
            ~{(preview.sizeEstimate.totalCells ?? 0).toLocaleString()} cells across the full form.
          </div>
        )}
      </div>
      {(preview.ruleAssociations?.length ?? 0) > 0 && (
        <div className="epmw-rules"><b>Business rules:</b> {preview.ruleAssociations!.join(", ")}</div>
      )}
    </div>
  );
}
