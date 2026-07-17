// Artifacts-panel state (zustand).
//
// Holds the currently-open artifact and whether the panel is visible. The panel
// is OPT-IN: it starts closed and is only shown when the user clicks the
// top-right toggle (see ArtifactToggle) or "Open in panel" on a chat block. It
// never auto-opens when an artifact block streams in.

import { create } from "zustand";
import type { FormSpecification, ReportSpecification } from "../schemas/types";

export type ArtifactKind = "formSpec" | "reportSpec";
export type ArtifactTab = "view" | "edit";

export interface OpenArtifact {
  kind: ArtifactKind;
  /** camelCase spec JSON (FormSpecification | ReportSpecification) */
  spec: Record<string, unknown>;
  /** last-known preview payload (FormPreview | ReportPreview), if any */
  preview?: Record<string, unknown> | null;
  title: string;
  /** the message id this artifact came from, for provenance */
  sourceMessageId?: string;
}

interface ArtifactsState {
  open: boolean;
  tab: ArtifactTab;
  artifact: OpenArtifact | null;
  projectId?: string;

  setProjectId: (id?: string) => void;
  /** Open the panel with an artifact (used by "Open in panel" buttons). */
  openArtifact: (a: OpenArtifact) => void;
  /** Keep the artifact but toggle panel visibility (top-right button). */
  toggle: () => void;
  close: () => void;
  setTab: (tab: ArtifactTab) => void;
  /** Replace the current spec+preview after an edit round-trips. */
  update: (spec: Record<string, unknown>, preview?: Record<string, unknown> | null) => void;
}

export const useArtifacts = create<ArtifactsState>((set) => ({
  open: false,
  tab: "view",
  artifact: null,
  projectId: undefined,

  setProjectId: (id) => set({ projectId: id }),
  openArtifact: (a) => set({ artifact: a, open: true, tab: "view" }),
  toggle: () => set((s) => ({ open: !s.open })),
  close: () => set({ open: false }),
  setTab: (tab) => set({ tab }),
  update: (spec, preview) =>
    set((s) => (s.artifact ? { artifact: { ...s.artifact, spec, preview: preview ?? s.artifact.preview } } : {})),
}));

export function specTitle(kind: ArtifactKind, spec: Record<string, unknown>): string {
  const s = spec as Partial<FormSpecification & ReportSpecification>;
  return (s.name as string) || (kind === "reportSpec" ? "Report" : "Form");
}
