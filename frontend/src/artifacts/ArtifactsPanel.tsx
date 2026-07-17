// The Claude-style artifacts side panel.
//
// Opt-in: rendered only when the store says `open` and an artifact is loaded.
// Tabs swap between the rendered View (Oracle-EPM report grid or form preview)
// and Edit (whole-artifact prompt + spec). Reports expose a Download control.
// Mount <ArtifactsPanel/> once, alongside your chat column (see README).

import { useEffect, useState } from "react";
import type { FormPreview, ReportPreview } from "../schemas/types";
import { downloadArtifact, formPreview, reportDownload, reportPreview } from "./api";
import { EditTab } from "./EditTab";
import { FormView } from "./FormView";
import { ReportView } from "./ReportView";
import { useArtifacts } from "./store";

export function ArtifactsPanel() {
  const { open, tab, artifact, projectId, setTab, close, update } = useArtifacts();
  const [downloading, setDownloading] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);

  // Ensure a preview exists for the View tab (fetch if the block didn't carry one).
  useEffect(() => {
    let cancelled = false;
    if (open && artifact && !artifact.preview) {
      setLoadingPreview(true);
      const fetcher = artifact.kind === "reportSpec" ? reportPreview : formPreview;
      fetcher(artifact.spec, projectId)
        .then((p) => { if (!cancelled) update(artifact.spec, p as unknown as Record<string, unknown>); })
        .catch(() => undefined)
        .finally(() => { if (!cancelled) setLoadingPreview(false); });
    }
    return () => { cancelled = true; };
  }, [open, artifact, projectId, update]);

  if (!open || !artifact) return null;

  async function onDownload() {
    if (!artifact || artifact.kind !== "reportSpec") return;
    setDownloading(true);
    try {
      const res = await reportDownload(artifact.spec, projectId);
      downloadArtifact(res.downloadUrl);
    } finally {
      setDownloading(false);
    }
  }

  const preview = artifact.preview ?? null;

  return (
    <aside className="epmw-panel" aria-label="Artifacts">
      <header className="epmw-panel-head">
        <div className="epmw-panel-title">
          <span className="epmw-kind">{artifact.kind === "reportSpec" ? "Report" : "Form"}</span>
          <strong>{artifact.title}</strong>
        </div>
        <div className="epmw-panel-actions">
          <div className="epmw-tabs" role="tablist">
            <button role="tab" aria-selected={tab === "view"} className={tab === "view" ? "active" : ""} onClick={() => setTab("view")}>
              {artifact.kind === "reportSpec" ? "Report" : "Form"}
            </button>
            <button role="tab" aria-selected={tab === "edit"} className={tab === "edit" ? "active" : ""} onClick={() => setTab("edit")}>
              Edit
            </button>
          </div>
          {artifact.kind === "reportSpec" && (
            <button className="epmw-download" disabled={downloading} onClick={onDownload} title="Download HTML + CSV + JSON + Markdown">
              {downloading ? "…" : "⭳ Download"}
            </button>
          )}
          <button className="epmw-close" onClick={close} aria-label="Close panel">✕</button>
        </div>
      </header>

      <div className="epmw-panel-body">
        {tab === "edit" ? (
          <EditTab />
        ) : loadingPreview && !preview ? (
          <div className="epmw-loading">Rendering…</div>
        ) : preview ? (
          artifact.kind === "reportSpec" ? (
            <ReportView preview={preview as unknown as ReportPreview} />
          ) : (
            <FormView preview={preview as unknown as FormPreview} />
          )
        ) : (
          <div className="epmw-loading">No preview available.</div>
        )}
      </div>
    </aside>
  );
}
