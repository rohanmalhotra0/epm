// Oracle-EPM-styled report grid with per-cell and per-table inline prompts.
//
// Rendering uses the smart-formatted values the backend already computed in the
// ReportPreview (formatted string + colour/background/bold flags), so the grid
// always matches the downloaded HTML. Clicking a cell opens a scoped prompt box;
// the table header exposes a table-scoped prompt. Edits round-trip through
// /api/artifact/edit and refresh the whole preview.

import { useState } from "react";
import type { ReportGridPreview, ReportPreview } from "../schemas/types";
import { promptEdit } from "./api";
import { useArtifacts } from "./store";

function cellStyle(c: { color?: string | null; background?: string | null; bold?: boolean }): React.CSSProperties {
  return {
    color: c.color ?? undefined,
    background: c.background ?? undefined,
    fontWeight: c.bold ? 700 : undefined,
  };
}

interface PromptBoxProps {
  placeholder: string;
  onSubmit: (text: string) => void;
  onCancel: () => void;
  busy?: boolean;
}

function PromptBox({ placeholder, onSubmit, onCancel, busy }: PromptBoxProps) {
  const [text, setText] = useState("");
  return (
    <div className="epmw-promptbox" onClick={(e) => e.stopPropagation()}>
      <input
        autoFocus
        value={text}
        placeholder={placeholder}
        disabled={busy}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && text.trim()) onSubmit(text.trim());
          if (e.key === "Escape") onCancel();
        }}
      />
      <button disabled={busy || !text.trim()} onClick={() => onSubmit(text.trim())}>
        {busy ? "…" : "Apply"}
      </button>
      <button className="ghost" onClick={onCancel}>✕</button>
    </div>
  );
}

export function ReportView({ preview }: { preview: ReportPreview }) {
  const { artifact, projectId, update } = useArtifacts();
  const [target, setTarget] = useState<{ grid: number; row?: string; col?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!artifact) return null;

  async function runEdit(scope: "table" | "cell", gridIndex: number, instruction: string, row?: string, col?: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await promptEdit(
        { artifactKind: "reportSpec", scope, instruction, spec: artifact!.spec, gridIndex, rowLabel: row, columnLabel: col },
        projectId,
      );
      if (res.changed && res.spec) update(res.spec, res.preview ?? undefined);
      else setError(res.questions?.[0] ?? "No change was applied.");
      setTarget(null);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="epmw-report">
      {error && <div className="epmw-error">{error}</div>}
      {(preview.grids ?? []).map((grid, gi) => (
        <Grid
          key={grid.name + gi}
          grid={grid}
          gridIndex={gi}
          target={target}
          busy={busy}
          onTablePrompt={() => setTarget({ grid: gi })}
          onCellPrompt={(row, col) => setTarget({ grid: gi, row, col })}
          onCancel={() => setTarget(null)}
          onSubmit={(instruction) => {
            if (target?.row && target?.col) runEdit("cell", gi, instruction, target.row, target.col);
            else runEdit("table", gi, instruction);
          }}
        />
      ))}
    </div>
  );
}

interface GridProps {
  grid: ReportGridPreview;
  gridIndex: number;
  target: { grid: number; row?: string; col?: string } | null;
  busy: boolean;
  onTablePrompt: () => void;
  onCellPrompt: (row: string, col: string) => void;
  onCancel: () => void;
  onSubmit: (instruction: string) => void;
}

function Grid({ grid, gridIndex, target, busy, onTablePrompt, onCellPrompt, onCancel, onSubmit }: GridProps) {
  const cols = grid.columnLabels ?? [];
  const tableTargeted = target?.grid === gridIndex && !target.row;
  return (
    <div className="epmw-grid">
      <div className="epmw-grid-head">
        <span className="epmw-grid-title">{grid.name}</span>
        <button className="epmw-tableprompt" onClick={onTablePrompt} title="Prompt this whole table">✎ table</button>
      </div>
      {(grid.pov?.length || grid.pages?.length) ? (
        <div className="epmw-pov">
          {[...(grid.pov ?? []), ...(grid.pages ?? [])].map((p) => (
            <span className="epmw-chip" key={p}>{p}</span>
          ))}
        </div>
      ) : null}
      {tableTargeted && (
        <PromptBox placeholder={`Prompt for "${grid.name}" (e.g. show as millions, add a bar chart)`} busy={busy} onSubmit={onSubmit} onCancel={onCancel} />
      )}
      <div className="epmw-tablewrap">
        <table className="epmw-table">
          <thead>
            <tr>
              <th className="rowhead" />
              {cols.map((c) => <th key={c}>{c}</th>)}
              {grid.showRowTotals && <th>Total</th>}
            </tr>
          </thead>
          <tbody>
            {(grid.rows ?? []).map((row) => (
              <tr key={row.label}>
                <td className="rowhead">{row.label}</td>
                {(row.cells ?? []).map((cell, ci) => {
                  const col = cols[ci];
                  const isTarget = target?.grid === gridIndex && target.row === row.label && target.col === col;
                  return (
                    <td
                      key={col}
                      style={cellStyle(cell)}
                      className={"epmw-cell" + (isTarget ? " targeted" : "")}
                      title={cell.note ?? "Click to prompt this cell"}
                      onClick={() => onCellPrompt(row.label, col)}
                    >
                      {cell.formatted}
                      {isTarget && (
                        <PromptBox placeholder={`Prompt ${row.label} · ${col} (e.g. set to 1200, bold red, note: …)`} busy={busy} onSubmit={onSubmit} onCancel={onCancel} />
                      )}
                    </td>
                  );
                })}
                {grid.showRowTotals && row.total && <td style={cellStyle(row.total)}>{row.total.formatted}</td>}
              </tr>
            ))}
          </tbody>
          {grid.showColumnTotals && (grid.columnTotals?.length ?? 0) > 0 && (
            <tfoot>
              <tr>
                <td className="rowhead">Total</td>
                {(grid.columnTotals ?? []).map((cell, ci) => (
                  <td key={cols[ci] ?? ci} style={cellStyle(cell)}>{cell.formatted}</td>
                ))}
                {grid.showRowTotals && <td />}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      {(grid.rowsTruncated || grid.columnsTruncated) && (
        <div className="epmw-trunc">Preview truncated to fit — the download contains all rows/columns.</div>
      )}
    </div>
  );
}
