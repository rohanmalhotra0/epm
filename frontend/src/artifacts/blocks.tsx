// Chat-block renderers for the artifact block types + the top-right panel toggle.
//
// These are the TWO integration seams with the chat shell:
//   1) In your ChatBlock switch, render <ArtifactBlock/> for the four artifact
//      block types (reportPreview, reportSpecification, formPreview,
//      formSpecification). It shows a compact inline card + an "Open in panel"
//      button — it does NOT auto-open the panel (opt-in, like Claude).
//   2) Put <ArtifactToggle/> in the chat's top-right header to show/hide the
//      panel for the most-recently-opened artifact.

import { specTitle, useArtifacts, type ArtifactKind } from "./store";

/** Minimal block shape (matches both the generated ChatBlock and the shell's ChatBlockT). */
export interface ArtifactBlockT {
  id: string;
  type: string;
  data?: Record<string, unknown> | null;
}

const KIND_LABEL: Record<string, string> = {
  reportSpecification: "Report",
  reportPreview: "Report preview",
  formSpecification: "Form",
  formPreview: "Form preview",
};

/** True for block types this module knows how to open in the panel. */
export function isArtifactBlock(type: string): boolean {
  return type in KIND_LABEL;
}

export function ArtifactToggle() {
  const { open, artifact, toggle } = useArtifacts();
  if (!artifact) return null; // nothing to show yet
  return (
    <button className={"epmw-toggle" + (open ? " active" : "")} onClick={toggle} title="Toggle artifacts panel">
      ▤ {open ? "Hide" : artifact.kind === "reportSpec" ? "Report" : "Form"}
    </button>
  );
}

/** Inline card for an artifact block, with an opt-in "Open in panel" action. */
export function ArtifactBlock({ block, messageId }: { block: ArtifactBlockT; messageId?: string }) {
  const openArtifact = useArtifacts((s) => s.openArtifact);
  const data = (block.data ?? {}) as Record<string, unknown>;
  const type = String(block.type);

  const isReport = type.startsWith("report");
  const kind: ArtifactKind = isReport ? "reportSpec" : "formSpec";

  // "*Specification" blocks carry {spec, preview?}; "*Preview" blocks ARE the preview.
  const isSpecBlock = type.endsWith("Specification");
  const spec = (isSpecBlock ? (data.spec as Record<string, unknown>) : undefined) ?? undefined;
  const preview = (isSpecBlock ? (data.preview as Record<string, unknown> | undefined) : data) ?? undefined;

  const title = spec ? specTitle(kind, spec) : (isReport ? String(data.reportName ?? "Report") : String(data.formName ?? "Form"));
  const canOpen = Boolean(spec); // only *Specification blocks carry an editable spec

  return (
    <div className="epmw-block-card">
      <div className="epmw-block-head">
        <span className="epmw-block-kind">{KIND_LABEL[type] ?? type}</span>
        <strong>{title}</strong>
      </div>
      <ArtifactSummary type={type} data={data} />
      {canOpen && (
        <button
          className="epmw-openpanel"
          onClick={() => openArtifact({ kind, spec: spec!, preview: preview ?? null, title, sourceMessageId: messageId })}
        >
          Open in panel ↗
        </button>
      )}
    </div>
  );
}

function ArtifactSummary({ type, data }: { type: string; data: Record<string, unknown> }) {
  if (type === "reportPreview" || type === "reportSpecification") {
    const preview = (type === "reportSpecification" ? (data.preview as Record<string, unknown> | undefined) : data) ?? {};
    const grids = (preview.grids as Array<{ name: string; columnLabels?: string[]; rows?: unknown[] }>) ?? [];
    return (
      <div className="epmw-block-summary">
        {grids.map((g) => (
          <span key={g.name}>{g.name}: {(g.rows?.length ?? 0)}×{(g.columnLabels?.length ?? 0)}</span>
        ))}
      </div>
    );
  }
  const preview = (type === "formSpecification" ? (data.preview as Record<string, unknown> | undefined) : data) ?? {};
  const rows = (preview.rowLabels as string[] | undefined)?.length ?? 0;
  const cols = (preview.columnLabels as string[] | undefined)?.length ?? 0;
  return <div className="epmw-block-summary"><span>{rows}×{cols} grid</span></div>;
}
